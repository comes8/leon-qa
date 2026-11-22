# P15 Binance API 外部规则映射与测试补强

## 任务

将 Binance 官方 API 参考与本项目的需求、接口契约、配置、现有测试点或用例做可追溯映射，识别可以迁移的测试判据、不能直接迁移的产品差异，以及需要补充的覆盖。此 Prompt 只做资料分析和测试设计，不连接 Binance 生产环境，不读取或生成密钥，不把外部规则自动升级为公司规则。

## 输入

- `{{task_mode}}`：`map`、`design`、`amend` 或 `review`。
- `{{project_materials}}`：项目需求、接口目录、配置、业务模型、测试点、用例或运行报告；逻辑上对应统一输入的 `source_materials`。
- `{{binance_reference}}`：`references/binance-api-reference.md`、N-Tester 的 Binance 快照或指定官方链接。
- `{{scope}}`：Spot、USDⓈ-M、资金、事件、API 安全或指定的窄范围。
- `{{existing_assets}}`：已有 REQ/RUL/TP/TC/SCN ID 及版本；若平台仍使用 CASE 字段，按统一规范映射为 TC。
- `{{requested_output}}`：映射矩阵、测试点增量、用例修订、评审意见或 Markdown/JSON 报告。
- `{{constraints}}`：环境、数据、预算、时间、执行能力和副作用策略。

## 工作规则

1. 先固定 `task_mode`、产品、API 版本、环境、资料日期和范围；Spot、USDⓈ-M、Coin-M、Margin、DEX 不得因字段相似而混用。
2. 对每条规则输出 `reference_rule_id`、`project_rule_id`、`mapping_status`、来源版本、适用环境和影响范围。
3. `reference_only` 只用于发现覆盖或设计方向；只有项目材料和责任人确认后，才可使用 `confirmed_project_rule` 作为硬断言。
4. 对交易对过滤器、精度、手续费、冻结/结算、状态、时间窗口、限流和事件顺序要求来源、单位、截面和独立观察点。
5. 对请求超时、HTTP 5XX、429/418、事件延迟、重复通知和重试，分别说明“传输结果、业务受理、业务终态、账务/仓位收敛”。
6. 现货改单的 keep-priority 语义与 USDⓈ-M LIMIT 改单重排队必须分开；单向/双向持仓、reduceOnly、closePosition 和条件单互斥必须按合约产品单独核对。
7. 保留已有 ID 和版本映射。不能证明的规则使用 `resolution_status: pending` 或 `resolution_status: blocked`，不要用 Binance 示例数字填补项目数据。若下游旧 Schema 仍要求 `needs_confirmation`，只能作为由 `resolution_status` 派生的兼容字段。
8. 只输出分析或设计结果；若用户要求执行，仍需先确认授权环境、测试账号、数据准备、观察接口、清理和副作用策略。

`mapping_status` 只能按 `reference_only → mapped_pending_confirmation → confirmed_project_rule` 推进；来源冲突进入 `conflicted`。`confirmed_project_rule` 必须有项目规则 ID、项目来源、确认责任人和确认日期。它与 `evidence_type`、`resolution_status` 分开记录，不得用 `resolution_status: confirmed` 代替项目规则确认记录。

## 输出

### 1. 资料与范围

列出产品、API 版本、环境、来源 URL/路径、资料日期和不适用范围。

### 2. 规则映射矩阵

| reference_rule_id | project_rule_id | mapping_status | 适用范围 | 证据 | 影响 |
|---|---|---|---|---|---|
| ... | ... | ... | ... | ... | ... |

同时记录 `source_version_or_date`、`source_snapshot`（URL/路径/快照标识）和 `confirmation_owner/date`；没有项目确认时后两列为空并保持 `mapped_pending_confirmation`。

### 3. 测试补强

为每条新增或修订项给出稳定 ID、前置、数据、动作、逐步预期、独立观察、清理、来源和 `evidence_type`/`resolution_status`。使用 `REQ → RUL → TP → TC → SCN → RUN → BUG` 保持血缘。

### 4. 差异与待确认

列出外部规则与项目规则的差异、冲突、缺少的接口或观察能力、需要谁确认，以及对现有用例的影响。

### 5. 结论

分别给出：可直接作为参考、经映射后可采用、需要业务确认、当前阻塞。不要把“官方文档存在”写成“项目已实现或已执行通过”。
