# A 股 ETF 策略 Proxy 回测验证（2026-06-27）

> 投资有风险。本文为工程验证记录，不构成投资建议。

## 数据与方法

- **数据源**：AkShare `fund_etf_hist_em`（前复权），2021-01-04 ~ 2026-06-26
- **模拟器**：`cn_equity_strategies.backtest.proxy_simulator`（T+1 执行、100 股整手、万三佣金、ETF ±10% 涨跌停、2% 现金预留）
- **调仓**：月末信号，次一交易日收盘成交
- **复现**：

```bash
cd CnEquityStrategies
pip install -e '.[test]' akshare
PYTHONPATH=src python3 scripts/research_cn_strategy_validation.py --json-output /tmp/cn_strategy_validation.json
```

## 全样本对比（2021-01 ~ 2026-06）

| 排名 | 策略 | Total Return | Ann. Return | Max DD | 说明 |
| --- | --- | ---: | ---: | ---: | --- |
| 1 | equal_weight_offensive | 30.79% | 5.23% | **-39.26%** | 进攻池等权，高收益高回撤 |
| 2 | no_risk_off | 22.14% | 3.87% | -18.72% | 去掉 MA200 risk-off |
| 3 | **cn_index_etf_tactical_rotation** | **16.97%** | **3.02%** | **-11.68%** | **当前策略** |
| 4 | defensive_blend | 13.57% | 2.45% | -1.04% | 货基+国债 ETF |
| 5 | benchmark_510300 | 8.90% | 1.63% | -36.55% | 沪深300 买入持有 |
| 6 | naked_momentum | -1.00% | -0.19% | -24.09% | 裸动量 top2 |

## 分年观察

| 年份 | 当前策略 | 510300 | 等权进攻 | 裸动量 |
| --- | ---: | ---: | ---: | ---: |
| 2022 | +1.90% | -21.26% | -22.46% | -18.37% |
| 2023 | -0.05% | -10.22% | -5.30% | +8.19% |
| 2024 | -5.17% | +18.11% | +14.99% | +0.11% |
| 2025 | +16.79% | +21.03% | +34.79% | +10.38% |
| 2026 YTD | +3.45% | +5.87% | +17.59% | +3.11% |

## 结论与组织决策

### 保留 `cn_index_etf_tactical_rotation`（进攻/轮动轨）

1. **全样本跑赢 510300**（16.97% vs 8.90%），**最大回撤显著更低**（-11.68% vs -36.55%）。
2. **裸动量对照亏损**（-1.00%），验证 MA200 risk-off、趋势过滤、逆波加权等风控组件的必要性。
3. 2024–2025 牛市阶段跑输基准/等权，符合「控回撤、降波动」设计目标；2022 熊市显著优于基准。
4. **不建议**换成等权进攻或裸动量等社区「高收益」方案作为个人中长线主力——回撤过大。

### 保留 `cn_dividend_quality_snapshot`（防守/底仓轨）

- 本次仅完成 ETF 轨 proxy 验证；**红利质量 snapshot 需历史 factor CSV 序列**才能做同等回测（依赖 `CnEquitySnapshotPipelines` staging 历史）。
- 防御 ETF 对照（13.57% / MDD -1.04%）支持「低波底仓 + 轮动进攻」双轨架构合理性。

### 暂不切换至其他主流策略

| 社区热门方案 | 本次结论 |
| --- | --- |
| 小市值 + ETF 双核 | 未测；注册制后尾部风险高，维持 research scaffold |
| 纯等权 ETF 进攻 | 收益高但 MDD -39%，不适合作为唯一主力 |
| 裸动量轮动 | 全样本亏损，否决 |
| 纯 510300 持有 | 可作为 benchmark，但回撤与夏普均劣于当前策略 |

### 下一步（仍不做 live）

1. 构建 `cn_dividend_quality_snapshot` 历史 snapshot 回测（P3.5）。
2. 双轨组合回测：50/50 或 risk-off 动态切换 dividend + rotation。
3. 参数敏感性：momentum 窗口、top_n、target_vol。
