# CnEquityStrategies

[Chinese README](README.zh-CN.md)

> Investing involves risk. This project does not provide investment advice and is for education, research, and engineering review only.

## What this repository is

`CnEquityStrategies` is the A-share equity strategy package for QuantStrategyLab. It contains reusable strategy implementations, manifests, catalog metadata, and runtime adapters for CN-capable platform repositories.

This repository is a strategy layer, not a broker or deployment layer. It does not store broker credentials, submit orders by itself, publish snapshot artifacts, or decide whether a profile is safe for live trading without external evidence.

## Current runtime surface

### Direct runtime strategies

These profiles use platform-provided `market_history` and do not require a separate snapshot artifact before the strategy entrypoint can produce target weights.

| Profile | Name | Input | Benchmark | Current role |
| --- | --- | --- | --- | --- |
| `cn_index_etf_tactical_rotation` | CN Index ETF Tactical Rotation | `market_history` | `510300` | A-share ETF tactical rotation with CSI300 benchmark risk-off defensive switching. |

### Planned snapshot-backed strategy

The following profile is planned but not yet implemented in this repository. `CnEquitySnapshotPipelines` will own the artifact contract when it is promoted.

| Profile | Name | Input | Benchmark | Current role |
| --- | --- | --- | --- | --- |
| `cn_dividend_low_vol_quality_snapshot` | CN Dividend Low-Vol Quality Snapshot | `feature_snapshot` + manifest | `510300` | Planned A-share single-name selector; scaffold only. |

## Performance and evidence boundary

The research numbers in this repository are review evidence, not return promises. Before enabling or changing any live profile, rerun the relevant research/readiness commands and review short, medium, and long windows where applicable:

- return and benchmark-relative return
- maximum drawdown and drawdown stability
- turnover, costs, lot-size (100-share lots), slippage, suspension, and limit-up/limit-down behavior
- data freshness and artifact version
- broker dry-run order preview, notification logs, rollout controls, and operator approval

If evidence is stale, incomplete, or the profile is not returned by `get_runtime_enabled_profiles()`, keep it out of live runtime settings.

## Quick start

```bash
python -m pip install -e '.[test]'
python -m pytest -q
```

Local smoke coverage for the ETF rotation path:

```bash
python scripts/smoke_cn_index_etf_tactical_rotation_dry_run.py --json
```

## How this connects to execution

Platform repositories consume this package through strategy loaders and runtime metadata. They own broker credentials, market-data access, account state, dry-run/live switches, order submission, notifications, deployment settings, and rollback controls.

The intended A-share runtime platform is:

- `QmtPlatform` (miniQMT / QMT execution layer; planned)

## Deploy safely

1. Keep broker credentials and account identifiers outside Git.
2. Use platform repositories for dry-run, paper, or live execution switches.
3. Confirm strategy evidence and platform dry-run output before enabling scheduled execution.
4. Review generated orders, notifications, artifact URIs, and rollback settings.
5. Start with small staged exposure and keep kill-switch procedures documented in the platform repository.

## Repository layout

- `src/`: strategy implementations, manifests, catalog metadata, and runtime adapters.
- `tests/`: unit, contract, and regression tests.
- `docs/`: integration notes and strategy research.
- `scripts/`: local research and smoke helpers.

## Useful docs

- [`docs/platform_integration.md`](docs/platform_integration.md)
- [`docs/research/cn_index_etf_tactical_rotation.md`](docs/research/cn_index_etf_tactical_rotation.md)

## Safety and contribution notes

- Do not commit secrets, tokens, cookies, broker credentials, account identifiers, or private order data.
- Keep behavior changes small and include tests or reproducible evidence commands.
- Do not promote a research profile into live runtime settings without the documented evidence gates.

## License

See [LICENSE](LICENSE).
