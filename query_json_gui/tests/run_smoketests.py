from __future__ import annotations

import io
import json
import logging
import os
import sys
import tempfile
from datetime import datetime

import pandas as pd
import re

import optimization_console as oc
from ui_helpers import format_value_for_display, truncate_for_view
try:
    # When executed as a module
    from .smoketest_data import generate_fixtures
except Exception:
    # When executed as a script
    from tests.smoketest_data import generate_fixtures


def setup_logging(log_dir: str) -> str:
    from logging.handlers import RotatingFileHandler
    logger = logging.getLogger("opt_console_ui")
    logger.setLevel(logging.INFO)
    for h in list(logger.handlers):
        logger.removeHandler(h)
    log_path = os.path.join(log_dir, "opt_console_ui.log")
    handler = RotatingFileHandler(log_path, maxBytes=1024 * 1024, backupCount=5, encoding="utf-8")
    fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    return log_path


def print_result(name: str, ok: bool, detail: str = ""):
    status = "PASS" if ok else "FAIL"
    line = f"{status} - {name}"
    if detail:
        line += f" - {detail}"
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        print(line.encode(enc, errors="ignore").decode(enc, errors="ignore"))
    except Exception:
        print(line)


def check_sidecar_keys(sidecar_path: str) -> bool:
    required = [
        "app_version", "timestamp_utc", "profile_name", "qc_params", "filter_expr",
        "sort_by", "limit", "group_by", "objectives_weights", "visible_columns",
        "_source_files", "row_count"
    ]
    with open(sidecar_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    return list(meta.keys()) == required


def main() -> int:
    overall_ok = True
    with tempfile.TemporaryDirectory() as tmp:
        # Setup logging
        log_path = setup_logging(tmp)

        # Generate fixtures (Unicode workspace)
        ws, files = generate_fixtures(tmp)

        # Load using engine
        df = oc.load_json_results(files)
        df = oc.add_risk_derivatives(df)

        # Write log entries
        logging.getLogger("opt_console_ui").info("Test: good load event")
        try:
            raise ValueError("Fake error for rotation test")
        except Exception as exc:
            logging.getLogger("opt_console_ui").error(f"Test: fake error: {exc}")

        # 1) Export sidecar keys EXACT
        meta = {
            "profile_name": "SmokeTest",
            "qc_params": {"min_trades": 20, "max_mdd": 0.10, "nondegenerate": True},
            "filter_expr": "profit_factor >= 1.5",
            "sort_by": "-calmar_ratio",
            "limit": None,
            "group_by": "chart",
            "objectives_weights": "Default Pareto: calmar_ratio(max), max_drawdown(min), profit_factor(max)",
            "visible_columns": list(df.columns),
        }
        csv_path, parquet_path, sidecar_path = oc.export_df(df, ws, name="smoketest", meta=meta)
        ok1 = check_sidecar_keys(sidecar_path)
        print_result("Export sidecar keys exact", ok1)
        overall_ok &= ok1

        # 2) Logging rotation & entries
        # Grow log file > 1MB for rotation
        logger = logging.getLogger("opt_console_ui")
        big_msg = "X" * 10000
        for _ in range(120):
            logger.info(big_msg)
        # Check existence of base log and at least one rotated file
        rotated_exists = any(os.path.exists(f"{log_path}.{i}") for i in range(1, 3))
        has_base = os.path.exists(log_path)
        ok2 = has_base and rotated_exists
        print_result("Logging rotation present (1MB x5)", ok2, log_path)
        overall_ok &= ok2

        # 3) Percent parsing parity
        df_parity = df.copy()
        f1 = oc.query_df(df_parity, filter_expr="max_drawdown < 8%")
        f2 = oc.query_df(df_parity, filter_expr="max_drawdown < 8 %")
        f3 = oc.query_df(df_parity, filter_expr="max_drawdown < 0.08")
        cols = [c for c in ["calmar_ratio", "profit_factor", "max_drawdown", "_source_file"] if c in df.columns]
        def sig_rows(d):
            if cols:
                rows = d[cols].copy()
                # Cast types for stable comparison
                for col in rows.columns:
                    if isinstance(rows[col].dtype, pd.api.types.CategoricalDtype):
                        rows[col] = rows[col].astype(str)
                return rows.sort_values(by=cols, axis=0).reset_index(drop=True).to_json(orient="records")
            return d.reset_index(drop=True).to_json(orient="records")
        ok3 = sig_rows(f1) == sig_rows(f2) == sig_rows(f3)
        print_result("Percent parsing parity", ok3)
        overall_ok &= ok3

        # 4) Sorting & formatting helpers
        sorted_asc = df.sort_values(by=["calmar_ratio"], ascending=[True]).reset_index(drop=True)
        sorted_desc = df.sort_values(by=["calmar_ratio"], ascending=[False]).reset_index(drop=True)
        toggles = sorted_asc.iloc[0]["calmar_ratio"] <= sorted_desc.iloc[0]["calmar_ratio"]
        fmt_percent = format_value_for_display("max_drawdown", 0.1234)
        fmt_win = format_value_for_display("win_rate", 0.8765)
        fmt_other = format_value_for_display("profit_factor", 1.234567)
        two_dec_pct = bool(re.match(r"^\d+\.\d{2}%$", fmt_percent)) and bool(re.match(r"^\d+\.\d{2}%$", fmt_win))
        four_dec_other = bool(re.match(r"^\d+\.\d{4}$", fmt_other))
        ok4 = toggles and two_dec_pct and four_dec_other
        print_result("Sorting toggles & formatting helpers", ok4, f"{fmt_percent}, {fmt_win}, {fmt_other}")
        overall_ok &= ok4

        # 5) Unicode paths load & export already validated via ws
        try:
            with open(sidecar_path, "r", encoding="utf-8") as f:
                _ = json.load(f)
            ok5 = True
        except Exception:
            ok5 = False
        print_result("Unicode paths load & export", ok5)
        overall_ok &= ok5

        # 6) Large dataset truncation helper
        large_df = pd.DataFrame({
            "calmar_ratio": list(range(60000)),
            "max_drawdown": [0.05] * 60000,
            "profit_factor": [1.5] * 60000,
        })
        display_df, suffix = truncate_for_view(large_df, cap=50_000)
        ok6 = len(display_df) == 50_000 and suffix.strip().startswith("| Showing 50,000 of")
        print_result("Large dataset truncation helper", ok6, suffix)
        overall_ok &= ok6

        # Print summary and fully release logs BEFORE temp dir cleanup
        print("\n=== Smoketest Summary ===")
        print("RESULT:", "PASS" if overall_ok else "FAIL")
        try:
            lg = logging.getLogger("opt_console_ui")
            for h in list(lg.handlers):
                try:
                    h.flush()
                except Exception:
                    pass
                try:
                    h.close()
                except Exception:
                    pass
                try:
                    lg.removeHandler(h)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            logging.shutdown()
        except Exception:
            pass
        return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())


