# Web3 多业务模拟 · 合约、资金幂等和 DEX

适用范围为 Leon QA 的 /Ntesterc_web3/mock 本机模拟 v1。每个用例先创建独立 session_id，金额和数量按 Decimal 比较。GET 查询成功码均为 200，状态在当前模拟接口中立即可查询。clientId 幂等范围仅限当前 session_id，不同会话的数据独立。

| 规则 ID | 已确认的模拟行为 |
| --- | --- |
| SIM-FUTURES-01 | 初始 LONG 数量 5，POST futures/position 用 quantity=2、reduceOnly=true 后返回 HTTP 200、side=LONG、quantity=3，再 GET 核对。quantity 超过持仓、非正数或 reduceOnly 不是 true，返回 400 / REDUCE_ONLY_REJECTED。 |
| SIM-FUNDS-01 | 钱包初始 100，合约钱包 0。POST funds/transfers 用 clientId=同一用例唯一编号、quantity=10，返回 HTTP 201、status=SUCCESS、transferId 和 clientId。再次相同 clientId 和 quantity 返回 200 且 transferId 相同。GET 显示 wallet=90、futuresWallet=10、transferCount=1。 |
| SIM-FUNDS-02 | 相同 clientId 改数量返回 409 / IDEMPOTENCY_CONFLICT。金额超过钱包返回 400 / INSUFFICIENT_BALANCE。 |
| SIM-DEX-01 | GET dex/quote 返回 chainId=31337、quoteId=fixture-quote、minAmountOut=900、amountOut=950。POST dex/swaps 携带此报价、链和 minAmountOut=900 返回 201 和 transactionHash。GET 对应 receipts 返回 status=0x1、amountOut=950、balanceDelta=950。 |
| SIM-DEX-02 | chainId 或 quoteId 不匹配返回 400 / INVALID_QUOTE。minAmountOut 超过 950 返回 400 / SLIPPAGE_EXCEEDED。 |

该模拟的回执和余额来自合成状态，实际 DEX 的授权、签名、区块确认、代币费用和索引一致性需在对应项目另行接入。

模拟接口字段约定：资金方向固定 wallet → futuresWallet，不接收 from/to；当前幂等比较仅含 clientId 和 quantity。GET funds/transfers 不返回 transferId，只返回两个余额和 transferCount，因此不能对该查询断言 transferId。表内业务错误响应格式为 {"code":"规则中的错误码"}，缺失或无法解析的金额由参数校验返回 HTTP 400 / detail=INVALID_AMOUNT。DEX 报价中的 chainId 为整数，quoteId 为字符串，minAmountOut 和 amountOut 分别为字符串 "900"、"950"；兑换体接收同一报价的三个字段，需优先从报价响应提取。合约 reduceOnly 为 JSON 布尔值，false 的拒绝状态码为 400，拒绝不改变仓位。
