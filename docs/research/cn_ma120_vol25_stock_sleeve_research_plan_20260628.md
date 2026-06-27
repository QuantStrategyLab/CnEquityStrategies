# CSI500 MA120 vol25 个股 sleeve — Research 回测与设计计划

**状态：** research_only（未进 QMT live rollout）  
**日期：** 2026-06-28  
**关联 preset：** `momentum_csi500_top5_vol25_ma120_riskoff`（`CSI500_MA120_RETURN_OPTIMIZED_PRESET_KEY`）

---

## 1. 定位（与已 live 配置的关系）

| 层级 | 配置 | 年化 | MDD | Live |
|---|---|---:|---:|---|
| QMT 主轨（默认） | `cn_industry_etf_rotation` conservative | 13.8% | -15.4% | ✅ |
| QMT optional | `cn_industry_etf_rotation_aggressive` vol25% | 14.8% | -15.4% | ✅ optional target |
| Snapshot 防御 | `cn_dividend_quality_snapshot` expanded | 7.7% | -23.8% | ✅ pipeline |
| **本计划** | CSI500 cross-section MA120 vol25% | **25.2%** | **-23.5%** | ❌ research |

**用户回撤预算：** -30% ~ -35% → vol25 MA120 在预算内，且为当前 research 最高年化档。

---

## 2. 已完成的回测证据

**脚本：** `scripts/research_cn_ma120_vol_and_combo_scan.py`  
**JSON：** `docs/research/cn_ma120_vol_and_combo_scan_20260628.json`

### 2.1 MA120 vol 调参（2021–2026）

| Preset | 年化 | MDD | OOS 2024+ | 熊市 2021–22 |
|---|---:|---:|---:|---:|
| vol18 MA120 | 20.3% | -21.6% | +98% | -5.2% |
| vol20 MA120 | 22.0% | -22.2% | +106% | -5.0% |
| vol22 MA120 | 23.5% | -22.7% | +111% | -4.9% |
| **vol25 MA120** | **25.2%** | **-23.5%** | **+118%** | **-4.6%** |

### 2.2 与 ETF 组合（return blend，research）

| 权重 | 年化 | MDD | 说明 |
|---|---:|---:|---|
| 100% vol25 MA120 | 25.2% | -23.5% | **单腿最优** |
| 30% ETF + 70% vol25 | 23.7% | -17.0% | 降 MDD，牺牲 ~1.5pp 年化 |
| 50% ETF + 50% vol25 | 21.0% | -15.7% | 接近 ETF MDD，年化仍高于纯 ETF |

**结论：** 抬年化目标下 **100% vol25 MA120** 为 research 默认；若要与 live ETF 腿做 paper 组合，优先试 **30/70 或 50/50**，不在 live 层默认。

---

## 3. 未过 Live 的原因（gate 与工程）

|  blocker | 现状 | Phase 2 要求 |
|---|---|---|
| catalog status | `research_backtest_only` | 需显式 promotion + 用户批准 |
| PIT 成分股 | 最新 csindex 表，非 as_of | Pipeline 按日重建 CSI500 池 |
| 单票集中度 | top5 等权 + vol scaling | 单票 cap 8–10%（core 参数） |
| 统一组合模拟 | 仅 return-level blend | 多资产 rebalance 模拟器 |
| promotion gate | OOS lift + MDD -25% 双重要求 | 用户 MDD -35% 时可放宽 research gate |

---

## 4. Phase 2 回测设计（下一步编码）

### P2.1 放宽 research gate（仅文档 + 评估脚本）

```python
STOCK_MOMENTUM_RETURN_FOCUSED_GATE = {
    **STOCK_MOMENTUM_PROMOTION_GATE,
    "max_mdd_absolute": -0.35,
    "min_oos_total_return_lift": 0.10,
}
```

对 `vol18/20/22/25 MA120` 重跑 `evaluate_promotion`，确认 vol25 在 -35% gate 下是否 PASS。

### P2.2 权重扫描（ETF aggressive + MA120 vol25）

扩展 `research_cn_ma120_vol_and_combo_scan.py`：

- industry_profile=`aggressive`（14.8% ETF leg）
- 权重：`0/30/50/70/100%` stock
- 输出：MDD–年化前沿 JSON

**假设：** 50% aggressive ETF + 50% vol25 MA120 → 年化 ~20%、MDD ~-18%（待跑验证）。

