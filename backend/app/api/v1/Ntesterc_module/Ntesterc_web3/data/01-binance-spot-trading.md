# 币安现货 · 下单、查单和撤单

资料类型为 Binance Spot 官方参考，核对日期为 2026-11-20。用于币安现货接口设计参考，公司项目和本地模拟要确认字段与规则映射。

| 规则 ID | 规则和测试方向 |
| --- | --- |
| BIN-SPOT-ORDER-01 | 下单 POST /api/v3/order，查单 GET /api/v3/order，撤单 DELETE /api/v3/order。按 symbol 和订单标识串联请求，核对原始数量 origQty、累计成交 executedQty 和 status。 |
| BIN-SPOT-CANCEL-01 | cancelRestrictions 支持 ONLY_NEW 和 ONLY_PARTIALLY_FILLED。分别验证匹配和不匹配订单状态的撤单行为。 |
| BIN-SPOT-IDENTITY-01 | clientOrderId 用于关联委托，不能把 open-order 唯一性推断为永久幂等。提交超时先按原订单标识查询。 |

资金冻结、手续费、释放时限和可重复撮合数据需引用项目的账务规则。行情价格与数量需来自选定测试环境。

来源 https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md
