# 币安现货 · 签名、时间窗口、超时和限流

资料类型为 Binance Spot 官方参考，核对日期为 2026-11-20。

| 规则 ID | 规则和测试方向 |
| --- | --- |
| BIN-SPOT-AUTH-01 | SIGNED 请求检查签名与 timestamp、recvWindow。以测试凭据覆盖有效、失效、缺失鉴权和时间窗口边界。按项目选择 HMAC、RSA 或 Ed25519。 |
| BIN-SPOT-TIMEOUT-01 | -1007 表示执行状态未知，不能据此断定订单失败。用原订单标识查询并结合用户数据流核实后处理。 |
| BIN-SPOT-RATE-01 | 限流以所选环境和接口规则为准，核对权重、429 和 Retry-After。负载验证单独准备隔离环境。 |

API 密钥在运行时从测试环境引用，模型输入、用例导出和报告使用脱敏内容。

来源 https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md
