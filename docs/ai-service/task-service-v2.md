# CN ETF Generic Task Invocation

English | [简体中文](task-service-v2.zh-CN.md)

Local migration baseline: `CnEquityStrategies` `8f2c7296ddad5245203f445667f18fa41dc13d91`. No changes were made to the primary workspace, commits, releases, deployments, or live model invocations.

`backtest/index_etf_research_task.py` takes over the former AIAuditBridge CN ETF research invocation, root-protected local policy, source and issue bindings, once-daily new research admission, live forward observation, and terminal archival verification. Strategy boundaries stay in this repository while the AI service receives only generic tasks.

The new entry workflow identity is `QuantStrategyLab/CnEquityStrategies/.github/workflows/cn-index-etf-research.yml@refs/heads/main`, with local policy and persistence paths `/etc/cn-equity-strategies-policy/` and `/var/lib/cn-equity-strategies/`. These reflect local code conventions only and do not imply cloud resources have been created or modified. Legacy research records cannot be copied directly to the new directory and treated as authorized; they must be audited by historical provenance and original task identity.

Task outcomes may only be interpreted as research advice after completion and binding to the original request. Pending or unknown outcomes persist the task ID so recovery queries only the original task. The existing QPK persistence path passes through `read_pending_diagnosis`; frozen numerical inputs, parameter spaces, fees, backtests, and manual approvals are never chosen by the assistant. Expired forward windows cannot trigger new research, and reading existing tasks produces no new observation evidence.

Offline verification covers root-owned policy checks, Actions/OIDC identity, task provenance, daily admission, calendar and shadow evidence, idempotent archiving, pending recovery, and existing numerical task tests using synthetic test inputs.

Release steps remain pending: enabling the new entry workflow, installing verified wheels, and updating dependency versions are not yet complete. The legacy AIAuditBridge SDK has been removed from the `research` extra and lockfile, and the evidence-review workflow no longer checks out AIAuditBridge. The currently pinned QPK version does not expose the new interface yet and must be updated after a coordinated official release before switching entrypoints. CN protection rules still require QPK to be installed from a non-editable pinned Git commit with verified `direct_url`; local wheels support packaging acceptance only and do not replace production source gates. PersonalAIService uses verified build artifacts without fabricating remote SHAs or published packages.

Evidence review constructs tasks from the strategy caller while preserving `primary`, `secondary`, and `independent` roles. Incomplete results, missing roles, invalid formats, or conflicts fail validation; missing service configuration returns blocking status rather than silently succeeding due to absent legacy scripts. The explicit `DUAL_REVIEW_GATE_SKIP` operator override remains intact with no automatic skip added. Migrating the legacy drift reusable workflow and the new CN research workflow remains open.

## Owner Flow Closure

The drift flow adopts this repository's new reusable workflow with configurable three-role model review while preserving existing source, snapshot, and financial admission boundaries. The new manual strategy-research workflow defaults to disabled, gates activation on `AI_SERVICE_RELEASE_READY` and approved cloud environments, and grants no trading or auto-adoption permissions. Shared dependencies must reference actually approved sources or artifacts; unpublished local state cannot be substituted with a fabricated remote SHA.
