# A 股策略 Promotion 路线图（2026-06-28）

> 配套代码：`industry_etf_rotation_presets.py`（checklist / preset）、`backtest/promotion_gate.py`（自动 gate）

---

## 0. 策略架构：A 股 vs 美股 vs Snapshot（你问的分层）

**不是「ETF 轮动 vs Snapshot」拿来和美股对比**——美股是 **另一个 domain + 另一套 Platform**，和 A 股 QMT 并列，不在同一策略池里。

```
QuantRuntimeSettings（切换控制台）
├── us_equity domain → IBKR / Schwab / LongBridge / Firstrade
│   └── UsEquityStrategies：tqqq_growth_income、soxl…（美股 live）
│
└── cn_equity domain → QMT（当前仅 dry-run）
    └── CnEquityStrategies
        ├── market_history 直驱（「普通 A 股」runtime）
        │   └── cn_industry_etf_rotation ← 生产默认，14 行业 ETF 动量
        ├── feature_snapshot 快照（「A 股 Snapshot」runtime）
        │   └── cn_dividend_quality_snapshot ← Pipeline 因子 CSV + manifest
        └── research_backtest_only（回测/研究，不进切换页默认）
            ├── cn_industry_etf_rotation_aggressive（ETF vol25%）
            ├── cn_index_etf_tactical_rotation（legacy）
            ├── cross-section 个股动量 proxy（CSI500 宽池）
            └── 固定 8 股主题 sleeve proxy
```

| 类型 | Profile 示例 | 输入 | 是否需要 Pipeline | 与美股关系 |
|---|---|---|---|---|
| **A 股直驱（普通）** | `cn_industry_etf_rotation` | `market_history`（日 K CSV） | 否 | 无；美股另有一套 |
| **A 股 Snapshot** | `cn_dividend_quality_snapshot` | `feature_snapshot` | **是**（CnEquitySnapshotPipelines） | 无 |
| **美股** | `tqqq_growth_income` 等 | 各 Platform 自有 | 否（UsEquity 域） | **独立 domain** |
| **研究 proxy** | CSI500 个股动量、双轨 70/30 | 脚本 + AkShare | 红利腿用 Pipeline；ETF/动量腿不用 | 无 |

**对照关系（正确理解）：**

- **行业 ETF 轮动** = A 股 **market_history 直驱** 的生产主轨（类似「只喂行情就能跑」的普通策略）。
- **红利 quality** = A 股 **snapshot 轨**，必须先跑 Pipeline 产出因子快照，再喂给策略。
- **CSI500 个股动量** = 研究中的 **第三条线**，输入方式仍像 ETF（行情驱动），但 **尚未注册 runtime profile**；和 Snapshot 无关，也和美股无关。
- **双轨 70/30** = research 里把 **直驱 ETF 腿 + snapshot 红利腿** 收益加权；不是单一 profile。

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

### 1.4 落地步骤（optional_target — **已完成 2026-06-28**）

- [x] catalog 保留 `research_backtest_only`；QMT allowlist 通过 `get_qmt_rollout_allowlist()` 显式加入 aggressive
- [x] `runtime_adapters.py` aggressive adapter
- [x] `QuantRuntimeSettings/.../industry_etf_aggressive_dry_run.example.json`
- [x] 控制台 strategy-profiles + account-options + KV sync（PR #104，deploy run 28301083243）
- [x] `QmtPlatform/scripts/smoke_cn_industry_etf_rotation_aggressive_dry_run_e2e.py`（PR #8）
- [x] `QmtPlatform` pin → `de6c760`（PR #8）

**PR：** CnEquityStrategies #8 | QmtPlatform #8 | QuantRuntimeSettings #104

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
  --json-output docs/research/cn_momentum_stock_csi500_full_20260628.json
