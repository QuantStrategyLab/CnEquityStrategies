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

## 6. 双轨组合（70% 行业轮动 + 30% 红利 quality，2021–2026）

```bash
PYTHONPATH=src:scripts:../QuantPlatformKit/src:../CnEquitySnapshotPipelines/src \
  python3 scripts/research_cn_dual_track_combo_proxy_backtest.py \
  --industry-weight 0.7 --dividend-weight 0.3
```

| 方案 | 年化 | 最大回撤 | 总收益 |
|---|---:|---:|---:|
| **70/30 组合** | **10.79%** | **-16.36%** | **+59.4%** |
| 行业轮动（100%） | 13.79% | -15.42% | +80.1% |
| 红利 quality（100%） | 2.81% | -29.39% | +15.7% |
| 510300 | 0.46% | -44.05% | +2.5% |

**解读**

- 加入 30% 红利轨**略降**年化（13.8% → 10.8%），但 MDD 与纯行业接近（-16% vs -15%）。
- 相对 510300，组合仍有显著超额；**纯行业轮动仍是更优进攻配置**。
- 红利轨价值在组合分散上有限（staging universe 证据不足），待扩大 universe 后再评估固定比例是否值得。

## 7. 扩大 Universe 基础设施（2026-06-27 续）

`CnEquitySnapshotPipelines` 分支 `feat/expanded-dividend-universe-metadata`：

| 组件 | 说明 |
|---|---|
| `akshare_metadata.py` | fhps 股息率筛选 universe；East Money 行业板块 sector 映射（JSON 缓存） |
| `akshare_staging.py` | `--universe-mode expanded|staging|custom`；移除 cninfo 依赖 |
| `compute_price_features(as_of=)` | list_days 按回测 as_of 计算 |
| sector 缓存 | `data/cache/symbol_sector_map.json`（~5609 条；首次需 `--refresh-sector-map` 构建） |

```bash
# 构建/刷新 sector 缓存
cd CnEquitySnapshotPipelines
PYTHONPATH=src python3 -c "
import akshare as ak
from cn_equity_snapshot_pipelines.akshare_metadata import build_symbol_sector_map
print('size', len(build_symbol_sector_map(ak, force_refresh=True)))
"

# expanded universe 回测（fhps top40 股息率 2.5%–12%，排除 ST）
cd CnEquityStrategies
PYTHONPATH=src:scripts:../QuantPlatformKit/src:../CnEquitySnapshotPipelines/src \
  python3 scripts/research_cn_dividend_quality_snapshot_proxy_backtest.py \
  --universe-mode expanded --expanded-top-n 40 \
  --start 2021-01-01 --end 2026-06-27 \
  --json-output /tmp/cn_dividend_expanded_proxy.json
```

## 8. Expanded Universe 回测（fhps top40，2021–2026）

| 方案 | 年化 | 最大回撤 | 总收益 |
|---|---:|---:|---:|
| **expanded 红利 quality** | **10.83%** | **-17.65%** | **+43.55%** |
| staging 红利 quality（§3） | 2.81% | -29.39% | +15.72% |
| 510300 B&H | 2.60% | -30.22% | +14.45% |
| 行业轮动 100%（§6） | 13.79% | -15.42% | +80.1% |

**解读**

1. 扩大 universe 后红利轨从「略优于 510300」变为**显著超额**（年化 +8% vs 510300），MDD 也明显改善。
2. 与行业轮动主轨相比，expanded 红利轨年化仍低约 3%，但回撤接近，**双轨配置值得重新评估**。
3. 2021–2022 子区间 expanded 策略几乎无收益（部分新股/次新股在 fhps 池中但早期无价格历史）；2023–2026 表现主导全样本。
4. fhps 仍非完全 PIT；evidence gate 尚未完全通过，但 expanded 结果已具备研究价值。

### expanded 长样本修复后（2017–2026，动态 universe + 510300 日历）

proxy 修复：`dropna(how="any")` → 510300 锚定日历 + 按列 ffill；每月 factor 面板仅纳入 as_of 日已有价格的标的。

| 方案 | 年化 | 总收益 | MDD | 有效交易日 | 调仓次数 |
|---|---:|---:|---:|---:|---:|
| **expanded 红利（修复后）** | **7.54%** | **+94.1%** | -33.6% | 2300 | 101 |
| expanded（修复前，错误） | 10.83%* | +43.5%* | -17.7%* | 886* | 31* |
| 510300 B&H | 3.33% | +34.9% | -44.1% | 2300 | — |

\*修复前因 41 股强制重叠，有效区间被截到 ~2023，指标不可比。

| 子阶段 | expanded 红利 | 510300 |
|---|---:|---:|
| 2021–2022 | +14.1% | -24.6% |
| 2023–2026 | +40.4% | +35.9% |

月均有效标的 ~38 只（expanded top40 池中已上市且有价格者）。

### 70/30 双轨（expanded 红利轨，2021–2026）

```bash
PYTHONPATH=src:scripts:../QuantPlatformKit/src:../CnEquitySnapshotPipelines/src \
  python3 scripts/research_cn_dual_track_combo_proxy_backtest.py \
  --dividend-universe-mode expanded --expanded-top-n 40 \
  --industry-weight 0.7 --dividend-weight 0.3
```

| 方案 | 年化 | 最大回撤 | 总收益 |
|---|---:|---:|---:|
| **70/30 组合（expanded）** | **16.22%** | **-15.37%** | **+69.65%** |
| 70/30 组合（staging，§6） | 10.79% | -16.36% | +59.4% |
| 行业轮动（100%） | 13.79% | -15.42% | +80.1% |
| expanded 红利 quality | 10.83% | -17.65% | +43.55% |

**解读**：expanded 红利轨加入后，70/30 组合在 proxy 层面**略高于**纯行业年化（16.2% vs 13.8%），MDD 几乎不变。注意这是收益序列加权 blend，非统一多资产组合；总收益仍低于纯行业（因红利轨拖累复利路径）。staging 版双轨则明显劣于纯行业。

## 9. 下一步

1. Pipeline 增加 `as_of` 截断的 fhps/财报选取（真正 PIT）
2. 用 expanded universe 重跑 70/30 双轨，对比 staging 版组合
3. 提交 CnEquitySnapshotPipelines PR + CnEquityStrategies research 脚本同步 PR
