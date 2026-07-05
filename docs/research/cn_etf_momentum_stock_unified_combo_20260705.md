# A 股行业 ETF + 股票动量统一组合研究记录（2026-07-05）

> 投资有风险。本文为工程与研究记录，不构成投资建议。

## 现状

- 已把 `scripts/research_cn_etf_momentum_stock_combo_proxy_backtest.py` 补成支持 `--simulation-mode unified`。
- 统一组合目标：`cn_industry_etf_rotation` + `CSI500 momentum stock risk-off sleeve`。
- 现阶段仍有一条明显限制：**股票腿不是严格 PIT**，仍依赖最新成分与历史可交易性过滤。

## 已有证据

### return-level blend（已有落盘结果）

| 方案 | 年化 | 最大回撤 | Sharpe |
| --- | ---: | ---: | ---: |
| 行业 ETF live conservative | 13.79% | -15.42% | 0.89 |
| 股票动量 risk-off | 15.19% | -16.47% | 0.92 |
| 70/30 return-level blend | **14.87%** | **-13.88%** | **1.09** |

### 解释

- 70/30 组合在现有研究里已经比单独行业 ETF 更强。
- 但这还不是统一组合模拟，不能直接当 live 证据。

## 新增统一组合路径

建议复跑命令：

```bash
PYTHONPATH=src:scripts python3 scripts/research_cn_etf_momentum_stock_combo_proxy_backtest.py \
  --start 2021-01-01 --end 2026-06-27 \
  --simulation-mode unified \
  --json-output /tmp/cn_etf_momentum_stock_unified_combo.json
```

## 当前阻塞

本次尝试统一回测时，AkShare 拉取 ETF 历史数据被远端断开，暂时没有拿到新的统一组合数值。

## 结论

- `cn_industry_etf_rotation`：继续保留 live 主轨。
- `cn_dividend_quality_snapshot`：继续做防守/备用。
- `行业 ETF + 股票动量 30%`：继续研究，先过统一组合与 PIT 约束，再谈 live。
