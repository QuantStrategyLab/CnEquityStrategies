# CN Index ETF Tactical Rotation

## Summary

Monthly-reviewed A-share ETF tactical rotation using:

- 60-day momentum ranking
- 200-day trend filter
- inverse-volatility weighting across top-2 eligible ETFs
- 14% annualized portfolio volatility target
- CSI300 (`510300`) benchmark risk-off switch into defensive ETFs (`511880`, `511260`)

## Default universe

| Symbol | Role |
| --- | --- |
| `510300` | CSI300 benchmark / broad beta |
| `510500` | CSI500 mid-cap beta |
| `159915` | ChiNext growth beta |
| `588000` | STAR50 innovation beta |
| `512100` | CSI1000 small-cap beta |
| `512170` | Healthcare sector |
| `515030` | New energy sector |
| `512760` | Semiconductor sector |
| `518880` | Gold hedge |
| `513100` | Nasdaq cross-market beta |

## Risk controls

- When CSI300 closes below its 200-day moving average, the strategy switches to defensive ETF allocation.
- Volatility targeting caps gross exposure below 100% when realized portfolio volatility exceeds the target.
- Platform execution must enforce T+1, 100-share lot sizing, and limit-up/limit-down constraints.

## Evidence boundary

Backtest and smoke outputs in this repository are engineering evidence only. They are not return promises and must be rerun before any live enablement decision.
