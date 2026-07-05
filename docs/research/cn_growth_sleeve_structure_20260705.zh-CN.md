# CN 成长 sleeve 结构草案（2026-07-05）

> 这是一份 CN 成长栈的设计草案，不是交易建议。

## 目标

把 CN 成长侧从“几个战术线 / 研究残留”整理成清晰结构，拆成三层：

1. **创业板成长 sleeve**
2. **科创板成长 sleeve**
3. **CN 组合 orchestrator**

这属于设计纠正，不只是参数微调。

## 为什么原来的形态不对

之前的形态把创业板 / 科创板当成了偏附属的研究分支，这太窄了。

公开市场表现说明这两个成长板块在当前成长行情里是可以领跑的。
更合理的理解是：

- 板块本身就是有效的成长 universe，
- 策略形态要单独建板块 gate，
- combo 层应该负责分配 sleeve，不该冒充唯一 alpha。

## 第一层：创业板成长 sleeve

### 建议 profile 名称

- `cn_chinext_growth_momentum_quality`

### 角色

面向创业板市场的独立成长 sleeve。

### 形态

- universe：创业板全池
- 频率：月频
- 风格：成长 + 动量 + 质量
- 显式 regime gate：基准趋势 + 广度 + 流动性 + 拥挤度

### 建议因子

- 营收增长
- 利润增长
- ROE / 盈利稳定性
- 12M-1M 动量
- 60/120 日趋势
- 流动性和执行成本
- 过热 / 拥挤惩罚

### 建议行为

- 可以从现有研究 snapshot 继续晋级。
- 不应该和行业 ETF 主线共用同一套 gate。
- 后续可以作为 combo orchestrator 的一个 sleeve。

## 第二层：科创板成长 sleeve

### 建议 profile 名称

- `cn_star_growth_momentum_quality`

### 角色

面向科创板 / STAR50 universe 的独立成长 sleeve。

### 形态

- universe：STAR50，或在后续证据支持下扩展到 STAR100 / STAR200 /
  专精特新等更广的科创板 universe
- 频率：月频
- 风格：成长 + 质量 + 流动性
- 比创业板更严格的集中度和流动性约束

### 建议因子

- 营收 / 盈利增长
- 研发强度或创新代理指标
- 盈利稳定性
- 12M-1M 动量
- 相对 STAR 基准趋势
- 流动性 / 换手 / spread 惩罚

### 建议行为

- 第一版先做成板块级增强 sleeve，不要一上来就做很窄的选股冠军。
- 比创业板更严格，因为科创板对集中度和流动性更敏感。
- 第一版尽量简单、可审阅。

## 第三层：CN combo orchestrator

### 当前问题

`cn_equity_combo` 现在更像一个混合研究策略，语义太模糊。

### 新角色

把它改成真正的 orchestrator / allocator：

- 分配不同 sleeve
- 管理 regime budget
- 决定进攻 / 防守的预算倾斜
- **不再**声称自己是一条单一 alpha 线

### 建议 sleeve

- 行业 ETF 主 sleeve
- 创业板成长 sleeve
- 科创板成长 sleeve
- 防守红利 / 质量 sleeve

### 建议 runtime 形态

```json
{
  "profile": "cn_equity_combo",
  "sleeves": [
    {"profile": "cn_industry_etf_rotation", "weight": 0.40},
    {"profile": "cn_chinext_growth_momentum_quality", "weight": 0.25},
    {"profile": "cn_star_growth_momentum_quality", "weight": 0.15},
    {"profile": "cn_dividend_quality_snapshot", "weight": 0.20}
  ]
}
```

权重可以配置，但职责拆分不能变。

## 门槛模型

### 继续调参

- 行业 ETF 主线继续作为 A 股 runtime 核心策略
- aggressive ETF 继续作为受控增强线

### 需要重构

- 创业板 tactical 和创业板 growth snapshot 要重构成创业板成长 sleeve
- 科创板要单独有自己的 sleeve，不要硬塞进创业板逻辑
- combo 要重做成 orchestrator

### 不要做

- 不要把板块成长直接并进行业 ETF 主线
- 不要保留太多小变体，只因为每个变体都只改了一点点
- 不要在同周期里还打不过主线时就提前 live

## 证据顺序

1. 先建板块级成长 sleeve contract。
2. 跑同周期对照，直接对比当前行业 ETF 主线。
3. 加入流动性 / spread / 拥挤度惩罚。
4. 确认惩罚后仍然能赢。
5. 再决定是 `live_candidate` 还是继续 research。

## 外部参考形态

这个结构和官方板块/指数定义是匹配的：

- 创业板本身就是成长属性很强的深交所板块 universe。
- 科创板 / 科创50 是上交所创新板块 universe，天然更集中、更敏感。

所以这两条线应该是独立 sleeve，而不是 generic tactical leftovers。

## 参考锚点

- 上交所官方 STAR 50 / STAR 100 / STAR 200 指数编制方案
- 上交所科创板相关指数和基金披露材料
- MSCI 因子指数家族中关于 growth / quality / momentum / low volatility 的框架
- EDHEC 和 AQR 趋势跟随研究中的 regime gate 逻辑
