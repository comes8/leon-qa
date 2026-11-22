# Binance API 外部规则参考层

状态：`external_reference`。本文件是本工作区 Binance 规则的权威归一化入口，用于补充 CEX 现货、USDⓈ-M 合约和 API 测试设计的外部参考，不等于公司项目规则，也不授权连接 Binance 生产环境。

核对日期：2026-11-22。使用前应重新查看官方文档和目标环境的 `exchangeInfo`；交易对、过滤器、接口参数、限流和产品能力可能变化。

## 来源登记

| 来源 | 用途 |
|---|---|
| [Spot General REST API Information](https://developers.binance.com/en/docs/products/spot/rest-api) | 基础地址、时间戳、签名、HTTP/错误、限流、超时和数据源 |
| [Spot Filters](https://developers.binance.com/en/docs/products/spot/filters) | 交易对、交易所和资产过滤器 |
| [Spot Trade REST API](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/trade) | 下单、撤单、撤改单、订单列表和账户查询 |
| [Spot User Data Streams](https://developers.binance.com/en/docs/products/spot/user-data-stream) | `executionReport`、余额事件和订单列表事件 |
| [USDⓈ-M Exchange Information](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data) | 合约状态、类型、精度、过滤器和限流 |
| [USDⓈ-M Trade REST API](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade) | 持仓模式、委托参数、条件单、只减仓和改单 |
| `N-Tester/backend/app/api/v1/Ntesterc_module/Ntesterc_web3/data/`、`leon-qa/backend/app/api/v1/Ntesterc_module/Ntesterc_web3/data/` | 历史/平台本地快照和初步测试规则 ID；不作为归一化入口 |

官方来源是产品参考的优先来源；本文件是工作区归一化快照；N-Tester 和 leon-qa 中的副本用于平台兼容和历史追溯。若来源版本不同，保留冲突并重新核对，不静默覆盖项目规则。

## 现货规则参考

### 产品与交易对配置

1. 测试开始前读取目标环境的 `GET /api/v3/exchangeInfo`，保存交易对状态、订单类型、时间有效类型、过滤器和限流快照。
2. 过滤器分为 symbol、exchange、asset 三类；测试数据不能硬编码成某个交易对永久有效的价格、数量或名义价值。
3. 价格、数量和名义价值使用 Decimal 或整数最小单位计算，保留输入精度、过滤器版本和计算截面。

### 下单、撤单和改单

| 规则 ID | 外部参考行为 | 建议测试方向 |
|---|---|---|
| `BIN-REF-SPOT-ORDER-01` | `POST /api/v3/order`、`GET /api/v3/order`、`DELETE /api/v3/order` 可用 symbol 与订单标识串联。 | 受理、成交、部分成交、撤单和查询的状态/数量链路；区分响应、终态和账务收敛。 |
| `BIN-REF-SPOT-CANCEL-01` | `cancelRestrictions` 可限制仅 `NEW` 或仅 `PARTIALLY_FILLED` 订单，条件不满足时撤单失败。 | 对两种允许状态和一个不匹配状态分别验证错误码、订单状态和资金效果。 |
| `BIN-REF-SPOT-AMEND-01` | `PUT /api/v3/order/amend/keepPriority` 用于减少现有开放订单数量，并声明不增加订单计数过滤器。 | 新数量必须大于 0 且小于原数量；核对剩余量、队列优先级语义和订单计数。 |
| `BIN-REF-SPOT-IDEMPOTENCY-01` | `clientOrderId` 用于关联订单；网络超时不能直接推出订单未创建。 | 超时后先按原标识查询，再决定是否补偿；不要用重复提交证明幂等。 |

### 过滤器

| 规则 ID | 规则 | 测试方向 |
|---|---|---|
| `BIN-REF-SPOT-FILTER-PRICE` | `PRICE_FILTER` 用 `minPrice`、`maxPrice`、`tickSize` 约束 price/stopPrice；字段为 0 时对应规则可禁用。 | 下界、上界、合法步长、非法步长、禁用字段。 |
| `BIN-REF-SPOT-FILTER-QTY` | `LOT_SIZE` 用 `minQty`、`maxQty`、`stepSize` 约束 quantity/icebergQty。 | 数量下界、上界、步长和超精度。 |
| `BIN-REF-SPOT-FILTER-NOTIONAL` | `MIN_NOTIONAL`/`NOTIONAL` 约束订单名义价值；市价适用范围和平均价窗口由过滤器字段决定。 | 限价/市价、边界值、平均价窗口和过滤器变化。 |
| `BIN-REF-SPOT-FILTER-COUNT` | `MAX_NUM_ORDERS` 约束账户在某交易对的开放订单数，普通和 algo 订单均可能计入。 | 达到上限、撤单释放计数、订单列表对计数的影响。 |

### 认证、超时、限流和事件

1. Binance 支持 HMAC、RSA 和 Ed25519；signed 请求要核对 timestamp/recvWindow、签名原文和 API Key 权限。密钥只从测试环境的 Secret 引用，不能进入 Prompt、用例或报告。
2. `-1007` 或 HTTP 5XX 表示执行状态可能未知，不能直接判定失败；应按原订单标识查询，并结合用户数据流确认。
3. HTTP 429 需要退避；持续违反限流可能导致 418，测试要记录响应头、Retry-After、请求权重和订单计数，不把重试次数写成通用常量。
4. `executionReport` 是订单执行事件；`outboundAccountPosition` 和 `balanceUpdate` 提供账户变化观察；订单列表还可能有 `listStatus`。REST 查询与事件流要独立核对，不以单一来源代替另一来源。
5. 事件时间、成交量、累计成交和累计成交额要保留原字段及单位；平均成交价等派生值必须写明公式和截面。

## USDⓈ-M 合约规则参考

1. 测试开始前读取 `GET /fapi/v1/exchangeInfo`，登记 symbol 状态、`contractType`、基础/报价/保证金资产、精度、过滤器和限流。
2. 持仓模式是账户级配置：`dualSidePosition=true` 表示 Hedge Mode，`false` 表示 One-way Mode；有开放订单或持仓时切换模式会被拒绝。模式切换前置必须单独造数和清理。
3. One-way Mode 使用 `positionSide=BOTH`；Hedge Mode 使用 `LONG` 或 `SHORT`，并按产品规则要求显式传递方向。
4. `reduceOnly` 不能在 Hedge Mode 发送，也不能与 `closePosition=true` 同时使用；使用 `closePosition=true` 的条件单不能同时发送 quantity。只减仓仍要按实际成交量、持仓方向、模式和事件顺序核对，不把接口接受当作仓位已减少。
5. LIMIT、MARKET、STOP/TAKE_PROFIT、STOP_MARKET/TAKE_PROFIT_MARKET 和 TRAILING_STOP_MARKET 的必需参数不同；`timeInForce`、触发价、workingType、priceProtect 和 GTD 的语义按当前接口版本核对。
6. 合约改单和现货 `keepPriority` 语义不同：USDⓈ-M 当前文档说明 LIMIT 改单会重新排入撮合队列。现货与合约不能共用一个“改单保留优先级”的预期。
7. `selfTradePreventionMode` 只在文档指定的 timeInForce 下生效；条件单、触发单和普通限价单必须分开设计。

## 映射到公司项目

外部规则必须经过映射才能进入公司测试预期：

| 字段 | 要求 |
|---|---|
| `reference_rule_id` | 本文件或本地 Binance 快照的规则 ID |
| `project_rule_id` | 项目需求/接口/配置中的规则 ID；没有则留空 |
| `product_scope` | Spot、USDⓈ-M、其他合约或 DEX；不可混用 |
| `mapping_status` | `reference_only`、`mapped_pending_confirmation`、`confirmed_project_rule`、`conflicted` |
| `environment` | local_mock、QA、testnet 或其他授权环境 |
| `evidence` | 来源版本、接口响应、事件、日志或人工确认记录 |
| `test_impact` | 新增测试点、修改预期、阻塞项或仅作背景参考 |

Binance 资料可以帮助发现覆盖项和设计判据，但不会自动改变公司项目的字段、状态、手续费、精度、资金账务、撮合裁决或 DEX 规则。

### 映射状态转换

```text
reference_only
      ↓ 补齐项目规则、产品范围和证据
mapped_pending_confirmation
      ├─ 责任人确认 → confirmed_project_rule
      └─ 来源冲突   → conflicted
```

`confirmed_project_rule` 必须同时有 `project_rule_id`、项目来源、确认人/责任人和确认日期。`conflicted` 不能作为当前有效项目硬断言；`resolution_status` 仍需独立记录确认、待确认、冲突或阻塞。

## 推荐补强场景

- 交易对配置变更后，过滤器快照和已生成用例的兼容性。
- 请求超时、HTTP 5XX、重复提交和事件延迟下的状态确认。
- cancelRestrictions、现货保留优先级改单、订单计数和自成交防护。
- Spot REST、`executionReport`、余额事件和订单列表事件的交叉一致性。
- USDⓈ-M 单向/双向持仓切换门禁、只减仓/closePosition 互斥、条件单触发和改单重排队。
- 429/418 退避、Retry-After、请求权重和订单计数的隔离验证。
