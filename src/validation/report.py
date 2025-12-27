def human_readable_report(stats: dict) -> list[str]:
    import numpy as np
    lines = []
    sr = stats.get('Sharpe Ratio', np.nan)
    if not np.isnan(sr):
        if sr > 2:
            lines.append(f"Sharpe {sr:.2f}: Outstanding risk-adjusted return.")
        elif sr > 1:
            lines.append(f"Sharpe {sr:.2f}: Good risk-adjusted performance.")
        elif sr > 0.5:
            lines.append(f"Sharpe {sr:.2f}: Moderate; some edge.")
        else:
            lines.append(f"Sharpe {sr:.2f}: Weak risk-adjusted return.")
    sor = stats.get('Sortino Ratio', np.nan)
    if not np.isnan(sor):
        lines.append(f"Sortino {sor:.2f}")
    mdd = stats.get('Max Drawdown [%]', np.nan)
    if not np.isnan(mdd):
        lines.append(f"Max DD {mdd:.2f}%")
    wr = stats.get('Win Rate [%]', np.nan)
    if not np.isnan(wr):
        lines.append(f"Win Rate {wr:.1f}%")
    pf = stats.get('Profit Factor', np.nan)
    if not np.isnan(pf):
        lines.append(f"Profit Factor {pf:.2f}")
    exp = stats.get('Expectancy', np.nan)
    if not np.isnan(exp):
        lines.append(f"Expectancy {exp:.4f}")
    return lines


