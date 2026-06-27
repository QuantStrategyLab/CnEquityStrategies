# CnEquityStrategies

[English README](README.md)

> 投资有风险。本项目不构成投资建议，仅用于学习、研究和工程审阅。

## 这个仓库是什么

`CnEquityStrategies` 是 QuantStrategyLab 的 A 股策略包，提供 A 股策略实现、manifest、catalog metadata 和 runtime adapter，供支持 A 股的执行平台复用。

这是策略层，不是券商或部署层。本仓库不保存券商凭据，不自行下单，不发布 snapshot artifact，也不能在缺少外部证据的情况下决定某个 profile 是否适合 live。

## 当前 runtime 面

### 普通 runtime 策略

这些 profile 使用平台提供的 `market_history`，不需要先生成单独的 snapshot artifact，也能通过策略入口生成目标权重。

| Profile | 名称 | 输入 | 基准 | 当前角色 |
| --- | --- | --- | --- | --- |
| `cn_industry_etf_rotation` | CN Industry ETF Rotation | `market_history` | `510300` | **主轨**：纯 A 股行业 ETF 动量轮动（top5 / vol20% / 纯动量）。 |
| `cn_dividend_quality_snapshot` | CN Dividend Quality Snapshot | `feature_snapshot` + manifest | `510300` | **防守轨**：红利+质量选股，广度控制防御敞口。 |
| `cn_index_etf_tactical_rotation` | CN Index ETF Tactical Rotation | `market_history` | `510300` | Legacy 全球扩池轮动；**research_backtest_only**。 |

### 计划中的 snapshot-backed 策略

| Profile | 名称 | 输入 | 基准 | 当前角色 |
| --- | --- | --- | --- | --- |
| `cn_small_cap_quality_snapshot` | CN Small-Cap Quality Snapshot | `feature_snapshot` + manifest | `510300` | Research scaffold，尚未 promotion。 |

## 表现和证据边界

本仓库里的研究数字是 review 证据，不是收益承诺。启用或调整 live profile 前，需要重新运行相关研究或 readiness 命令，并在适用场景下检查短、中、长周期：

- 收益和相对基准收益
- 最大回撤和回撤稳定性
- 换手、费用、整手（100 股）、滑点、停牌、涨跌停表现
- 数据新鲜度和 artifact 版本
- 券商 dry-run order preview、通知日志、上线控制和人工审批

如果证据过期、不完整，或者 profile 不在 `get_runtime_enabled_profiles()` 返回值里，就不要放进 live runtime settings。

## 快速开始

```bash
python -m pip install -e '.[test]'
python -m pytest -q
```

ETF 轮动路径的本地 smoke：

```bash
python scripts/smoke_cn_index_etf_tactical_rotation_dry_run.py --json
```

## 如何接到执行平台

执行平台通过 strategy loader 和 runtime metadata 消费本策略包。券商凭据、行情权限、账户状态、dry-run/live 开关、下单、通知、部署配置和回滚控制都属于平台仓库。

计划中的 A 股 runtime 平台：

- `QmtPlatform`（miniQMT / QMT 执行层；待建）

## 安全部署

1. 券商凭据和账户标识不要放进 Git。
2. dry-run、paper、live 开关放在平台仓库里控制。
3. 启用定时执行前，先确认策略证据和平台 dry-run 输出。
4. 检查生成订单、通知、artifact URI 和回滚设置。
5. 先小规模分阶段运行，并在平台仓库保留 kill switch 操作说明。

## 仓库结构

- `src/`：策略实现、manifest、catalog metadata、runtime adapter。
- `tests/`：单元测试、契约测试和回归测试。
- `docs/`：平台集成说明和策略研究。
- `scripts/`：本地研究和 smoke 辅助工具。

## 延伸文档

- [`docs/platform_integration.md`](docs/platform_integration.md)
- [`docs/research/cn_index_etf_tactical_rotation.md`](docs/research/cn_index_etf_tactical_rotation.md)

## 安全和贡献说明

- 不要提交密钥、token、Cookie、券商凭据、账户标识或私人订单数据。
- 行为改动尽量小，并附上测试或可复现证据命令。
- 没有通过文档化 evidence gate 前，不要把研究 profile 提升到 live runtime settings。

## 许可证

详见 [LICENSE](LICENSE)。
