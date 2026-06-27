# A 股策略 Promotion 路线图（2026-06-28）

> 配套代码：`industry_etf_rotation_presets.py`（checklist / preset）、`backtest/promotion_gate.py`（自动 gate）

---

## 1. Aggressive vol25% → Live 候选评审

**目标 profile：** `cn_industry_etf_rotation_aggressive`  
**基线：** `cn_industry_etf_rotation`（conservative v1）  
**Preset：** `full_pool_vol25_monthly` / `AGGRESSIVE_V1_PRESET`

### 1.1 自动化 gate（已通过）

| 检查项 | 阈值 | 结果 |
|---|---|---|
| OOS 2024–2026 total return lift | ≥ +5pp vs conservative | **+5.4pp** ✅ |
| 全样本 MDD 回归 | ≤ 5pp 劣化 | **0pp** ✅ |

### 1.2 人工评审清单（`AGGRESSIVE_PROMOTION_REVIEW_CHECKLIST`）

| ID | 状态 | 说明 |
|---|---|---|
| `oos_lift` | pass | 矩阵回测 2026-06-27 |
| `mdd_parity` | pass | MDD -15.42% 相同 |
| `bear_2021_2022` | **review** | 需确认熊市子区间未显著劣于 conservative |
| `live_dry_run` | pass | Qmt conservative e2e 已通；aggressive 同 entrypoint 形态 |
| `runtime_policy` | **pending** | 见下方 rollout 选项 |
| `pin_and_docs` | pass | PR #7 已合入 |

### 1.3 推荐 rollout（三选一）

1. **推荐：`optional_target`** — 在 QuantRuntimeSettings 增加第二个 QMT target（`STRATEGY_PROFILE=cn_industry_etf_rotation_aggressive`），**不替换**默认 conservative。
2. `promote_default` — 直接把平台默认改为 aggressive（+1pp 年化，风险中等，需你明确批准）。
3. `stay_research` — 维持 `research_backtest_only`，等双轨 combo runtime 验证后再议。

### 1.4 落地步骤（若选 optional_target）

- [ ] `catalog.status` 改为 `runtime_enabled`（或保留 research 但 QMT allowlist 显式加入）
- [ ] `runtime_adapters.py` 为 aggressive 注册 adapter（与 conservative 相同 `market_history`）
- [ ] `QuantRuntimeSettings/examples/targets/qmt/industry_etf_aggressive_dry_run.example.json`
- [ ] 控制台 strategy catalog 增加 aggressive 条目
- [ ] 跑 `smoke_cn_industry_etf_rotation_dry_run_e2e.py` 改 profile 验证

---

## 2. 双轨 70/30 Combo → Runtime 设计（未实现）

**目标 profile（设计）：** `cn_dual_track_combo`  
**Preset 规格：** `DUAL_TRACK_COMBO_PRESETS`

### 2.1 当前 research 形态

- 脚本：`research_cn_dual_track_combo_proxy_backtest.py`
- **return-level blend**（70% 行业 + 30% 红利），非统一多资产账户模拟
- expanded 红利腿依赖 Pipeline `--universe-mode expanded`

### 2.2 候选 preset

| Key | 行业腿 | 红利腿 | 证据（proxy） |
|---|---|---|---|
| `conservative_expanded_70_30` | vol 20% | expanded | ann 16.22%, MDD -15.37% |
| `aggressive_expanded_70_30` | vol 25% | expanded | ann 12.95%, MDD -15.37%, total +74% |

### 2.3 阻塞项（`DUAL_TRACK_PROMOTION_REVIEW_CHECKLIST`）

1. **统一组合模拟器** — 两腿共用交易日历、统一 rebalance、真实权重约束（非序列加权）
2. **红利 PIT** — fhps/财报按 `as_of` 截断（Pipeline 待做）
3. **Runtime 形态** — 单 profile 输出 combined weights，或 orchestrator 调两个 entrypoint
4. **Evidence gate** — 组合 MDD ≤ 行业腿 MDD + 2pp（2017+ 长样本）

### 2.4 建议 runtime 形状（第一版）

```json
{
  "profile": "cn_dual_track_combo",
  "legs": [
    {"profile": "cn_industry_etf_rotation", "weight": 0.70},
    {"profile": "cn_dividend_quality_snapshot", "weight": 0.30}
  ],
  "dividend_universe_mode": "expanded"
}
```

**Phase 1：** research-only orchestrator script（已有 proxy）  
**Phase 2：** catalog profile + QMT target（需 snapshot 生产链路）  
**Phase 3：** 权重可配置（60/40、80/20 sensitivity）

---

## 3. 个股光模块/算力轨 — 参数优化矩阵

**脚本：** `research_cn_thematic_stock_rotation_proxy.py`  
**Baseline presets：** `STOCK_THEMATIC_PRESETS`  
**Risk-control presets：** `STOCK_THEMATIC_RISK_PRESETS`（新增）

### 3.1 两条 research 轨（勿混淆）

| 轨道 | 脚本 / preset | Universe | 选股 |
|---|---|---|---|
| **A. 固定主题 sleeve** | `research_cn_thematic_stock_rotation_proxy.py` / `STOCK_THEMATIC_*` | 手工 8 只光模块/算力 | 池内动量 top2/3 |
| **B. Cross-section 动量** | `research_cn_momentum_stock_rotation_proxy.py` / `STOCK_MOMENTUM_CROSS_SECTION_*` | **CSI500（默认）** / CSI1000 / 流动性 Top300 | **宽池内动量 top-N** |

**默认建议：** 先看 **B 轨 CSI500**（比全 A 稳、比 8 只主题广）；再对照 A 轨看「叙事集中」的增量风险。

