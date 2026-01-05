# run_console.py
# Simple CLI wrapper around optimization_console functions.
import argparse, os, glob
import pandas as pd
from optimization_console import (
    load_json_results, add_risk_derivatives, qc_filter, composite_score,
    pareto_frontier, stability_by_params, param_spearman, partial_dependence,
    generalization_report, topk_per_group, export_df, query_df
)

def main():
    ap = argparse.ArgumentParser(description="Optimization Results Console (JSON)")
    ap.add_argument("--data_dir", type=str, default=".", help="Directory with *.json result files")
    ap.add_argument("--out_dir", type=str, default="./console_exports", help="Directory to write exports")
    ap.add_argument("--min_trades", type=int, default=20)
    ap.add_argument("--max_mdd", type=float, default=0.10, help="Fraction (0.10 = 10%)")
    ap.add_argument("--score_weights", type=str, default="",
                    help='JSON dict of weights: e.g. {"sharpe_ratio":1,"calmar_ratio":1,"max_drawdown":-1}')
    ap.add_argument("--topk_group_by", type=str, default="chart", help="Group column(s) separated by commas")
    ap.add_argument("--topk_sort_by", type=str, default="-calmar_ratio")
    ap.add_argument("--topk_k", type=int, default=5)
    ap.add_argument("--topk_filter", type=str, default="profit_factor >= 1.6 and calmar_ratio > 0 and max_drawdown < 10% and total_trades >= 20")
    ap.add_argument("--pd_param", type=str, default="", help="Parameter name for partial dependence")
    ap.add_argument("--pd_metric", type=str, default="calmar_ratio")
    args = ap.parse_args()

    paths = glob.glob(os.path.join(args.data_dir, "*.json"))
    df = load_json_results(paths)
    if df.empty:
        print("No JSON files found.")
        return

    df = add_risk_derivatives(df)
    base = qc_filter(df, min_trades=args.min_trades, max_mdd=args.max_mdd, nondegenerate=True)

    # Score
    weights = None
    if args.score_weights.strip():
        try:
            import json
            weights = json.loads(args.score_weights)
        except Exception as e:
            print(f"Invalid --score_weights JSON, using defaults. Error: {e}")
    scored = composite_score(base, weights=weights).sort_values("score", ascending=False)

    # Pareto
    pf = pareto_frontier(base, objectives=[("calmar_ratio","max"),("max_drawdown","min"),("profit_factor","max")])

    # Stability
    stab = stability_by_params(base, metrics=["calmar_ratio","profit_factor","max_drawdown"], lambda_std=0.5)

    # Correlations
    corr = param_spearman(base, metric_cols=["calmar_ratio","profit_factor","max_drawdown","sharpe_ratio"])

    # Partial dependence
    pd_table = None
    if args.pd_param:
        pd_table = partial_dependence(base, param=args.pd_param, metric=args.pd_metric)

    # Top-k per group
    group_cols = [c.strip() for c in args.topk_group_by.split(",") if c.strip()]
    topk = topk_per_group(base, group_by=group_cols if len(group_cols)>1 else group_cols[0],
                          sort_by=args.topk_sort_by, k=args.topk_k, filter_expr=args.topk_filter)

    # Generalization
    gen = generalization_report(df)

    os.makedirs(args.out_dir, exist_ok=True)

    # Exports
    export_df(df, args.out_dir, "all_merged_extended")
    export_df(scored.head(1000), args.out_dir, "qc_scored_top1000")
    export_df(pf, args.out_dir, "pareto_frontier")
    if stab is not None and not stab.empty:
        export_df(stab.sort_values(stab.columns[-1], ascending=False), args.out_dir, "stability_params")
    if corr is not None and not corr.empty:
        export_df(corr.reset_index(), args.out_dir, "param_metric_spearman")
    if pd_table is not None and not pd_table.empty:
        export_df(pd_table, args.out_dir, f"partial_dependence_{args.pd_param}_to_{args.pd_metric}")
    if topk is not None and not topk.empty:
        export_df(topk, args.out_dir, "topk_per_group")
    if gen is not None and not gen.empty:
        export_df(gen, args.out_dir, "generalization_report")

    print(f"Exports written to: {args.out_dir}")

if __name__ == "__main__":
    main()
