# 币安现货 · 订单状态与用户数据流

资料类型为 Binance Spot 官方参考，核对日期为 2026-11-20。

| 规则 ID | 规则和测试方向 |
| --- | --- |
| BIN-SPOT-STATE-01 | NEW、PARTIALLY_FILLED、FILLED、CANCELED、EXPIRED 等状态按当前订单类型和交易规则校验。先确认受理，再确认最终状态。 |
| BIN-SPOT-EVENT-01 | 用户流 executionReport 含订单与执行信息。用订单标识关联 REST 查询与事件，核对累计成交，保留断线、重复或延迟事件的观察证据。 |

WebSocket 增量顺序和账户余额更新语义应按当前协议核对。缺少订阅客户端时把事件验证标为待接入，HTTP 查询只证明查询结果。

来源 https://github.com/binance/binance-spot-api-docs/blob/master/enums.md
来源 https://github.com/binance/binance-spot-api-docs/blob/master/user-data-stream.md
