# A 股 AI 自动研究首例：双宽基 ETF 轮动

截至 2026-09-08，本例完成了本地执行能力与拒绝路径，尚未完成真实数据回测、前向 shadow 或人工候选晋级。研究结果的成功条件是可复核且正确拒绝不合格材料，不是必须调出盈利策略。

## 角色与选择依据

- `QmtPlatform` 是执行适配层；当前 `application/qmt_client.py` 使用 synthetic 账户快照和订单预览，非 dry-run 请求返回 blocked。离线 paper admission 校验本地输入身份，不连接券商 paper 账户。
- 策略与回测属于 `CnEquityStrategies`，数据接入属于 `CnEquitySnapshotPipelines`。本次仅修改策略仓，不修改 QMT 的 runtime allowlist、目标开关或订单路径。
- 复用已有 `cn_index_etf_tactical_rotation`，将本例研究配置限定为 `510300`、`510500` 和现金。首例不依赖个股历史财报、动态股票池、跨境 ETF 或复杂期权。
- 这是基于工程可解释性与既有代码的选择，不是基于本轮真实收益排名；不代表已验证优于现有行业 ETF 策略。

迅投官方区分 XtData 行情与 XtTrader 交易模块，要求使用前启动 MiniQMT 客户端。仓库存在不证明拥有已配置券商终端或连接权限。本轮未连接任何 QMT 终端。[迅投快速开始](https://dict.thinktrader.net/nativeApi/start_now.html)

## 冻结的首例设计

| 项目 | 本例约定 |
| --- | --- |
| 标的 | 沪深 300 ETF `510300`、中证 500 ETF `510500`；不合格时持现金 |
| 基准 | 选参先比较原始参数配置；正式晋级还需同窗口、含成本的 `510300` 买入持有基准 |
| 信号 | 正动量且高于趋势均线；沪深 300 低于固定 200 日均线时转现金 |
| 默认参数 | 动量 60 日、趋势 200 日、选择 1 只 ETF |
| 搜索 | 动量 `{40,60,80}` × 趋势 `{120,200}` × 持有数量 `{1,2}`，共 12 组、3 个参数键；预算较低时由既有 QPK 搜索截断。另有 1 次 baseline 和最多 3 次开发分段诊断，单次完整作业最多 16 次 runner 调用 |
| 权重 | 合格 ETF 等权、无杠杆；不使用波动率缩放；保留原 proxy 的 2% 现金余量 |
| 频率 | 月度；现有 proxy 在月末决策日使用此前可见收盘数据，再于后续交易日按收盘价代理成交 |
| 成本 | proxy 继承双边每笔 3 bps、最低 5 元的工程假设及 100 份单位；不是用户券商实际报价 |
| 时间窗口 | 必须显式给 development 起止日，至少 220 个交易日预热；当前固定日历仅覆盖 2024–2026，预热首日和 development 末日必须在覆盖内；不自动选历史“最佳”窗口；不读取锁定 OOS 输入来搜索 |
| AI 角色 | Codex 解释异常、查一手规则、提出有界参数假设；确定性代码执行搜索。该回调不调用模型、不调用付费 API |

上交所说明股票 ETF 实施 T+1、交易单位为 100 份；这支持首例使用 A 股股票 ETF 的交收与整手约束。该说明不能证明收盘价代理等于真实可成交价。[上交所 ETF 问答](https://www.sse.com.cn/assortment/fund/etf/question/)

上交所历史名录记载 `510500` 于 2013-03-15 上市。历史测试不得倒填上市前价格；固定两只 ETF 也不代表已经解决选池偏差或公司行动会计。[上交所 ETF 名录](https://english.sse.com.cn/access/via/eligible/)

## 本次完成的实现

1. 修复 `CnProxyBacktestRunner.run` 忽略调参的问题。旧版记录全部 `params`，实际仅向策略传入 `min_history_days`；现已传入实际参数，并使用相同的管理标的。极高动量门槛现在会产生现金结果，未知参数不再静默通过。旧报告未覆盖或重标，凡依赖被忽略参数作比较的旧结论须重新验证。
2. 修复明确传入空防守池仍恢复默认防守 ETF 的提取逻辑。首例只管理冻结的两只 ETF，不意外要求货币/债券 ETF 数据。
   同时修复普通工作日切片截短真实预热的问题：2025-01-02 的反例中原有 225 个工作日窗口只保留了 211 个交易观察日；改为保留输入中的 225 个实际日期，输出评估窗口保持不变。
3. 新增 `backtest/index_etf_research_job.py`，提供可直接传给 QPK 的 `optimize(drift, budget)` 回调。它注册已有 runner，调用 `BacktestOrchestrator` 和 `run_grid_search`，没有新建调度或实验管理框架。
4. 新入口拒绝缺输入、非冻结标的、重复记录、NaN/无穷/布尔价格、缺交易日、不足预热和不匹配候选。开发窗口后的价格在校验与搜索前剔除；持有资产的缺价仍沿既有 runner 拒绝。
5. 每个实际执行的 baseline/grid/development segment 均保留参数、窗口、成功或失败状态。成功结果由原有 `PerformanceStore` 保存；失败日志只有固定原因，不包含供应商错误或行情明细。外层 job 必须在失败/取消时也持久化 `trial_records`。
6. 原有 pilot 增加 `--bounded-research`，没有输入时结构化返回 parked，退出码 2；不会自动抓数据或生成 synthetic 代替真实输入。legacy smoke 仍兼容，并显式标为 synthetic/learning-only。

入口：

```text
python scripts/run_cn_index_etf_walk_forward_pilot.py --bounded-research
```

上述无输入命令只验证缺项拒绝。用经批准的本地开发数据执行时，另传 `--market-history`、`--development-start`、`--development-end`、独立的 `--store-root` 和 `--json-output`。CLI 不认证输入许可，因此输出始终标记 `caller_supplied_unverified` 和 `promotion_eligible=false`；不要把它直接发布为可信研究输入。

## 接入现有 AI 链路的位置

```text
新鲜且来源有效的偏离事件
  → Codex 根因分类（数据/平台问题先修，或决定无需优化）
  → 输入 producer 校验来源/许可/版本，只向 job 提供开发分区
  → make_index_etf_optimizer(...)(drift, budget)
      BacktestOrchestrator → 当前 CN runner → 有界 trial → OptimizationProposal
  → 真实 strict backtest callback：purged WFA + 锁定独立 OOS
  → 同候选与基准的真实前向 paired shadow callback
  → QPK ticket → QRT 候选写入并读回 → 人工接受/拒绝
```

具体接线契约：

| 现有 hook | 本例绑定/当前状态 |
| --- | --- |
| `optimize(drift, budget)` | `make_index_etf_optimizer(market_history, development_start, development_end, store, trial_records)` 返回的函数；本地已执行真实数值计算 |
| `enforce_backtest_gates(proposal)` | 仍缺可用于晋级的 CN runner 与完整证据；不能将 proxy 输出包装成 PASS，也不能手填 IC、WFA/OOS |
| `record_shadow(proposal)` | 仍缺真实前向同窗基准/候选观察结果；没有 QMT 订单权限也可研究型 shadow，但必须有批准行情与真实时间积累 |
| `sync_console(ticket)` | 复用 QPK/QRT 既有 adapter；前两项未通过时不调用 |
| 当前消费者版本 | CN main `83060e19d298` pin QPK `c812ed70f83d`，该 pin 没有 `research_promotion_cycle`。优化回调兼容旧 pin；HITL 集成须在 QPK 实现发布后选择性采用新版并验证安装包 |

新 QPK `run_actionable_research_promotion` 会在缺 strict/shadow callback 时先 parked，不应为跑示例传入假的 PASS 回调。本轮另用 QPK 本地新版验证了实际优化结果进入现有 cycle 后的拒绝路径，以及模拟候选分支在缺严格证据时停下。没有产生人工候选，也没有调用 shadow、控制台或模型。

`learning_only` 描述当前输入和 runner 的证据能力，不是另建永久禁止晋级的体系。后续在原 runner/adapter 内补齐真实事件时序和输入，再产生新的严格证据；旧 proxy 报告保持原状态。

## 当前不能宣称成功的具体原因

| 缺口 | 进入真实验证前的最小工作 |
| --- | --- |
| 数据许可与来源 | 已有 legacy CSV 产物：[2026-09-08 最新发布 run 34235477987](https://github.com/QuantStrategyLab/CnEquitySnapshotPipelines/actions/runs/34235477987) 成功，未过期 artifact `10059689779` 为 `cn-equity-market-history-34235477987-1`。当前 workflow 仅运行腾讯 CSV staging 并上传 CSV，未调用要求官方许可/复权材料的严格 publisher，也未提供可核验的 `research_input_manifest.v1`。因此是“已有研究 CSV、批准来源材料未核验”，不能称没有数据或直接批准晋级。私有 vault 是否已有合格包未知；本轮未下载 CSV/archive/bars |
| 开源库与数据权利 | AKShare 官方只声明接口/数据用于学术研究；库开源不代替腾讯等底层数据源的许可、保留和再分发范围确认 |
| 成交时序 | 当前 close-only proxy 不是下一开盘可执行结果；需要分开信号复权价、原始成交价、实际可见时间及交易日历 |
| 历史日历 | 当前 pinned QPK 只收录 2024–2026 节假日；更早年份退化为工作日，不能宣称完整。正式更长历史研究前须由既有 producer/runner 接入覆盖全部窗口的官方日历，不能补入假价格填“缺日” |
| 停牌/涨跌停/流动性 | 需要当日停牌、交易资格、实际价格上下限和可成交量；不能仅以收盘涨跌幅推断成交；限价成交失败应保留未成交状态与现金 |
| 公司行动 | ETF 分红、拆分和价格调整应可复核；不能把复权价格直接当现金成交价格。`510300` 在 2026 年有除息公告，说明这不是可永久忽略的边角情况 |
| 费用与基准 | 确认实际券商费用/最低费用与税费适用范围，建立滑点和流动性压力测试；基准按同窗口、成本和成交假设计算，不能只比较毛收益 |
| 晋级验证 | 沿实际锁定 validator，至少 3 个有序 purged folds、正 purge/embargo、独立锁定且未用于选择的至少 12 日历月 OOS；已看窗口只是 development |
| QMT 环境 | 真正的 broker paper/readback 需券商支持的 miniQMT 环境、已配置 session、只读查询与账户/持仓/委托/成交/现金/账务证据；离线 admission 不替代这一步 |

资料：[AKShare 项目声明](https://akshare.akfamily.xyz/introduction.html)、[沪深 300 ETF 除息对应公告](https://www.sse.com.cn/assortment/options/disclo/update/c/c_20260116_10805396.shtml)。本例未购买数据、配置付费服务、登录券商或启动真实交易。

## 验证记录

- 本次基线为 CN `83060e19d298dde96235a55b40f99762e2d51aa3`，独立 worktree，未 commit/push/PR。
- 参数修复前两项回归均实际失败；修复后参数影响、错参拒绝、整手、费用、后续交易日执行、缺价、现金防守等相关测试通过。
- 测试仅使用代码生成的 synthetic 行情。隔离探针确认原 workspace、凭据路径、网络均不可读/不可访问。
- 当前 pinned QPK 的优化测试与本地新版 HITL 集成分别验证；后者不代表消费者已经升级或服务已经发布。
- 当前 pin 的六个相关测试文件：71 passed、2 skipped、4 subtests passed；最后补充的输入回归：7 passed（含新增 nullable 缺值一项）。两项 skip 对应旧 pin 缺失 HITL 模块。新版 QPK 的两项跨仓集成另行验证通过；无真实历史收益或真实 shadow 成功结论。

### 2026-09-09 晋级复核退出保护

在 CN `c5576b613fbf37c0b82398b0052e60be6031086a` 后续切片中，修复 Evidence Gate 将复核子进程退出码 `1` 或负退出码误当通过的问题：任何非零退出均阻断，多工件中后续成功也不能覆盖此前失败。使用真实本地合成 Python 子进程，先复现 4 个失败子案例，再验证 5 项测试通过（含多工件、全成功、原有显式 skip 与缺可选脚本行为）。本次不运行真实模型，不改变证据发现、validator、候选数值或执行权限；CN/QPK pins 保持原值。新研究代码采用新版 QPK 与 Evidence Gate/定时漂移工作流的实际版本采用仍须分别核对，旧冻结证据不重解释。