```

### 3.7 全量 CSI500 回测（2021–2026，2026-06-28）

**设置：** 500 成分候选，**398** 只在 `2021-01-01` 有足够历史；csindex 成分为最新表（非 PIT）。

| Variant | 年化 | MDD | 总收益 | OOS 2024–26 |
|---|---:|---:|---:|---:|
| **CSI500 top5 + CSI300 risk-off** | **14.39%** | **-25.66%** | **+99.1%** | +89.2%（≈ ETF +89.1%） |
| CSI500 top5 vol20% | 3.92% | -36.10% | +21.8% | fail |
| CSI500 top5 vol18% low gross | 3.87% | -31.77% | +21.5% | fail |
| ETF conservative v1（对照） | 13.79% | -15.42% | +80.0% | +89.1% |
| 固定 8 股 top3 thematic（旧） | ~28% | ~-40% | +380% | — |

**解读**

- **Risk-off 版** 在全量 CSI500 下 OOS 与 ETF conservative **几乎打平**（+89% vs +89%），全样本总收益更高（+99% vs +80%），但 MDD 仍 **-26%**（gate 要求 ≥-25%），熊市 2021–22 仍 **-17% vs ETF -3.5%**。
- 纯 vol20% 无 risk-off 在全池上 **远差于 ETF**（MDD -36%）——个股宽池必须带 benchmark 防御。
- 相对固定 8 股主题：cross-section + risk-off **显著降低回撤**，OOS 收益不再依赖叙事集中。
- 仍 **不过** `STOCK_MOMENTUM_PROMOTION_GATE`（MDD / 熊市约束）；暂不上 live。

JSON：`docs/research/cn_momentum_stock_csi500_full_20260628.json`

### 3.8 CSI500 risk-off 调参矩阵（2021–2026，2026-06-28）

**命令：**

```bash
PYTHONPATH=src:scripts python3 scripts/research_cn_momentum_stock_rotation_proxy.py \
  --suite csi500_riskoff \
  --json-output docs/research/cn_momentum_csi500_riskoff_tuning_20260628.json
```

**设置：** 432/500 只在 2021 初可交易；9 个 risk-off 变体共享一次行情下载。

| Preset | 年化 | MDD | 总收益 | OOS 2024–26 | 2021–22 熊市 |
|---|---:|---:|---:|---:|---:|
| **vol15% gross75%（MDD 优选）** | **15.19%** | **-16.47%** | **+100.5%** | +62.5% | **-2.99%** |
| vol16% gross80% | 16.03% | -17.50% | +107.8% | +66.6% | -3.2% |
| vol18% gross85% | 17.87% | -18.74% | +124.6% | +74.7% | -3.5% |
| vol18 MA120 risk-off | 20.34% | -21.60% | +148.7% | **+98.1%** | -5.0% |
| vol20% baseline risk-off | 20.21% | -21.49% | +147.4% | +89.3% | -4.3% |
| ETF conservative（对照） | 13.79% | -15.42% | +80.0% | +89.1% | -3.5% |

**结论**

- **压 MDD 目标达成：** `vol15 + gross75%` 将 MDD 拉到 **-16.5%**（接近 ETF -15.4%），熊市 **-2.99% 略优于 ETF**。
- **OOS 代价：** 同一 preset OOS 仅 +62.5%（比 ETF +89% 低 ~27pp）——典型 **收益/防御 trade-off**。
- **偏 OOS 的 risk-off：** `MA120` 或 `vol20` 维持 OOS ~+89–98%，但 MDD 仍在 **-21%** 量级。
- **仍无 variant 过完整** `STOCK_MOMENTUM_PROMOTION_GATE`（OOS lift + MDD 双重要求同时满足很难）。
- **研究默认 risk-off 候选：** `CSI500_RISKOFF_MDD_OPTIMIZED_PRESET_KEY` → `momentum_csi500_top5_vol15_gross75_riskoff`。

JSON：`docs/research/cn_momentum_csi500_riskoff_tuning_20260628.json`

### 3.9 MA120 vol 抬年化调参（research only，2026-06-28）

**脚本：** `research_cn_ma120_vol_and_combo_scan.py`  
**JSON：** `docs/research/cn_ma120_vol_and_combo_scan_20260628.json`  
**Phase 2 计划：** `docs/research/cn_ma120_vol25_stock_sleeve_research_plan_20260628.md`

| Preset | 年化 | MDD | OOS 2024+ |
|---|---:|---:|---:|
| vol18 MA120 | 20.3% | -21.6% | +98% |
| vol20 MA120 | 22.0% | -22.2% | +106% |
| vol22 MA120 | 23.5% | -22.7% | +111% |
| **vol25 MA120** | **25.2%** | **-23.5%** | **+118%** |

**结论（MDD 预算 -35%）：** vol25 MA120 为 research 最高年化档；100% 单腿优于 ETF blend。Live 已落地 aggressive ETF optional target；个股 sleeve 继续 Phase 2（PIT、单票 cap、gate 放宽评估）。

### 3.5 70/30 组合：ETF conservative + vol15 risk-off 个股

**脚本：** `research_cn_etf_momentum_stock_combo_proxy_backtest.py`  
**Preset：** `DUAL_TRACK_COMBO_PRESETS["etf_vol15_riskoff_stock_70_30"]`

```bash
cd CnEquityStrategies
PYTHONPATH=src:scripts:../QuantPlatformKit/src \
  python3 scripts/research_cn_etf_momentum_stock_combo_proxy_backtest.py \
  --json-output docs/research/cn_etf_momentum_stock_combo_20260628.json
