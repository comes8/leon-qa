# 币安 USDⓈ-M 合约 · 下单、持仓模式和只减仓

资料类型为 Binance USDⓈ-M 官方参考，核对日期为 2026-11-20。

| 规则 ID | 规则和测试方向 |
| --- | --- |
| BIN-UM-ORDER-01 | POST /fapi/v1/order 创建订单，GET /fapi/v1/order 查询订单。测试时核对实际成交与仓位变化，费用与损益引用账户和交易资料。 |
| BIN-UM-POSITION-01 | 单向持仓 positionSide 默认 BOTH，双向持仓使用 LONG 或 SHORT，双向模式需传方向。覆盖开平仓、方向和模式组合。 |
| BIN-UM-REDUCE-01 | reduceOnly 在双向模式不可传。quantity 与 closePosition=true 存在互斥约定，触发类订单另查对应接口规则。 |

逐仓和全仓、杠杆档位、资金费、保证金、强平及超额只减仓的预期分别确认。避免将普通单、条件单或其他合约产品的规则混用。

来源 https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade
