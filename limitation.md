# Free-tier、MCP 与数据源限制

最后核对：2026-08-11。本文记录本项目在免费账户、免费 API 层和当前 IBKR/TWS 配置下的真实边界。供应商可能随时调整配额、保留期、权限和端点；运行报告必须保存 `provider`、`requested_at`、`as_of`、`entitlement_status` 和错误信息，不能把“没有返回数据”解释成“市场没有数据”。

## 1. 先看结论

| 能力 | 当前可用定位 | 免费层/当前配置的关键限制 | 报告中允许的表述 |
|---|---|---|---|
| 股票日线、基本面、公告 | SEC + IR + IBKR/Massive/yfinance 交叉 | 不同源的收盘时点、调整规则和延迟不同 | “截至某时点，某源显示……” |
| 股票 1 分钟 | IBKR 优先，Massive/yfinance 交叉 | IBKR 小周期 pacing；yfinance 日内保留期短；Massive 受计划、日期和请求配额约束 | 标明每一段实际来源和最后完整 bar |
| 股票 10 秒 | IBKR 历史短周期 | 不是逐笔；只能按 IBKR 可返回的近期窗口取数 | “10 秒 bar 观察”，不能称逐笔成交 |
| Tick-by-tick / Time & Sales | IBKR 仅在相应市场数据权限和请求路径可用 | 历史 tick 不是本地雷达的回放；历史 tick 按交易日请求，且需要 L1 权限 | “tick 级/雷达样本”，不推断机构身份 |
| 期权合约目录 | IBKR 链参数 + Massive reference + yfinance 当前链 | 目录只有到期日/行权价/类型，不代表有报价或成交 | “合约发现证据” |
| 期权历史日线 | Massive 优先，IBKR 可补选定合约 | 免费层不是完整历史链数据库；需要逐合约、逐到期、逐 strike 设计请求 | “选定合约的历史 OHLC” |
| 期权实时/延迟链 | IBKR 优先，但取决于 OPRA/市场数据权限；Massive 免费层不作为实时链 | 没有权限时不能靠代码修复；链参数成功也不等于报价成功 | “链不可用/延迟/昨日值”，明确证据等级 |
| 期权 Greeks、IV、OI、快照 | 当前免费配置不作硬依赖 | 没有稳定的免费实时 Greeks/OI 快照；IV 可由可用价格自行反推，但会受价差、时间点和模型误差影响 | “价格反推 IV 近似”，不能冒充供应商 Greeks |
| 新闻 | IBKR News + SEC/IR，其他源补充 | IBKR 新闻依赖已启用 provider、标的 conId 和时间窗口；文章正文未必有权限 | 标题、时间、provider、article ID、正文可用性分开记录 |
| Kelly/仓位 | 本地 deterministic engine | 期权证据不足时只能做风险 haircut/情景，不伪造胜率；OOS 样本不足时输出低置信度 | full/half/quarter 作为情景结果，不是自动下单 |

## 2. 数据源与 API 的免费限制

### 2.1 IBKR TWS API / 本地 IBKR MCP

MCP 本身是本地开源/自托管适配层，没有一个独立的“免费行情额度”。它把请求转给 TWS/IB Gateway；实际限制来自 IBKR 账户、交易所行情订阅、TWS API pacing、市场数据线路和本机连接状态。

官方文档：

