# 基本面多源整合規範

基本面不是「哪個 API 有回應就用哪個」。先固定申報期間，再做來源整合。

1. **SEC / 發行人 IR：一級主來源。** SEC companyfacts 提供申報事實；IR 補充指引、非 XBRL KPI、簡報與新聞稿。
2. **IBKR Reuters Fundamentals：二級交叉核對。** 透過 `ReportsFinSummary`、`ReportsFinStatements`、`ReportsOwnership` 取得；需要對應 Reuters Fundamentals 權限。空結果、錯誤或未訂閱只代表資料存取失敗。
3. **Finnhub：二級交叉核對。** `stock/financials-reported` 與 `stock/metric` 可作補充；標準化 `stock/financials` 可能需要更高級別權限。不可覆蓋 SEC，也不自動提供歷史回放的 PIT 保證。
4. **SimFin：二級交叉核對。** 使用 `https://backend.simfin.com/api/v3` 的 general、statements、shares 端點；Authorization header 需要 `api-key <key>`。statements 可要求 as-reported，但仍須自行核對期間與來源身份；API 回應不自動等於 PIT 證據。

## 硬性期間閘門

- 收入、毛利、營業利益、淨利、營運現金流等期間欄位，必須同一 `accession + filed + form + period_start + period_end` 才能計算轉換率、利潤率或同一期比較。
- 現金、資產、負債、股東權益等時點欄位，必須同一最新申報/`accession + filed + instant`。
- 找不到一致群組時，保留實際數字，但 `ratio_safe=false`；不得把 Q2 搭 H1、舊年度負債搭最新季度損益，也不得用 Finnhub/IBKR 靜默修補。
- `reconcile_fundamentals.py` 以 SEC 為 `primary_provider`，只保存 Finnhub、IBKR 與 SimFin 二級來源狀態與原始資料。

## 可重播欄位

每個來源包都要保留 provider、endpoint/report type、retrieved_at、as_of、available_at、HTTP/entitlement status、原始 payload 或 XML、以及錯誤。SimFin 請求必須串行，並保留 rate-limit / 429 狀態。
