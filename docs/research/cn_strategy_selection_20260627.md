# A 股策略选型研究（2026-06-27）

> 投资有风险。本文档为工程与研究证据，不构成投资建议。

## 1. 结论摘要

原先从港股平移的两条策略**部分适用、部分需调整**：

| 原方案 | A 股适配性 | 调整方向 |
| --- | --- | --- |
| ETF 动量轮动 | **适用，但必须加强风控** | 保留，叠加相关性过滤、基准 risk-off；裸动量无风控在 A 股回测可亏 76%+ |
| 红利低波单票 snapshot | **部分适用** | 改为 **红利+质量** 复合因子；纯低波/纯价值在 2025–2026 成长/预期驱动阶段承压 |

**最终推荐的双轨（个人中长线 / 中低频）**：

1. **`cn_index_etf_tactical_rotation`**（direct，进攻/轮动）— 改进版 ETF 动量轮动
2. **`cn_dividend_quality_snapshot`**（snapshot，防守/底仓）— 红利+质量选股，低波仅作辅助约束

**暂不纳入 runtime（仅 research scaffold）**：

- **`cn_small_cap_quality_snapshot`** — 社区极热（聚宽/JoinQuant「小市值+ETF 双核」），但注册制后尾部风险与容量问题显著，需独立 evidence gate

## 2. 论坛与社区主流策略（2025–2026）

### 2.1 小市值 + ETF 双核（JoinQuant / 雪球 / JunQuant 高热）

- 代表：JunQuant `smc_v3`、社区「双龙出海」
- 逻辑：小市值负责 A 股弹性，ETF 轮动负责板块趋势与 1 月/4 月避险
- 优点：回测进攻性强，社区验证多
- 风险：2020 年后纯小市值多次大回撤；微盘波动率可达 40%；需严格基本面与流动性过滤
- **组织决策**：列为 research scaffold，不首批 runtime

### 2.2 ETF 动量轮动（个人量化最主流入口）

- 代表：次方量化、QKA、吴润 ETF 轮动指南
- 频率：约 15 天–月度审视（中低频）
- **A 股关键发现**（社区回测共识）：
  - 追踪止损 + 相关性过滤贡献大部分超额
  - 裸动量排名无风控：最大回撤可达 -76.9%
  - MA200 / 绝对动量 / 切换门槛 / 波动率加权均为必要组件
- **组织决策**：保留并强化 `cn_index_etf_tactical_rotation`

### 2.3 红利 + 质量（机构与指数公司共识）

- 代表：中证全指红利质量（932315）、国泰海通低波增强、腾讯新闻因子观察
- A 股 2010–2024：价值、红利、低波、质量、现金流因子长期较有效；纯成长/纯动量较弱
- 2025–2026：纯价值/红利在「盈利预期+成长」阶段承压；**红利+质量**复合优于纯红利低波
- **组织决策**：snapshot 策略改为 `cn_dividend_quality_snapshot`，提高质量因子权重

### 2.4 风格轮动 / 宏观择时（机构级，个人可简化）

- 代表：国联民生低换手风格轮动、界面新闻高景气 vs 红利轮动
- 逻辑：宏观多头配红利+动量+成长；空头配红利+低波+质量
- **组织决策**：后续可通过 `QuantStrategyPlugins` / `MarketSignalSources` 做 sidecar，不首批写入策略仓

### 2.5 因子动量（学术证据强）

- A 股横截面因子动量 1 个月回看 Sharpe ~1.15（Quant Decoded）
- 更适合机构/multi-factor 框架；个人实施复杂度高
- **组织决策**：不在首批 personal mid-low freq 范围

## 3. 与港股方案差异

| 维度 | 港股 | A 股 |
| --- | --- | --- |
| 单票 snapshot | 低波+股息+质量 | **股息+质量为主**，低波降权 |
| ETF 轮动 universe | 港股上市全球 ETF | 沪深 ETF + 跨境 + 防御货基/国债 |
| 基准 risk-off | 可选 | **沪深300 MA200 必备** |
| 额外风控 | VCM/CAS | T+1、涨跌停、ST、100 股整手 |
| 社区最热组合 | HK ETF 轮动 | **小市值+ETF 双核**（高风险，暂缓） |

## 4. 当前仓库策略面（本分支）

| Profile | 类型 | 状态 | 角色 |
| --- | --- | --- | --- |
| `cn_index_etf_tactical_rotation` | direct | runtime_enabled | 进攻/轮动 |
| `cn_dividend_quality_snapshot` | snapshot | runtime_enabled | 防守/底仓 |
| `cn_small_cap_quality_snapshot` | snapshot | research_scaffold | 社区高热，待 evidence |

## 5. 证据与下一步

1. 用 `CnEquitySnapshotPipelines` 产出 `cn_dividend_quality_snapshot` factor snapshot + manifest
2. 对两条 runtime 策略分别跑 proxy backtest（含 A 股费用、T+1、涨跌停约束）
3. `cn_small_cap_quality_snapshot` 需单独 long/short window evidence 后再考虑 promotion
