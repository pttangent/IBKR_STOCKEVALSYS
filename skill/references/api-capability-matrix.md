# 基本面 API 能力与返回格式核验

核验日期：2026-08-13；实测标的：TER、KLAC。本文是当前账号和当前环境的可重播快照，不是供应商永久保证。

## SEC / EDGAR

请求方式：GET；data.sec.gov 使用项目 User-Agent，通常不需要 API key。

| 接口 | 实测 | 返回结构 |
|---|---:|---|
| company_tickers.json | 200 | JSON 对象；键为序号，值含 ticker、cik_str、title |
| company_tickers_exchange.json | 200 | JSON 对象；含 ticker、cik、exchange |
| submissions/CIK##########.json | 200 | JSON；公司元数据和 filings.recent，含 accession、form、filed、period、primaryDocument |
| api/xbrl/companyfacts/CIK##########.json | 200 | JSON；facts → taxonomy → tag → units |
| api/xbrl/companyconcept/.../us-gaap/AccountsPayableCurrent.json | 200 | 单一 taxonomy/tag 的 units、label、description、历史事实 |
| api/xbrl/frames/.../CY2025Q4I.json | 200 | JSON；data 数组，适合跨公司同一概念比较 |
| xbrl/companyfacts.zip | 200，可达 | 批量压缩文件；适合夜间仓库 |
| bulkdata/submissions.zip | 200，可达 | 批量申报历史；适合夜间仓库 |
| Archives/edgar/data/ | 目录不可依赖 | 目录索引不是个股数据接口；应使用具体 accession/filing URL |
| 个别 10-Q archive | 200 | 原始 HTML、XBRL、附件和新闻稿 |
| SEC API 文档及 EDGAR 存取说明 | 200 | 文档页面 |

SEC 是申报事实主来源。filed 是可用时间戳；不能把当前修订后的事实直接当成历史时点事实。

## SimFin

授权方式：

Authorization: api-key <SIMFIN_API_KEY>

当前 compact 请求格式：

https://backend.simfin.com/api/v3/companies/general/compact?ticker=TER

https://backend.simfin.com/api/v3/companies/statements/compact?ticker=TER&statements=PL,BS,CF,DERIVED&period=Q1,Q2,Q3,Q4,FY,H1,H2,NINE_MONTH&asreported=true&details=true

https://backend.simfin.com/api/v3/companies/common-shares-outstanding?ticker=TER&end=2026-08-13

| 接口 | 实测 | 返回结构 |
|---|---:|---|
| companies/list | 200 | 大型列表；用于 SimFinId/universe 映射，必须缓存 |
| companies/general | 404 | 附件中的非 compact 路由不可用 |
| companies/statements | 404 | 附件中的非 compact 路由不可用 |
| companies/general/compact | 200 | columns + data 矩阵；公司描述、行业、财年 |
| companies/statements/compact | 200 | 对象数组；含公司身份、currency、statements、columns/data |
| companies/common-shares-outstanding | 200 | 数组；含 pid、endDate、value |
| prod.simfin.com 的 general/compact | 200 | 可达；生产请求保留实际 base_url |

本地 Python simfin 包当前未安装。Bulk download 是账户下载流程，不是同一 HTTP API，本次不列为已验证接口。SimFin 只作二级核对，不能覆盖 SEC，也不自动提供严格 point-in-time 证明。请求必须串行并缓存；429 要退避。

## Alpha Vantage

请求格式：

GET https://www.alphavantage.co/query?function=FUNCTION&symbol=KLAC&apikey=KEY

| function | 实测 | 返回结构 |
|---|---:|---|
| OVERVIEW | 200 | 单一 JSON 对象；Symbol、Name、CIK、Exchange、MarketCapitalization 等 |
| INCOME_STATEMENT | 200 | symbol、annualReports、quarterlyReports 数组 |
| BALANCE_SHEET | 200 | symbol、annualReports、quarterlyReports 数组 |
| CASH_FLOW | 200 | symbol、annualReports、quarterlyReports 数组 |
| SHARES_OUTSTANDING | 200 | symbol、status、data 数组 |
| EARNINGS | 200 | symbol、annualEarnings、quarterlyEarnings；含 actual/estimate/surprise |
| EARNINGS_ESTIMATES | 200 | symbol、estimates；含 EPS/收入预测、分析师数量和修订字段 |
| EARNINGS_CALENDAR | 200 | CSV；本次返回 72 行，不能按 JSON 解析 |
| LISTING_STATUS | 200 | CSV；本次返回约 1 MB，不能按 JSON 解析 |

当前 key 对 KLAC 的九个端点均返回有效结构。免费配额仍然有限；遇到 Information、Note、空 CSV 或字段不足时必须标记为受限，不能只看 HTTP 200。

## Finnhub

请求格式：

GET https://finnhub.io/api/v1/PATH?symbol=KLAC&token=TOKEN

