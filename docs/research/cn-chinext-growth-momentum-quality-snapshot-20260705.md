# 创业板成长动量质量策略设计（2026-07-05）

> 投资有风险。本文是工程与研究设计，不构成投资建议。

## 1. 定位

这条策略的目标不是替代当前 A 股主轨，而是补一条 **创业板进攻增强 sleeve**：

- **比 `cn_industry_etf_rotation` 更进攻**
- **比裸小市值/纯动量更稳**
- **更适合作为 `cn_equity_combo` 的股票腿候选**

建议先作为 `scaffold` / external snapshot scaffold，不直接进 `runtime_enabled`。

## 2. 为什么是创业板

创业板的典型特征是：

- 成长属性更强，盈利预期变化更敏感
- 行业集中度高，容易出现阶段性主线
- 波动大、涨跌幅限制 20%，对风控要求高
- 更适合“成长 + 动量 + 质量”而不是单纯低估值

这意味着策略必须同时管住：

1. 选股质量
2. 动量持续性
3. 流动性和拥挤度
4. 回撤和买卖可执行性

## 3. 建议的策略形态

### 3.1 Universe

- 深交所创业板股票
- 排除 `ST/*ST`
- 排除上市天数不足 252 交易日
- 排除 `adv20_cny` 过低、停牌过多、财务字段缺失
- 必要时再叠加市值下限，避免微盘尾部风险

### 3.2 打分框架

建议采用 snapshot 形态，月频调仓，季度更新财务字段：

```text
score =
  0.30 * growth_score
+  0.30 * momentum_score
+  0.20 * quality_score
+  0.10 * liquidity_score
+  0.10 * risk_adjustment
```

### 3.3 因子建议

**Growth**

- 营收同比 / 增速分位
- 归母净利润同比 / 增速分位
- 经营现金流增速
- 如果未来接入一致预期，再加预期修正

**Momentum**

- 12M-1M 动量
- 60/120 日趋势
- 相对创业板指超额动量

**Quality**

- ROE TTM
- ROE 稳定性
- 毛利率或经营现金流质量
- 资产负债率惩罚

**Liquidity**

- `adv20_cny`
- 成交额稳定性
- 预估冲击成本

**Risk adjustment**

- 短期涨幅过陡惩罚
- 成交额拥挤惩罚
- 波动率异常放大惩罚

## 4. 风控建议

| 项 | 建议 |
|---|---|
| 调仓频率 | 月频 |
| 持仓数 | 15–25 只 |
| 单票上限 | 6%–8% |
| 行业上限 | 30%–35% |
| 最大 gross | 90%–100% |
| 现金缓冲 | 2%–5% |
| hard risk-off | 创业板指跌破 MA200 或 breadth 过弱时降仓 |
| soft risk-off | 趋势破坏时转入 `159915` / `510300` / 现金替代 |

要点是：**创业板策略不能只看收益，不看成交、涨跌停和尾部回撤。**

## 5. 与当前 A 股策略对比

| 维度 | `cn_industry_etf_rotation` | `cn_dividend_quality_snapshot` | 新创业板策略 |
|---|---|---|---|
| 资产 | ETF | 防守型单票 | 创业板单票 |
| 角色 | 主轨进攻 | 防守底仓 | 进攻增强 sleeve |
| 数据依赖 | `market_history` | `feature_snapshot` | `feature_snapshot` + PIT 财务/行情 |
| 风格 | 行业动量 | 红利 + 质量 | 成长 + 动量 + 质量 |
| 容量 | 高 | 中 | 低到中 |
| 回撤控制 | 已有较好证据 | 防守特征更强 | 需要更严格 gate |
| 适合上线顺序 | 已上线 | 已上线 | 先 research，再 promotion |

### 实际判断

- **对比行业 ETF 主轨**：创业板策略弹性更高，但回撤和拥挤度也更高。
- **对比红利质量轨**：方向相反，适合做组合中的进攻腿，而不是单独替代防守腿。
- **对比 `cn_equity_combo`**：最自然的接入点是替换或细化股票腿，但前提是先跑通长样本 evidence gate。

## 6. 推进路径

### Phase 1：scaffold

- 先把策略定义为 external scaffold
- 补齐 snapshot contract
- 跑 2021–2026 月频回测

### Phase 2：evidence gate

至少验证：

- 年化收益是否优于行业 ETF 主轨
- 最大回撤是否可控
- 2021–2022 熊市是否没有明显失真
- 2024+ 样本外是否还能维持 alpha

### Phase 3：runtime 决策

通过 gate 后再决定：

- 是否进入 `cn_equity_combo`
- 是否新增受控 QMT target
- 是否成为独立 `runtime_enabled` profile

## 7. 这次先落地的内容

- 新增创业板策略研究设计文档
- 把它放进 external scaffold 目录
- 让 catalog 明确它是 `scaffold`，不进 runtime
