# Platform integration

## Runtime-enabled profiles

| Profile | Input | Platform | Target mode |
| --- | --- | --- | --- |
| `cn_index_etf_tactical_rotation` | `market_history` | `qmt` | `weight` |

## Environment variables (planned for QmtPlatform)

| Variable | Purpose |
| --- | --- |
| `STRATEGY_PROFILE` | Canonical profile name, e.g. `cn_index_etf_tactical_rotation` |
| `QMT_DRY_RUN_ONLY` | Default `true`; set to `false` only after evidence review |
| `QMT_MARKET_HISTORY_PATH` | Optional local or GCS path for cached market history |

## Market history contract

Direct runtime profiles require a long-form daily history with columns:

- `date`
- `symbol` (6-digit A-share ETF code, with or without `.SH`/`.SZ` suffix)
- `close`

The strategy also requires defensive ETF history for benchmark risk-off switching:

- `511880` (money-market ETF)
- `511260` (10-year government bond ETF)

## Planned snapshot profile

`cn_dividend_low_vol_quality_snapshot` is tracked as an external snapshot scaffold only. It is not registered in the runtime catalog until `CnEquitySnapshotPipelines` publishes a contract and promotion evidence.
