# IBKR 新闻获取能力

本参考文件定义项目内个股报告如何获取、验证和使用 IBKR/TWS 新闻。新闻是催化剂与事件风险证据，不是自动交易信号。

## 官方文档

- [IBKR TWS API: News](https://interactivebrokers.github.io/tws-api/news.html)
- [IBKR TWS API 页面](https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/)

遇到 provider、字段、历史保留期、权限或错误码不确定时，先查官方文档和当前 TWS 返回，不凭记忆补字段。

## 项目内调用路径

只使用项目自己的 MCP：

```text
C:\DEV\CODEX_USSTOCK\stock-eval-system\ibkr-mcp
C:\DEV\CODEX_USSTOCK\stock-eval-system\.venv\Scripts\python.exe
```

不得修改外部 MCP，也不得把新闻测试改成下单或行情订阅测试。连接必须是只读 TWS 会话。

可用工具：

| 工具 | 用途 | 证据形态 |
|---|---|---|
| `ibkr_get_news_providers` | 枚举当前 TWS 会话可用 provider | 能力/权限清单 |
| `ibkr_get_news_articles` | 查询历史新闻标题 | 时间、provider、articleId、headline |
| `ibkr_get_news_article` | 按 `providerCode + articleId` 获取正文 | 正文/HTML（若该 provider 提供） |
| `ibkr_start_news_resource` | 订阅 IB 新闻 bulletin | 实时事件流，需单独确认订阅与生命周期 |
| `ibkr_start_tick_news_resource` | 订阅 tick news | 实时事件流，不能用历史标题结果代替 |

## 必须遵守的调用顺序

1. 连接 TWS，并记录 `as_of`、TWS server/API 状态和 clientId。
2. 调用 `ibkr_get_news_providers`，保存完整的 `code/name` 清单；不要假设某个 provider 一定可用。
3. 对股票先完成合约解析。项目 MCP 的 `ibkr_get_news_articles` 已在内部调用 `qualifyContractsAsync` 并使用真实 `conId`；返回中应检查 `conId`。如果 qualification 失败，记录错误，不把空数组当作“没有新闻”。
4. 历史标题按 provider 分开查询。推荐先尝试当前清单中存在的 `BRFG`、`BRFUPDN`、`DJ-N`、`DJ-RTPRO`、`DJNL`，但以实际枚举结果为准。分开查询便于保持各 provider 的覆盖可比；不要把一次多 provider 请求的 `totalResults` 误读成每个 provider 各自的数量。
5. 记录每条标题的 `time`、`providerCode`、`articleId` 和原始 `headline`，按 `(providerCode, articleId)` 去重。
6. 只有入选为关键催化剂的标题才调用 `ibkr_get_news_article` 获取正文。正文失败时保留标题证据，并明确标记 `body_available=false`。

时间窗口使用 IBKR 格式，例如：

```text
20260807 09:30:00 US/Eastern
20260807 16:00:00 US/Eastern
```

空起止时间表示由 IBKR 返回最近可用结果；报告必须写清这是“最近可用”而不是严格的过去 24 小时，除非显式传入时间窗口。

## 证据分级与报告写法

每条新闻至少保留：

```json
{
  "providerCode": "BRFG",
  "time": "...",
  "articleId": "...",
  "headline": "...",
  "body_available": false,
  "retrieved_at": "..."
}
```

- A：有 provider、时间、articleId，且正文可获取；正文中的事实仍需与公司公告、监管文件或其他一手来源交叉核验。
- B：有 provider、时间、articleId 和标题，但正文不可用。
- C：只有二手网页或搜索摘要；不能冒充 IBKR 原始新闻证据。

区分三类内容：公司公告/监管披露、分析师动作或观点、媒体/市场评论。分析师目标价和新闻 provider 的语气不是公司事实；同一事件被多个 provider 转发也不等于多个独立证据。保留原始标题，另存去除标签/格式后的规范化标题，不要把 provider 情绪标签直接当成方向信号。

## 权限、空结果与实时边界

历史新闻能力与股票实时行情、期权 OPRA 权限是不同能力。没有实时行情或期权权限，不自动推出“没有历史新闻”。先检查：

- provider 枚举是否成功；
- underlying 是否成功 qualification，返回的 `conId` 是否非零；
- provider code 是否确实存在；
- 时间窗口和 `totalResults` 是否合理；
- 是否只对一个 provider 得到空结果。

在这些检查完成前，空数组只能写成“本次请求无结果”，不能写成“该股票没有新闻”。常见 TWS 历史新闻问题包括无效 provider、无效/未解析合约、时间窗口不合法或新闻权限限制；保留 TWS 错误码和原始错误信息。

`ibkr_start_*_news_resource` 属于实时/事件流路径，是否能收到 bulletin 或 tick news 需要单独测试。历史标题测试成功，不代表实时新闻流已授权；实时流测试失败，也不否定历史标题/正文能力。

## 在个股报告中的使用

新闻应进入“催化剂/事件风险”层，并与价格、成交量、财报、公司公告、Street expectations 和期权隐含波动率交叉验证。完整研究还要遵循 `catalyst-context.md` 的 delta-first 规则：如果存在上一份评估，先回答“自上次评估后发生了什么变化”，再决定哪些 Claim Graph 节点需要强化、削弱或标记未决。报告至少说明：

- 查询时间、历史/实时状态和 provider；
- 标题、时间、articleId、正文可用性；
- 是否去重、是否存在 provider 冲突；
- 新闻属于事实、分析师观点还是市场评论；
- 对基本面、短期情景和失效条件的具体影响；
- 新闻不足以支持哪一个结论，以及还需要什么一手证据。

新闻在 Evidence Freeze 后只能作为带固定 `evidence_id` 的证据供 Bull/Bear/Skeptic 使用；reviewer 不得各自重新查询新闻。每条入选新闻应记录 `published_at`、`received/retrieved_at`、provider、articleId 和 PIT 截止状态；只有发布时间而没有接收时间时，必须披露该 PIT 限制。

不得仅依据标题数量、正负面词频或单一 provider 生成 BUY/SELL 结论。新闻情报不足时降低置信度，并保留可验证的触发与失效条件。