也可以使用 X-Finnhub-Token header。

| 接口 | 实测 | 返回结构 |
|---|---:|---|
| stock/profile2 | 200 | 单对象；公司名、交易所、行业、IPO、市场值、股数 |
| stock/peers | 200 | 字符串数组 |
| stock/metric?metric=all | 200 | metric、metricType、series、symbol |
| company-news | 200 | 新闻数组；headline、datetime、source、url、summary |
| stock/earnings | 200 | earnings 数组；季度 actual/estimate/surprise |
| calendar/earnings | 200 | earningsCalendar 数组 |
| stock/symbol?exchange=US | 200 | 大型标的数组，约 7 MB；必须缓存 |
| stock/financials-reported | 200 | cik、data、symbol；申报财务交叉核对 |
| stock/financials?statement=ic&freq=quarterly | 403 | standardized financials 当前账户未授权 |

Finnhub reported financials、metric、earnings、calendar 可作二级核对；standardized financials 不能使用。Finnhub 数值不得覆盖 SEC，也不能静默修复申报期间不一致。

## IBKR Reuters Fundamentals

已实际调用 ReportsFinSummary、ReportsFinStatements、ReportsOwnership，返回 10358 fundamentals data is not allowed。endpoint 存在，但当前 IBKR 账户没有 Reuters Fundamentals entitlement；不能把它写成公司基本面缺失。

## 系统路由

1. SEC / 公司 IR：申报事实、filing、GAAP、原始证据。
2. SimFin：标准化报表和跨公司核对。
3. Alpha Vantage：财务补充、earnings history、estimates、revision snapshot。
4. Finnhub：metadata、peers、earnings、calendar、news、reported financials。
5. IBKR Reuters：取得 entitlement 后才加入基本面交叉核对。

任何 200 但 payload 为空、CSV 没有数据行、返回 Information/Note、401、403、404 或字段不完整的响应，都必须保留原始状态，不能转换成 FOUND。

## Alpaca

Trading API 请求使用 headers：APCA-API-KEY-ID 与 APCA-API-SECRET-KEY。市场数据基础地址为 https://data.alpaca.markets，交易/资产基础地址为 https://paper-api.alpaca.markets/v2。本次只执行 GET 请求。

| 接口 | 实测 | 返回结构与用途 |
|---|---:|---|
| GET /v2/account | 200 | 账户对象；status、buying_power、options_approved_level、options_trading_level 等 |
| GET /v2/assets/KLAC | 200 | 单一资产对象；symbol、exchange、tradable、shortable、fractionable 等 |
| GET /v2/clock | 200 | is_open、next_open、next_close、timestamp |
| GET /v2/calendar | 200 | 交易日数组；本次 6 个交易日 |
| GET /v2/stocks/AAPL/snapshot?feed=iex | 200 | latestTrade、latestQuote、minuteBar、dailyBar、prevDailyBar |
| GET /v2/stocks/AAPL/trades/latest?feed=iex | 200 | symbol + trade；含价格、数量、交易所、时间 |
| GET /v2/stocks/AAPL/quotes/latest?feed=iex | 200 | symbol + quote；含 bid/ask、数量、交易所、时间 |
| GET /v2/stocks/AAPL/bars | 200 | bars、next_page_token、symbol；支持分页 |
| GET /v2/stocks/snapshots | 200 | 按 symbol 映射的多标的 snapshot |
| GET /v1beta1/options/snapshots/AAPL?feed=indicative | 200 | snapshots 映射、next_page_token；含 latestQuote/latestTrade/dailyBar/minuteBar |
| GET /v2/options/contracts | 200 | option_contracts、next_page_token；含合约、expiry、strike、call/put、underlying |
| GET /v1beta1/news | 200 | news、next_page_token；含 headline、author、created_at、updated_at、symbols、content/url |
| GET /v1/corporate-actions | 200 | corporate_actions、next_page_token；股息、拆股、并购、spin-off 等 |
| 股票 feed=sip | 403 | 当前 Basic 账号没有全市场 SIP 权限；IEX 可用 |
| 期权 feed=opra | 403 | 当前没有 OPRA 权限；indicative 可用 |
| GET /v1beta1/options/bars | 403 | 当前 Basic 账号不能取得历史期权 bars |

期权快照本次取 20 个 indicative 合约：20/20 有 latestQuote，18/20 有 latestTrade，但 0/20 有 impliedVolatility，0/20 有 greeks。即使官方接口模型支持这些字段，也不能在当前账号响应缺失时自行补造 IV 或 Greeks。

结论：Alpaca 可作为 IEX 股票行情、资产/证券主表、新闻、公司行动、期权合约目录和 indicative 期权 quote/trade 补充；不能作为当前账号的全市场 SIP、OPRA、历史期权 bars 或可靠 IV/Greeks 主来源，也不提供本项目所需的财务三表/基本面事实。
