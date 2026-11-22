# Web3 多业务模拟 · 会话与现货规则

适用范围为 Leon QA 的 /Ntesterc_web3/mock 本机模拟 v1。每条用例先 POST /sessions，提取 session_id，各场景独立。

| 规则 ID | 已确认的模拟行为 |
| --- | --- |
| SIM-SESSION-01 | 创建会话返回 201 和 environment=local_mock。初始现货可用报价币 1000，合约多仓 5，资金钱包 100，合约钱包 0。 |
| SIM-SPOT-01 | 以 quantity=5、price=10 下单返回 201、NEW、origQty=5、executedQty=0、remainingFrozen=50。按 orderId 查同一订单。 |
| SIM-SPOT-02 | 显式模拟 fills 数量 2，返回 PARTIALLY_FILLED、executedQty=2、remainingFrozen=30。DELETE 撤余单后为 CANCELED，executedQty=2、remainingFrozen=0。 |
| SIM-LEDGER-01 | 上述订单的独立账务查询显示 tradeQuantity=2、spent=20、released=30，账户 free=980、locked=0。 |
| SIM-SPOT-ERROR-01 | 未知订单返回 404 / ORDER_NOT_FOUND。撤已撤或全成订单返回 409 / ORDER_NOT_CANCELABLE。非法 quantity、price 返回 400 / INVALID_AMOUNT。 |
| SIM-SPOT-PRECISION-01 | 模拟价格和数量均要求 0.01 步长，不满足返回 400 / PRECISION_ERROR。资金不足返回 400 / INSUFFICIENT_BALANCE。 |

amount 字段以八位小数字符串返回。fills 为模拟撮合控制接口。该样例无手续费。GET 查单、GET 查流水、POST fills、DELETE 撤单的成功状态码均为 200，POST 下单为 201。下单、fills、撤单和查单均返回 orderId、status、origQty、executedQty、remainingFrozen。订单数据与资金按 session_id 隔离，HTTP 201 创建会话后即刻可用。

表内订单业务错误响应为 {"code":"规则中的错误码"}。缺失或无法解析的金额由参数校验返回 HTTP 400 / detail=INVALID_AMOUNT。未知订单可直接将查询步骤的 path_variables.order_id 设置为 missing-{{run_id}}，无需额外造数接口。报价币余额为纯模拟的定向买入场景，不包含 symbol、side 或真实撮合规则。
