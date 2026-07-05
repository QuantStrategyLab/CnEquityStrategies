# Platform integration

## Runtime-enabled profiles

| Profile | Input | Platform | Target mode |
| --- | --- | --- | --- |
| `cn_industry_etf_rotation` | `market_history` | `qmt` | `weight` |

## Live candidate profiles

| Profile | Input | Platform | Target mode |
| --- | --- | --- | --- |
| `cn_industry_etf_rotation_aggressive` | `market_history` | `qmt` | `weight` |

## Research-only profiles

| Profile | Input | Platform | Target mode |
| --- | --- | --- | --- |
| `cn_index_etf_tactical_rotation` | `market_history` | `qmt` | `weight` |
| `cn_dividend_quality_snapshot` | `feature_snapshot` + manifest | `qmt` | `weight` |
| `cn_chinext_tactical_rotation` | `market_history` | `qmt` | `weight` |
| `cn_equity_combo` | `market_history` + `feature_snapshot` | `qmt` | `weight` |

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

## Planned snapshot scaffolds

`cn_small_cap_quality_snapshot` and `cn_chinext_growth_momentum_quality_snapshot` are tracked as external snapshot scaffolds only. They are not registered in the runtime catalog until `CnEquitySnapshotPipelines` publishes a contract and promotion evidence.

## Current lane policy

- 每条市场线只保留一个最强版本做后续评审。
- 如果该版本仍明显不如当前 live 主轨，就不要为了“有候选”保留多个弱版本，直接重做这条线。
- 现在更适合保留的方向是：
  - 行业 ETF：`cn_industry_etf_rotation_aggressive`
  - 创业板：`cn_chinext_tactical_rotation`
  - 科创板：先留 research，等独立证据出来再定
  - snapshot 个股：`cn_dividend_quality_snapshot` 先降到 research；它现在更像底仓/防守研究，不该算 live
  - 组合轨：`cn_equity_combo` 也先降到 research，等底层 legs 重新过线再评审
