# 基本面、預期與市場反應多源整合規範

本文件是個股研究報告的能力邊界與來源角色主契約。資料源不得因為「有回應」就彼此替代；先判斷它回答的是 reported fact、standardized comparison、market expectation、event/metadata，還是 market reaction。

## 五層角色

1. **SEC / 發行人 IR = 真相層（reported truth）**
   - SEC `submissions`、`companyfacts`、具體 accession filing 與 XBRL 是已申報會計事實主來源。
   - 發行人 IR 補 management guidance、earnings release、presentation、非 XBRL KPI 與公司聲明。
   - Revenue、Gross Profit、Operating Income、Net Income、Cash Flow、Cash、Debt、Shares 等 reported actuals 預設由此層控制。

2. **SimFin = 標準化層（standardization / peer-ready view）**
   - 用於將跨公司報表整理為較一致的 schema、衍生欄位與 peer/cross-sectional 比較。
   - production base 使用 `https://prod.simfin.com/api/v3`。
   - SimFin 不得覆蓋 SEC reported actual。若 normalized value 與 SEC 不一致，輸出 conflict / mapping note，而不是取平均或靜默替換。
   - 嚴格 PIT 回放仍須自行保存 retrieval/availability 與 period identity；「標準化」不等於「歷史 PIT 安全」。

3. **Alpha Vantage = 市場預期層（expectations）**
   - `EARNINGS_ESTIMATES`：EPS / Revenue estimates、analyst count、revision fields。
   - `EARNINGS`：reported vs estimated EPS / surprise history，可作 expectations/event context，不取代 SEC GAAP actual。
   - `EARNINGS_CALENDAR` / transcript 為可選輔助。
   - current API snapshot 只代表目前可見的市場預期；沒有 `available_at <= historical_as_of` 證據時，不得拿今天的 consensus 回填歷史研究。
   - 每次取得 estimates 應 append-only 保存 snapshot，逐步建立自己的 PIT revision history。

4. **Finnhub = 事件 / metadata / 快速交叉驗證層**
   - 優先使用 `stock/profile2`、`stock/peers`、`stock/metric`、`stock/earnings`、`calendar/earnings`、`company-news`。
   - `stock/financials-reported` 只作 reported-financial cross-check；不得取代 SEC。
   - standardized `stock/financials` 若帳戶未授權就明確標示 `not_entitled`，不把 403 解讀成公司資料缺失。
   - Finnhub earnings/calendar 可能採 adjusted/non-GAAP expectation，必須與 SEC GAAP reported facts 分欄展示。

5. **Alpaca = 市場 / 事件 / 反應層（market reaction）**
   - IEX stock snapshot/trade/quote/bars、assets、news、corporate actions、option contracts、indicative option context，以當前 entitlement 為準。
   - 回答「市場如何定價已發生的基本面與預期變化」，例如價格跳空、成交量、波動、option repricing。
   - Alpaca **永遠不是 accounting fundamentals source**；IEX 亦不等於 consolidated SIP。

IBKR/TWS 不再是單股研究的預設資料源；它主要保留給盤中實時雷達、微觀結構、交易所/OPRA entitlement 與 execution-adjacent 驗證。當非 IBKR 資料已足以支援個股研究模組時，不應因習慣而額外連 IBKR。

## IBKR Reuters Fundamentals 的定位

`reqFundamentalData` / Reuters report types 只保留為 **optional legacy / entitlement diagnostic**。若當前帳戶實測 10358、空結果或未訂閱，報告仍可由 SEC + SimFin + Alpha Vantage + Finnhub 完成；不得把 Reuters entitlement 當 fundamental report readiness 的必要條件，也不得把其失敗寫成「公司基本面缺失」。

## 不可跨角色替換

- SEC reported actual 缺失：標記 `needs_primary_source`；不得用 estimate、price、technical level 或 normalized value 冒充 actual。
- SimFin normalization 缺失：仍可做 SEC 單一公司基本面，但 peer/cross-sectional confidence 降級。
- Alpha Vantage expectations 缺失：仍可做 historical fundamentals；priced-in / revisions / forward valuation 判斷降級，不自行補 consensus。
- Finnhub event/metadata 缺失：不影響 SEC actual，只降低事件時序、peer discovery 與 cross-check 完整性。
- Alpaca market-reaction 缺失：不影響 accounting truth，只降低 market reaction / timing / option interpretation。
- 任一 401/403/404/429、空 payload、quota note 或 schema mismatch 都是 provider status，不是 market signal。

## 硬性期間與 PIT 閘門

- duration facts 必須同一 `accession + filed + form + period_start + period_end` 才能計算同期間 margin / conversion / growth。
- instant facts 必須使用同一最新申報身份與 instant date 才能做 balance-sheet cross-ratios。
- `available_at` / `filed` 必須不晚於 research `as_of` 才能稱為 PIT-qualified。
- 當前 consensus snapshot 若沒有歷史 availability 證明，標示 `CURRENT_SNAPSHOT_ONLY`；可分析現在市場預期，不可回灌歷史回測。
- 找不到一致期間時保留原始值與 source ID，但 `ratio_safe=false`。

## 個股報告固定輸出順序

1. **Reported truth**：SEC/IR actual、filing identity、period、filed/available time。
2. **Fundamental trajectory**：growth、margin、cash conversion、working capital、balance-sheet、capital allocation / dilution，只用 period-safe facts。
3. **Standardized / peer-ready view**：SimFin coverage、mapping/status、可比較指標與 conflict。
4. **Market expectations**：Alpha Vantage EPS/Revenue estimates、analyst count、revision/surprise，清楚標示 current-vs-PIT。
5. **Event / metadata cross-check**：Finnhub earnings calendar、earnings surprise、profile/peers、news/metric 狀態。
6. **Expectation vs actual**：actual acceleration/deterioration 與 estimate direction 是否同向；不得揉成單一數字。
7. **Market reaction**：Alpaca IEX price/quote/bars、news/corporate actions/option context；IEX-only 限制要可見。
8. **Valuation readiness**：只有 shares/debt/cash、forecast period、可核驗 expectation 或明示 internal model 足夠時才輸出 fair-value range；technical support/resistance 不得替代估值。
9. **Conflicts / missing evidence**：按角色列缺口，說明缺口影響哪一種結論，而不是只列 API error。

## 建議的可重播流程

```text
fetch_sec_research.py
fetch_simfin_research.py
fetch_alpha_vantage_research.py
fetch_finnhub_research.py
fetch_alpaca_research.py
(optional exception) fetch_ibkr_fundamentals.py / IBKR market data
        ↓
reconcile_fundamentals.py        # accounting period / identity gate
        ↓
build_fundamental_layer.py       # role-aware report contract
        ↓
research_content / structured report / HTML
```

所有 packet 至少保留 provider、endpoint/report type、retrieved_at、as_of、available_at、HTTP/entitlement status、原始 payload 與錯誤。