- [TWS API 文档索引](https://www.interactivebrokers.com/docs/tws-api/doc/introduction)
- [请求市场数据](https://www.interactivebrokers.com/docs/tws-api/doc/quick-start/requesting-market-data)
- [历史市场数据](https://www.interactivebrokers.com/docs/tws-api/market_data.html)
- [历史数据 pacing](https://www.interactivebrokers.com/docs/tws-api/historical_limitations.html)
- [期权 Greeks](https://www.interactivebrokers.com/docs/tws-api/option_computations.html)
- [Tick-by-tick 数据](https://www.interactivebrokers.com/docs/tws-api/tick_data.html)
- [IBKR News](https://interactivebrokers.github.io/tws-api/news.html)

#### 股票与历史 K 线

- 通过 API 获取实时股票报价通常需要对应市场数据订阅；TWS 界面能看到某数据，不保证 API 账户也有同等权限。没有实时权限时，延迟数据、冻结数据或空字段都可能出现。
- IBKR 对历史小周期请求实施 pacing。官方规则包括：相同请求在短时间内重复会被拒绝；相同合约/交易所/tick type 在 2 秒内过多请求会被拒绝；10 分钟内历史请求过多会触发限制；`BID_ASK` 请求按两次计数。工程上必须限速、缓存、分块、指数退避，不能用并发轰炸。
- 30 秒及以下的历史 bars 不是无限回溯资源；IBKR 文档说明超过约 6 个月的小周期 bars 不可用。项目的 1 分钟和 10 秒窗口因此是“近期观察窗口”，不是永久历史数据库。
- `reqRealTimeBars` 的原生实时 bar 粒度是 5 秒。1 秒、10 秒历史 bar 与 5 秒实时 bar、Time & Sales 是不同接口，不能混称。
- 历史成交量可能经过过滤或调整，且与实时成交量存在差异；跨源比对时要比对时间戳、bar 完整状态和口径。

#### 期权：必须区分六类能力

| 期权能力 | IBKR 当前项目的含义 | 限制 |
|---|---|---|
| 链参数/合约发现 | 查询到期日、行权价、权利方向、交易所和 conId | 只是“有哪些合约”；没有报价、成交、OI 或 Greeks 的保证 |
| 当前链报价 | `ibkr_get_option_chain` 对选定到期日和 strike 返回可取得的 last/high/low/volume 等 | 依赖期权行情权限、合约 qualification 和 TWS 状态；盘前可能是昨日值；缺权限不能靠重试制造实时数据 |
| 历史期权 bars | 项目可对选定合约取历史日线/选定分钟 bars，再用 call/put 配对 | 不是完整历史链；请求量随 expiry × strike × call/put 线性增加，受 pacing 和可用历史限制 |
| Greeks/IV | 有可靠期权价格时，本地可用 Black-Scholes 数值 IV 或 ATM straddle 近似反推 | 反推值依赖正股 S、时间戳、无风险利率、股息、价差和最后成交；不等于 IBKR 实时 Greeks；无报价时不能算 |
| OI | 只有数据源明确返回且时间口径正确时才能使用 | 不能用 volume、bars 或链目录替代 OI；盘中 OI 通常不是实时变量 |
| Tick / 逐笔期权 | 需要对应 L1/期权行情权限及 TWS 接口 | 本项目的 stock radar 不等于期权逐笔历史库；没有权限时必须降级为选定合约 bars 或不输出 |

当前研究流程是：IBKR 优先尝试当前链/选定合约；若没有实时期权权限，改用 Massive 的历史 EOD/分钟能力和 yfinance 的当前链做补充；所有结果标注来源和时间。不会把 IBKR 链参数成功误报为“完整期权链报价已成功”。

#### 历史 tick 与本地雷达

- IBKR 历史 tick 不是“调用一次返回任意长度的全市场逐笔”。历史 tick 按单个交易日请求，返回数量和边界受接口限制；官方文档还要求相应 Level 1 Top-of-Book 权限。
- 1 秒/5 秒/10 秒 bar 是一段时间内的聚合 OHLCV/count。`count` 只能作为成交活跃度代理，不是逐笔成交方向，也不能识别大户或机构。
- SQLite radar 只保存本地雷达进程实际运行期间收到的样本。它不会凭空补回雷达未运行时的历史；tick 的主动买卖方向是本地 bid/ask、uptick 等启发式标记，不是交易所确认的 aggressor side。
- 一个打印可能被拆分、合并、重复或延迟；不同数据源的成交量、时间戳和过滤规则也可能不同。因此微观结构报告只能使用“样本观察、方向性证据、置信度”，不能写成完整订单流事实。

### 2.2 Massive REST / Options Basic

官方页面：[Massive Options pricing](https://massive.com/pricing?product=options)；接口文档：[Options REST overview](https://massive.com/docs/rest/options/overview)、[contracts](https://massive.com/docs/rest/options/contracts/all-contracts)、[custom bars](https://massive.com/docs/rest/options/aggregates/custom-bars)。

当前免费 Options Basic 页面列出的能力包括：

- $0/月、个人使用；
- 5 API calls/minute；
- 2 年历史数据、全美期权 ticker 覆盖；
- End-of-Day data、reference data、corporate actions、technical indicators；
- 页面当前也列出 minute aggregates，但实际能否访问某 endpoint 仍以账号返回、产品许可和 API 状态为准。

免费期权层页面没有把以下能力列为 Basic 的保证项，而这些项目在更高层明确列出：实时数据、实时 Greeks/IV、每日 OI、snapshot、second aggregates、trades、quotes、WebSockets 和 flat files。因此本项目不把它们作为免费流程的硬依赖。

对期权分析的具体影响：

1. `reference/contracts` 适合发现 expiry、strike、C/P 和 ticker，不等于有历史或实时价格。
2. 历史期权 OHLC 需要逐合约请求；要做 ATM、5% OTM put、5% OTM call、front/back term structure，至少要请求多个合约，再配对同日正股 bars。
3. 5 次/分钟意味着“一个标的一次完整历史重建”必须排队、缓存和分批；不能在一轮报告里无上限遍历所有 strike/expiry。
4. 没有供应商 Greeks/IV/OI 时，只有在 call、put、正股和 DTE 同日对齐后，才可计算价格反推 IV；若使用 last 而不是 bid/ask 中间价，必须降低置信度。
5. 当日查询返回 0 根不等于标的没有交易，可能是免费层 EOD 口径、数据尚未发布、日期/时区、认证、endpoint 许可或传输层问题。报告必须保存 HTTP 状态、响应体摘要和请求日期。

### 2.3 yfinance / Yahoo Finance 非官方接口

官方项目文档：[yfinance download](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html)、[项目免责声明](https://ranaroussi.github.io/yfinance/index.html)。

- yfinance 是对 Yahoo Finance 网页/API 的开源封装，不是 Yahoo 官方授权的交易所数据接口；项目文档明确提示不保证由 Yahoo 背书或审核，适合研究/教育和个人使用。
- 日内数据不能延伸到最近 60 天以前。1 分钟数据的实际 Yahoo 保留窗口通常更短（本项目按运行时返回动态判断，常见约 7 天），不可把“60 天”当作 1 分钟固定保留期。
- 没有稳定的 SLA、实时性、完整性或固定请求配额保证；可能遇到限流、空结果、cookie/crumb 变化、部分交易日缺失或分钟边界差异。
- `Ticker.options`/期权链更适合作为当前链的补充观察，不能当成历史期权链、历史 OI 或实时 Greeks 数据库。
- yfinance 只作为 Massive 失败时的补充/交叉校验，不覆盖 IBKR 的权限缺口，也不应覆盖 primary SEC/IR 事实。

### 2.4 SEC EDGAR

官方文档：[EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)、[SEC Developer FAQs](https://www.sec.gov/os/accessing-edgar-data)。

- `data.sec.gov` 的 submissions 和 XBRL API 不要求 API key；必须提供真实、可联系的 User-Agent（项目模板使用 `SEC_USER_AGENT`）。
- SEC 公共服务有公平使用、自动化访问和速率约束；不要并发抓取、伪装身份或绕过拒绝。大批量历史数据应优先使用官方 nightly bulk ZIP。
- submissions/XBRL 有处理延迟，且 filing facts 可能在申报后出现修订或上下文差异。回测和历史报告必须按 filing acceptance time / `as_of` 截断，不能把今天才知道的修订值回填到过去。
- SEC 是基本面和监管事实源，不提供实时股票/期权报价，也不提供期权 Greeks、OI 或交易逐笔。

### 2.5 FRED / ALFRED

官方文档：[FRED API overview](https://fred.stlouisfed.org/docs/api/fred/overview.html)、[API keys](https://fred.stlouisfed.org/docs/api/fred/v2/api_key.html)、[terms](https://fred.stlouisfed.org/docs/api/terms_of_use.html)、[real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html)。

- 每个 web service request 需要 FRED API key；项目使用 `FRED_API_KEY`，不应写入仓库。
- FRED/ALFRED 允许查询 vintage/realtime period，但宏观序列可能修订。研究回测必须使用 `realtime_start`/`realtime_end` 或 vintage date 做 point-in-time 截断。
- 官方条款允许 FRED 调整 bandwidth/transaction limits，且不承诺永久可用；项目不把未取到的宏观数据静默当作 0。
- FRED 是宏观背景，不是个股实时价格、期权链或逐笔数据源。

### 2.6 Alpha Vantage

官方说明：[Customer Support](https://www.alphavantage.co/support/)、[Premium API](https://www.alphavantage.co/premium/)。

- 免费服务目前公开写明为最多 25 requests/day；超过标准限制或需要特定 premium endpoint 时必须升级。
- 免费额度按 API request 消耗，不按“一个报告”计数。 earnings estimates、calendar、transcript 等端点必须逐次检查返回状态，不能假设所有免费 key 都覆盖所有数据集。
- 适合低频补充共识/日历/电话会信息，不适合分钟级行情或高频轮询。缓存和按标的排队是默认要求。
- Alpha Vantage 的 consensus/estimate 不能替代 SEC 已披露事实；若与 primary source 冲突，报告必须分开呈现。

### 2.7 Finnhub

官方页面：[Finnhub pricing](https://finnhub.io/pricing)。

- 免费计划的具体 endpoint、分钟配额、历史深度和延迟以账户当前 pricing 页面为准；项目不把 Finnhub 当作期权实时/历史全链硬依赖。
- API key 只放在本地 `.env`；任何 401/403/429、空字段或 endpoint 不在计划内，都必须降级并记录。
- Finnhub 可以做新闻、公司资料或部分市场数据的补充，但不能覆盖 IBKR 的 TWS entitlement，也不能凭一个股票 endpoint 推断期权 Greeks/OI。

### 2.8 FINRA Reg SHO short-sale volume

官方目录：[FINRA Short Sale Volume Data](https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data)。

- 这是短卖成交量数据/流量代理，不是 short interest、借券库存、净空头仓位，也不是机构持仓。
- 数据按 FINRA 发布节奏提供，通常不是实时盘中指标；不能用来判断某一秒或某一笔成交是谁卖出。
- 本项目固定标注为 `SHORT_SALE_FLOW_PROXY`，只能作为量价和风险背景的一项弱证据。

### 2.9 Polymarket 公共市场数据

官方文档：[Polymarket API documentation](https://docs.polymarket.com/)。

- 公共 Gamma/CLOB 数据可用于读取市场和价格，但可用端点、速率限制、市场生命周期和历史深度以官方文档/运行返回为准。
- 市场价格是参与者定价，不是客观概率、公司预测或 SEC 事实；流动性不足、价差、结算规则和市场选择偏差都会影响解读。
- 本项目固定标注为 `MARKET_IMPLIED_EXPECTATION`，不把它混进财务事实或模型概率。

### 2.10 IR 网站与公开新闻

- 公司 IR 页面、新闻稿和 SEC filing 是 primary evidence，但没有统一 API、统一保留期或统一发布时间字段。
- 网页抓取可能受 robots、CDN、重定向、地区和临时维护影响；不能用一个失败的网页请求证明“没有新闻”。
- 新闻标题有重复转载和不同时间戳；项目应保留原始 URL、发布时间、抓取时间和来源，去重后仍保留 provider。

## 3. MCP 的边界：免费的是适配层，不是行情权限

本仓库的 `ibkr-mcp/` 是项目内版本化的 TWS API MCP。它的限制如下：

- 它不赠送 IBKR 市场数据、OPRA、L1、历史数据或新闻 provider 权限。
- 它默认连接本机 TWS/IB Gateway 的一个 socket；TWS 登录、端口、client ID、每日重认证、断线和同一账户的其他客户端都会影响可用性。
- 市场数据 lines、活动订阅数、历史请求 pacing 和本机资源是共享的；同时运行 radar、历史拉取、期权链和新闻会互相争用预算。
- MCP 工具返回空链、空 bars 或 `TWS client not connected` 时，必须先检查连接、contract qualification、权限、时间窗口、市场开闭市状态和 provider 错误；不能无限重试。
- 通用 MCP 源码可能包含账户/订单相关工具，但本项目的 stock-eval skill 研究流程是只读的，不会自动调用下单接口。部署时应使用只读账户/策略、禁用订单工具或在 MCP 层保留明确的 read-only policy。
- MCP 的 `get_option_chain_params` 成功只证明 underlying/链参数发现成功；`get_option_chain` 成功只证明某次请求返回了选定范围的链数据，不代表全市场、实时、完整 Greeks/OI。

## 4. 期权分析的免费可用范围

### 4.1 可以做什么

在数据确实返回且时间对齐时，本项目可以：

1. 用 IBKR 做当前/盘前链的选定 expiry、strike、C/P 观察。
2. 用 Massive reference 发现合约，再拉选定 call/put 的历史 EOD 或可用分钟 bars。
3. 用 yfinance 当前链做第三源 sanity check，但不当历史期权数据库。
4. 用配对的正股价格、DTE 和期权价格反推 ATM IV 近似、期限结构、put/call 价格关系和偏斜方向。
5. 把期权风险证据用于股票仓位 haircut、事件风险标注和止损距离，而不是用期权本身替代股票基本面。

### 4.2 不能保证什么

- 不能保证免费层有实时期权报价、完整 NBBO、实时 Greeks、实时 IV、盘中 OI、完整 snapshot、二级盘口或历史逐笔期权。
- 不能用 `last` 单点价格在没有 bid/ask、成交时间和流动性信息时生成高置信度 IV。
- 不能从一两个 ATM 合约推断整个 volatility surface；要做 skew/term structure，必须说明 strike、expiry、价格口径、样本数量和缺失合约。
- 不能用期权 volume 代替 OI，也不能用 OI 变化推断开仓/平仓方向而不掌握成交配对。
- 不能因为一个源失败就静默换成另一个源，并把结果写成同一时点。fallback 必须显示：`source_used`、`source_failed`、`data_timestamp`、`staleness` 和 `confidence`。

### 4.3 期权证据等级

| 等级 | 证据 | 可支持的结论 |
|---|---|---|
| A | 同一时点、有权限的 bid/ask/last/volume，call-put 和正股同步 | 近似 IV、价差、流动性和事件定价观察 |
| B | 同一日选定合约历史 OHLC + 配对正股 | 历史 IV 序列、期限/偏斜的方向性回溯 |
| C | 只有链目录或只有 last | 合约存在/价格线索；低置信度，不宜作仓位核心证据 |
| D | 只有第三方网页/搜索摘要 | 仅作线索，不能进入冻结证据包的硬事实层 |

## 5. 当前项目的默认 fallback 与失败处理

### 股票 bars

`IBKR → Massive → yfinance`。但 fallback 不是无条件替换：先比较请求日期、时区、交易日、bar 完整性和数据时间戳；缺一段就按日期分段标注来源，而不是把整段伪装成单一来源。

### 期权

`IBKR 当前链/选定合约 → Massive reference + 历史 bars → yfinance 当前链补充`。

- IBKR 有权限并返回有效 bid/ask/last：用于当前链证据。
- IBKR 无实时权限但历史 bars 可用：用于选定合约的历史价格/IV，不写成实时 Greeks。
- Massive 免费层可用：用于历史 EOD/允许的 aggregates 和合约目录，遵守 5 calls/minute。
- yfinance：仅补当前链或正股交叉，不覆盖历史期权、Greeks、OI 缺口。
- 三源都没有足够证据：报告仍可输出技术面、基本面和条件式场景，但期权章节必须写“未验证/低置信度”，Kelly 只能降低风险，不得虚构期权输入。

### 新闻与基本面

`SEC/IR primary → IBKR News → Alpha Vantage/Finnhub/其他补充`。新闻源的 headline、正文、时间和事件性质必须分开记录；免费新闻接口失败不能覆盖 SEC/IR 已确认事实。

## 6. 对报告、Kelly 和微观结构的直接影响

- 报告必须显示每个关键数值的 `as_of` 和来源；“最新价”“昨日收盘”“最后完整分钟”不能混为一个时点。
- 期权 IV 只能在输入价格有效时反推；如果使用近似公式或 last，写明“近似”和误差来源。
- 期权证据默认用于波动率/尾部风险 haircut，不自动产生方向性胜率 `p`。胜率仍来自策略定义和历史回测。
- Kelly 的 full/half/quarter 是不同风险预算情景。样本不足、OOS 未达标、期权输入缺失或数据跨源不同步时，仍可输出数值情景，但必须降低置信度、使用固定风险上限并说明不是已验证优势。
- `>=60` 总交易且 `>=30` OOS 是标准策略资格门槛；`>=20` 总交易且 `>=10` OOS 只能作为条件式战术参考；更少样本只能 exploratory，不能把 Kelly 当成统计可靠的最优比例。
- tick/秒 bar 只能描述“样本内的冲击、成交活跃度、买卖盘代理和价格响应”。不能据此确认大户、机构、内幕或真实主动买卖方向。
- 本项目只输出研究和条件式观察，不自动下单，不把报告中的仓位比例发送给 IBKR。

## 7. 运行前检查清单

1. 记录 `.env` 是否存在、但不要打印 secrets；确认 `.env.example` 不含真实 key。
2. 记录每个 provider 的 HTTP 状态、响应时间、数据最后时间戳、返回行数和错误摘要。
3. IBKR 先检查连接、账户模式、市场数据类型、contract qualification、provider 和 pacing 状态。
4. 期权先固定 expiry/strike 集合，再计算请求预算；不要扫描整条链后才考虑免费额度。
5. 跨源合并前统一时区、交易日、复权口径、bar 完整性和 `as_of`。
6. 任何 fallback 都在报告中公开；禁止把空结果补成 0、把昨日值写成实时值、把目录写成报价、把 short-sale volume 写成 short interest。

