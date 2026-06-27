# cn_dividend_quality_snapshot 历史 Proxy 回测（P3.5，2026-06-27）

> 投资有风险。本文为工程与研究记录，不构成投资建议。

## 1. 目的

为防守轨 `cn_dividend_quality_snapshot` 提供首版历史证据，与 510300 买入持有对比，支撑双轨配置决策。

## 2. 方法

```bash
cd CnEquityStrategies
PYTHONPATH=src:../QuantPlatformKit/src:../CnEquitySnapshotPipelines/src \
  python3 scripts/research_cn_dividend_quality_snapshot_proxy_backtest.py \
  --start 2021-01-01 --end 2026-06-27 \
  --json-output /tmp/cn_dividend_proxy.json
```

| 项 | 设定 |
|---|---|
| Universe | AkShare staging 8 股 + `510300` safe haven |
| Factor 面板 | 每月末 point-in-time 价格/财务/分红；fhps 用最新可用表 |
| 模拟 | T+1、100 股、涨跌停、万三佣金、2% 现金预留、月频 |
| 持仓 | top4（小 universe 适配） |

## 3. 初步结果（2021-01 ~ 2026-06）

| 方案 | 年化 | 最大回撤 | 总收益 |
|---|---:|---:|---:|
| 红利 quality | **2.81%** | -29.39% | +15.72% |
| 510300 B&H | 2.60% | -30.22% | +14.45% |

| 阶段 | 红利 quality | 510300 |
|---|---:|---:|
| 2021–2022 | -13.84% | -15.76% |
| 2023–2026 | +34.32% | +35.87% |

## 4. 解读

1. **staging 小样本下**，红利 quality 略优于 510300，但差距很小（年化 +0.2%），不足以证明双轨进攻价值。
2. 2021–2022 熊市两者均亏损；2023–2026 修复期**跑平略输**宽基。
3. 与行业轮动主轨（2021–2026 年化 ~13.8%）相比，防守轨在本设定下**不能替代**进攻敞口。

## 5. 已知局限（evidence gate 未过）

- Universe 仅 8 股，非全市场红利池
- fhps 未完全 point-in-time 按报告期选取
- 需扩展 `CnEquitySnapshotPipelines` 历史 builder + 更大 universe 后再 promotion

## 6. 下一步

1. Pipeline 增加 `as_of` 截断的 fhps/财报选取
2. 扩大 universe（中证红利/高股息成分）
3. 双轨组合 proxy（如 70% 行业轮动 + 30% 红利 quality）
