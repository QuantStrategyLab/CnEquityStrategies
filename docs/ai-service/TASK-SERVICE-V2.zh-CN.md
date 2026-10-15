# CN ETF 通用任务调用

本地迁移基线：CnEquityStrategies `8f2c7296ddad5245203f445667f18fa41dc13d91`。没有修改主工作区、提交、发布、部署或调用真实模型。

`backtest/index_etf_research_task.py` 接管原 AIAuditBridge 的 CN ETF 研究调用、根用户保护的本地政策、来源与问题绑定、每日一次新研究准入、真实前向观察及终态归档校验。策略边界由本仓库提供，AI 服务只接收通用任务。

新入口身份为 `QuantStrategyLab/CnEquityStrategies/.github/workflows/cn-index-etf-research.yml@refs/heads/main`；新政策与持久目录分别为 `/etc/cn-equity-strategies-policy/` 和 `/var/lib/cn-equity-strategies/`。这些只是本地代码约定，尚未创建或更改云端配置。旧研究记录不能直接搬到新目录并视为已授权；需按历史来源和原任务身份审核。

任务结果完成并绑定原请求后才能解释研究建议。等待或未知结果保存 task ID；恢复只查询原任务。原有 QPK 持久流程新增 `read_pending_diagnosis` 传递，冻结数值输入、参数空间、手续费、回测和人工审批不由助手选择。已过前向窗口不能触发新研究；读取既有任务不会制造新的观察证据。

离线验证覆盖根用户政策、Actions/OIDC 身份、任务来源、每日准入、日历与 shadow 证据、归档幂等、等待恢复及既有数值任务测试。测试输入均为 synthetic。

发行尚未完成：新的入口 workflow、已核验 wheel 安装与依赖版本更新待落实。`research` extra 和锁文件已移除旧 AIAuditBridge SDK，证据审查 workflow 不再 checkout AIAuditBridge。QPK 的现有固定版本还没有新接口，必须在同批正式发行后更新；现在不能直接切换入口。CN 保护政策仍要求 QPK 从非 editable 的固定 Git 提交安装并核对 direct_url；本地 wheel 只用于打包验收，不替代该生产来源准入。PersonalAIService 使用经过核验的构建材料。没有伪造新的远端提交号或已发布包。

证据审查由策略调用方构造任务，保持 primary、secondary、independent 三名角色。未完成、缺少角色、非法格式或冲突不会通过；服务配置缺失返回阻断，不能因旧脚本缺失而静默成功。保留原有显式 `DUAL_REVIEW_GATE_SKIP` 操作入口；没有新增自动跳过。漂移 workflow 的旧复用入口和 CN 新研究 workflow 仍待迁移。

## 所有者流程收尾

漂移流程使用本仓库的新 reusable workflow，模型审查改为可配置三角色；来源、快照和金融准入保持原有边界。策略研究的新手动 workflow 默认关闭，通过 AI_SERVICE_RELEASE_READY 与经过批准的云端环境启用，未增加交易或自动采用权限。共享依赖必须使用准确批准的源码/产物；当前未发布，不能改成一个不存在的远端 SHA。