### 3.2 问题诊断（baseline 固定主题 top3 monthly）

| 指标 | 个股 top3 | ETF conservative |
|---|---:|---:|
| 年化 | 28.2% | 13.8% |
| MDD | **-39.5%** | -15.4% |
| 2021–2022 熊市 | **~-38%** | ~-3.5% |

根因：top-N 集中、无 benchmark 防御、vol25% 对单票波动不足、池子非 PIT。

### 3.3 新增 risk-control 参数（固定主题轨，`STOCK_THEMATIC_RISK_PRESETS`）

| Preset key | 设计意图 | 主要参数 |
|---|---|---|
| `stock_optical_vol20_top2_monthly` | 降低 vol target | vol **20%**, top2 |
| `stock_optical_vol18_top2_low_gross` | 强制留现金 | vol **18%**, max_gross **75%** |
| `stock_optical_top2_tight_corr` | 降低同质化集中 | max_pair_corr **0.70** |
| `stock_optical_top2_benchmark_riskoff` | 熊市切 CSI300 | MA200 risk-off, 510300 |
| `stock_optical_hybrid_etf_sleeve` | 个股+宽基/半导体 ETF 混合池 | 510300+512760, top3, risk-off |
| `stock_optical_top2_min_momentum` | 过滤弱动量 | min_momentum **5%** |

### 3.4 Cross-section 动量 preset（`STOCK_MOMENTUM_CROSS_SECTION_PRESETS`）

| Preset key | Universe | top-N | 备注 |
|---|---|---:|---|
| `momentum_csi500_top5_vol20_monthly` | CSI500 | 5 | **默认首选** |
| `momentum_csi500_top5_vol20_riskoff` | CSI500 | 5 | + CSI300 MA200 防御 |
| `momentum_csi1000_top10_vol20_monthly` | CSI1000 | 10 | 更广中小盘 |
| `momentum_liquid_top300_top5_vol20_monthly` | 成交额 Top300 | 5 | 流动性快照（非 PIT） |
| `momentum_csi500_top5_vol18_low_gross` | CSI500 | 5 | vol18% + gross 80% |

```bash
# 默认 CSI500 cross-section（推荐起手）
PYTHONPATH=src:scripts python3 scripts/research_cn_momentum_stock_rotation_proxy.py

# 三种 universe 全跑 + 与固定主题 8 股对照
PYTHONPATH=src:scripts python3 scripts/research_cn_momentum_stock_rotation_proxy.py \
  --universe-mode all --track both \
  --json-output docs/research/cn_momentum_stock_matrix_20260628.json
```

### 3.5 更严格 promotion gate（个股）

- **Cross-section 动量：** `STOCK_MOMENTUM_PROMOTION_GATE`（MDD ≥ -25%，熊市劣化 ≤10pp vs ETF）

- **固定主题 sleeve：** `STOCK_THEMATIC_PROMOTION_GATE`（MDD ≥ -28%，熊市劣化 ≤15pp）

| 约束 | 阈值 |
|---|---|
| `max_mdd_absolute` | MDD ≥ **-28%**（不得深于 -28%） |
| `max_bear_total_return_regression` | 2021–2022 总收益不得比 ETF baseline 差 **>15pp** |

**说明：** 即使 OOS 收益极高，MDD -40% 或熊市 -38% 仍会被 gate 拒绝。

### 3.6 固定主题轨运行命令

```bash
cd CnEquityStrategies

# baseline 个股矩阵
PYTHONPATH=src:scripts python3 scripts/research_cn_thematic_stock_rotation_proxy.py --suite stock

# 新增 risk-control 矩阵
PYTHONPATH=src:scripts python3 scripts/research_cn_thematic_stock_rotation_proxy.py --suite stock_risk

# 或统一入口
PYTHONPATH=src:scripts python3 scripts/research_cn_industry_etf_rotation_aggressive_matrix.py --suite stock_risk
```

### 3.5 后续参数方向（待编码）

| 方向 | 参数 | 预期效果 |
|---|---|---|
| 动态 vol scaling | 高 VIX/广度 proxy 时 vol target ×0.8 | 降熊市回撤 |
| 单票 weight cap | max_single_name_weight 15% | 降集中风险 |
| Trailing stop | 组合层 -12% 月内降 gross | 截断主题崩盘 |
| PIT 池子 | Pipeline 按 as_of 重建 optical universe | 降幸存者偏差 |
| 与 ETF 腿捆绑 | 70% conservative ETF + 30% stock sleeve | 类似双轨思路 |

---

## 4. 优先级建议

| 优先级 | 动作 | 预期收益 | 风险 |
|---|---|---|---|
| P0 | Aggressive **optional QMT target** | +1pp 年化（ETF） | 低 |
| P1 | 跑 **stock_risk** 矩阵，找 MDD/bear 改善最大的 preset | 可能保留 15–20% 年化同时 MDD → -28% | 中 |
| P2 | 双轨 combo Phase 1→2（PIT + unified sim） | 组合年化 ~16% | 中 |
| P3 | 个股 sleeve 仅在有 preset 过 stock gate 后讨论 profile | 高收益 | 高 |

---

## 5. 相关文件

| 文件 | 用途 |
|---|---|
| `industry_etf_rotation_presets.py` | 全部 preset + checklist 常量 |
| `backtest/promotion_gate.py` | 可配置 gate 评估 |
| `research_cn_thematic_stock_rotation_proxy.py` | 个股矩阵 |
| `research_cn_dual_track_combo_proxy_backtest.py` | 双轨 proxy |
| `docs/research/cn_industry_etf_rotation_design_20260627.md` | §12–§14 回测证据 |