```

**2021-01-01 ~ 2026-06-27（return-level 70/30 blend）**

| 腿 | 年化 | 总收益 | MDD | OOS 2024+ | 熊市 2021–22 |
|---|---:|---:|---:|---:|---:|
| **70/30 组合** | **14.87%** | **+87.9%** | **-13.88%** | +81.9% | **-3.21%** |
| ETF conservative（70% 权重来源） | 13.79% | +80.0% | -15.42% | +89.1% | -3.46% |
| vol15 risk-off 个股（30% 权重来源） | 15.19% | +100.5% | -16.47% | +62.5% | -2.99% |
| 70/30 ETF + expanded 红利（对照） | 16.22% | — | -15.37% | — | — |

**结论**

- **MDD 优于两腿单独：** 组合 **-13.9%** 低于 ETF（-15.4%）与个股（-16.5%），说明低相关 sleeve 在 return blend 层有效分散。
- **年化介于两腿之间：** 14.9% > 纯 ETF 13.8%，但低于纯个股 15.2% 与红利双轨 16.2%。
- **OOS 仍偏 ETF 侧：** 2024+ 组合 +82% 介于 ETF +89% 与个股 +63% 之间——**未同时 beat 纯 ETF OOS**。
- **熊市略优于纯 ETF：** -3.21% vs -3.46%（个股腿 -2.99% 拉低组合）。
- **相对红利双轨：** 换 30% 个股 sleeve 后 MDD 略优（-13.9% vs -15.4%），年化略低（14.9% vs 16.2%）——**防御略强、收益略弱** 的 trade-off。

JSON：`docs/research/cn_etf_momentum_stock_combo_20260628.json`

### 3.6 更严格 promotion gate（个股）

- **Cross-section 动量：** `STOCK_MOMENTUM_PROMOTION_GATE`（MDD ≥ -25%，熊市劣化 ≤10pp vs ETF）
- **固定主题 sleeve：** `STOCK_THEMATIC_PROMOTION_GATE`（MDD ≥ -28%，熊市劣化 ≤15pp）

即使 OOS 收益极高，MDD -40% 或熊市 -38% 仍会被 gate 拒绝。

### 3.7 固定主题轨运行命令

```bash
cd CnEquityStrategies
PYTHONPATH=src:scripts python3 scripts/research_cn_thematic_stock_rotation_proxy.py --suite stock
PYTHONPATH=src:scripts python3 scripts/research_cn_thematic_stock_rotation_proxy.py --suite stock_risk
```

### 3.8 后续参数方向（待编码）

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
| P2b | **70/30 ETF + vol15 stock** 已验证 proxy；可对比 50/50、40/60 权重扫描 | MDD ~-14% | 低 |
| P3 | 个股 sleeve 仅在有 preset 过 stock gate 后讨论 profile | 高收益 | 高 |

---

## 5. 相关文件

| 文件 | 用途 |
|---|---|
| `industry_etf_rotation_presets.py` | 全部 preset + checklist 常量 |
| `backtest/promotion_gate.py` | 可配置 gate 评估 |
| `research_cn_thematic_stock_rotation_proxy.py` | 个股矩阵 |
| `research_cn_dual_track_combo_proxy_backtest.py` | 双轨 proxy（ETF + 红利） |
| `research_cn_etf_momentum_stock_combo_proxy_backtest.py` | ETF + CSI500 动量 risk-off 组合 proxy |
| `docs/research/cn_industry_etf_rotation_design_20260627.md` | §12–§14 回测证据 |
