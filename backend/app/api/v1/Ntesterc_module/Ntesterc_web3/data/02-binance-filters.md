# 币安现货 · 精度与下单过滤器

资料类型为 Binance Spot 官方参考，核对日期为 2026-11-20。测试前读取选定环境的 exchangeInfo。

| 规则 ID | 规则和测试方向 |
| --- | --- |
| BIN-SPOT-FILTER-01 | PRICE_FILTER 提供 minPrice、maxPrice、tickSize。核对启用规则的上下界与步长，字段为 0 时按文档判断该规则是否禁用。 |
| BIN-SPOT-FILTER-02 | LOT_SIZE 提供 minQty、maxQty、stepSize。覆盖上下界、合法步长和超精度输入。 |
| BIN-SPOT-FILTER-03 | MIN_NOTIONAL 与 NOTIONAL 决定名义价值限制，市价适用开关与平均价窗口需按过滤器核对。 |

用 Decimal 或整数最小单位比较。交易对的配置可能变化，知识库中的示例数字不能当作固定阈值。

来源 https://github.com/binance/binance-spot-api-docs/blob/master/filters.md