### P2.3 三轨 paper 组合（research）

| 腿 | 权重 | Profile / preset |
|---|---:|---|
| ETF aggressive | 50% | live optional |
| MA120 vol25 个股 | 30% | research |
| 红利 expanded | 20% | live snapshot |

return blend proxy；对比纯 aggressive live 与纯 vol25。

### P2.4 PIT 成分（依赖 CnEquitySnapshotPipelines）

- 新增 `csi500_constituents_pit` feature（或复用 index membership snapshot）
- `_load_universe_bundle` 按 `as_of` 过滤 candidate
- 重跑 vol25 MA120 full sample，记录与 non-PIT 差异

### P2.5 单票 weight cap

- `industry_etf_rotation_core` 增加 `max_single_name_weight`（默认 None；research preset 设 0.10）
- 重跑 vol25，观察 MDD/OOS 变化

---

## 5. 命令备忘

```bash
# MA120 vol 矩阵 + 权重网格
cd CnEquityStrategies
PYTHONPATH=src:scripts:../QuantPlatformKit/src \
  python3 scripts/research_cn_ma120_vol_and_combo_scan.py \
  --json-output docs/research/cn_ma120_vol_and_combo_scan_20260628.json

# Live 候选对照
PYTHONPATH=src:scripts:../QuantPlatformKit/src:../CnEquitySnapshotPipelines/src \
  python3 scripts/research_cn_live_candidate_evaluation.py \
  --json-output docs/research/cn_live_candidate_evaluation_20260628.json

# ETF + 个股 combo（vol15 防御版，对照）
PYTHONPATH=src:scripts:../QuantPlatformKit/src \
  python3 scripts/research_cn_etf_momentum_stock_combo_proxy_backtest.py \
  --stock-preset momentum_csi500_top5_vol25_ma120_riskoff \
  --etf-weight 0.30 --stock-weight 0.70
```

---

## 6. Promotion 到 Live 的最低条件（建议）

1. PIT 池重跑后，vol25 MA120 年化 ≥ 22%、MDD ≥ -28%、OOS lift ≥ +10pp vs ETF aggressive  
2. 单票 cap + 流动性过滤上线  
3. 与 live ETF 腿做 **50/50 paper 组合** 6 个月，MDD 不劣于 -25%  
4. 用户明确批准将 catalog 从 `research_backtest_only` 改为 optional QMT target（类似 aggressive ETF 路径）

**当前建议：** 保持 research_only；live 主 alpha 用 **aggressive ETF optional target**，个股 sleeve 继续 Phase 2 回测。

---

## 7. Phase 2 回测结果（2026-06-28）

**脚本：** `research_cn_ma120_phase2_return_focused.py`  
**JSON：** `docs/research/cn_ma120_phase2_return_focused_20260628.json`

### 7.1 P2.1 Promotion gate

| Gate | vol25 MA120 | 结论 |
|---|---|---|
| Standard（MDD≥-25%, ΔMDD≤5pp） | fail（mdd_vs_baseline -8.1pp） | 预期 |
| Return-focused（MDD≥-35%, OOS lift≥10pp, **ΔMDD≤10pp**） | **PASS**（OOS +29pp vs conservative, MDD -23.5%） | vol25 为唯一 promoted 候选 |

vol18–vol22 在 return-focused gate 下仍 fail（OOS lift 或 ΔMDD 边界）。

### 7.2 P2.2 Aggressive ETF + vol25 权重网格

| ETF / 个股 | 年化 | MDD | OOS 2024+ |
|---|---:|---:|---:|
| 100% vol25 MA120 | **25.2%** | -23.5% | +118% |
| **30% aggressive + 70% vol25** | **24.0%** | **-17.0%** | **+113%** |
| 50% / 50% | 21.6% | -15.7% | +109% |
| 70% / 30% | 19.0% | -15.5% | +104% |
| 100% aggressive ETF | 14.8% | -15.4% | +94% |

**Research paper 组合建议：** **30% live aggressive ETF + 70% vol25 MA120**（return blend）— 年化 24%、MDD -17%，OOS +113%，Sharpe 优于纯 vol25 单腿。

### 7.3 下一步（Phase 3）

1. 三轨 blend：50% aggressive + 30% vol25 + 20% expanded 红利  
2. PIT CSI500 成分重跑 vol25  
3. 单票 weight cap 8–10% 后复验 gate
