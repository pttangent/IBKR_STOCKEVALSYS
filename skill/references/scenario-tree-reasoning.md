# 多週期情景樹：以證據與價格事件組合，而不是固定模板

這份 reference 用於任何包含情景推演的報告。**情景樹不是固定的 `高開 / 平開 / 低開` 三叉模板，也不是把昨天收盤價換一個 ticker 再重複一次。** Agent 必須先找出當前股票真正存在、且有計算/來源支持的價格錨點，再由「市場實際發生的事件」組合出當天的樹。

核心鏈條是：

```text
證據 → 價格錨點 → 第一個被測試的結構 → 突破/受阻/跌破 → 回踩或反抽 → 守住/失守 → 下一個事件
```

例如最有用的日內鏈不是「高開所以看多」，而是：

```text
向上測試 R1
  → 有效突破 R1
     → 第一次回踩 R1 不破
        → 再次上攻前高/R2        （延續確認）
        → 守住但無法再攻         （高位整理）
     → 第一次回踩 R1 失守
        → 守住 VWAP/EMA20         （二次嘗試）
        → 連 VWAP/S1 一起失守     （假突破擴大）
  → 未突破 R1 就被拒絕
     → 回踩 VWAP/EMA20/S1 不破    （二次攻壓力）
     → 回踩也失守                 （壓力拒絕確認）
```

這種事件語法可以在不同股票、不同日期生成不同的樹，而不是 100 份報告長得一樣。

## 1. 完整報告固定分三個週期，但每棵樹內容必須動態生成

1. **日內 / 下一交易日**：盤前資訊、當日第一輪價格事件、VWAP/ORH/ORL、突破/回踩/反抽/失效。
2. **短期 / 數日到數週**：跨日結構修復、區間消化、支撐失守、RV 收斂/擴張、催化吸收。
3. **長期 / 季度以上**：公司營運 KPI、現金流、資本強度、競爭、估值與論點失效。

三者不可互相冒充。日內突破不能證明長期 thesis；長期基本面看多也不能把當天的假突破解釋成「只是噪音」。

## 2. 先建立價格錨點，再建立情景樹

任何出現在讀者面前的具體價格，都必須有來源與方法。建議優先級：

### A. 同一交易日動態錨點（若資料已形成）

- `VWAP`：當日成交量加權平均價；
- `ORH / ORL`：明確宣告窗口，例如開盤後 15 分鐘；
- 當日已形成的局部高/低、成交量峰值區（只有算法真的計算時才使用）。

這類錨點的顯示應與日線結構價不同顏色，因為它們是 **same-session dynamic evidence**。

### B. deterministic 技術結構錨點

- `S1 / S2 / ...`：deterministic engine 算出的最近支撐候選；
- `R1 / R2 / ...`：deterministic engine 算出的最近壓力候選；
- `EMA20 / SMA50 / SMA200`：已完成日 K 算出的均線；
- close-weighted volume node：只可標成低信心結構，不能冒充真實 intraday volume profile。

支撐/壓力本身可能來自 swing/Fibonacci bundle；若 engine 尚未保存更細 provenance，報告要如實標示「deterministic support/resistance bundle」，不能假裝知道它一定是某一種形態。

### C. 波動空間，不是支撐/壓力

- `±1 ATR`；
- Bollinger upper/lower；
- options implied move（只有 quote / IV 品質足夠時）。

這些應用另一種顏色，並且清楚標成 **volatility room / risk band**。不能因為 `price + ATR = 105` 就把 105 寫成壓力。

### D. 當前/最近有效價格

同一交易日有即時/近期 bar 時，可顯示 current price。若只有上一個 completed session 的 close，只能標成 **reference-only**，不能用它當日內結構分支的主幹。

### E. 前收價格

前收可以用於計算 gap 或交代背景，但不得取代真正的 `S/R/VWAP/ORH/ORL/MA` 成為情景樹核心。如果報告的每一條日內分支都在說「高於昨天 close / 跌破昨天 close」，表示情景樹設計失敗。

## 3. 每個價格錨點要帶 provenance

Structured JSON 中，scenario node 除了舊的 `price_reference` 相容欄位，應提供 `price_anchors[]`：

```json
{
  "id": "R1",
  "label": "壓力 R1",
  "value": 103.66,
  "role": "resistance",
  "source": "stock_eval.json:technical.support_resistance.resistances[0]",
  "method": "deterministic resistance candidate from swing/Fibonacci resistance bundle",
  "confidence": "medium",
  "status": "observed"
}
```

HTML 應讓讀者一眼區分：

- 支撐：綠色；
- 壓力：紅色；
- VWAP/ORH/ORL 等同日動態值：青色；
- 均線：紫色；
- ATR/波動帶：琥珀色；
- current/reference price：白色或中性色。

滑鼠停留或展開時應能看到來源/算法，而不是只有一個 `$103.66`。

## 4. 日內情景樹使用「事件 primitive」組合

Agent 不要硬背一棵固定樹，而要從下面 primitives 組合出與當前價格結構最相關的路徑。

### 向上事件 primitives

- `測試上方壓力`；
- `有效突破`；
- `突破後回踩`；
- `回踩不破`；
- `回踩失守`；
- `二次放量突破`；
- `守住但無法再攻`；
- `衝高未突破就回落`；
- `回落守住中軸/支撐`；
- `回落連中軸/支撐一起失守`。

### 向下事件 primitives

- `測試下方支撐`；
- `下探不破`；
- `跌破支撐`；
- `跌破後反抽`；
- `反抽原支撐不過`；
- `跌破後迅速收復（bear trap）`；
- `支撐反彈收復 VWAP/EMA20`；
- `收復後回踩不破`；
- `反彈在中軸受阻，再測支撐`。

### 中性/壓縮 primitives

- `窄幅震盪`；
- `反覆穿越 VWAP/中軸`；
- `量能萎縮`；
- `區間上破後回踩`；
- `區間下破後反抽`；
- `多次假突破，繼續無方向`。

只有當資料存在時才引用對應錨點。ORH/ORL 尚未形成時，不得填假數值；樹可以說「形成後觀察 ORH」，但價格 chips 不應出現虛構價格。

## 5. 最低完整度：日內樹至少要能回答「下一步是什麼」

一棵合格的日內樹應至少包含以下邏輯深度（具體分支可依證據增減）：

```text
日內第一輪價格事件
├─ 向上測試結構
│  ├─ 突破
│  │  ├─ 回踩不破
│  │  │  ├─ 再攻/突破下一壓力
│  │  │  └─ 守住但無法再攻
│  │  └─ 回踩失守
│  │     ├─ 中軸止跌，二次嘗試
│  │     └─ 中軸/支撐再失守，假突破擴大
│  └─ 未突破即受阻
│     ├─ 淺回踩不破，再測壓力
│     └─ 深回踩失守，壓力拒絕確認
├─ 窄幅震盪/壓縮
│  ├─ 上破 → 回踩驗證
│  ├─ 持續區間 → 等待
│  └─ 下破 → 反抽驗證
└─ 向下測試結構
   ├─ 支撐不破
   │  ├─ 反彈收復中軸 + 回踩不破
   │  └─ 反彈中軸受阻 → 再測支撐
   └─ 跌破支撐
      ├─ 反抽原支撐不過 → 弱勢延續
      └─ 快速收復 + 回踩不破 → bear trap 候選
```

這是 **事件 grammar 的最低語義完整度**，不是要求每支股票每次都渲染所有節點。若某股票上方沒有可辯護壓力、某日沒有同日 VWAP，相關枝節應縮減或改成未知，而不是硬補。

## 6. Node contract

每個 scenario node 應包含：

- `label`：中文、人可以直接看懂的事件名稱；
- `trigger`：可以在數據上觀察到的條件；
- `price_anchors`：有 provenance 的價格錨點；
- `watch`：下一步看什麼；
- `interpretation`：這個事件代表什麼；
- `response`：研究判斷如何改變；
- `invalidation`：什麼條件讓這個節點失效；
- `action_boundary`：等待 / 降低信心 / 允許 setup / no-trade；
- `sizing_tier`：`none / quarter / half / full_diagnostic / risk_only`；
- `children`：下一個事件，而不是另一段重複 prose。

概率只有在有可辯護方法時才填；不可以為了讓樹看起來完整而虛構 35%/40%/25%。

## 7. 分支內容要被當前結構裁剪，而不是永遠相同

生成樹前先問：

1. 最近的真正結構支撐/壓力在哪裡？
2. 是否有同日 VWAP/ORH/ORL？
3. EMA20/SMA50 是否剛好和 S/R 重疊形成 confluence？
4. 下一個壓力/支撐離現在只有 0.2 ATR 還是 1.5 ATR？
5. options implied move 是否可信，若不可信就不要放進 anchor book？
6. 當前股票是高 RV 還是壓縮狀態？
7. 現在真正最有信息量的是「突破壓力」、「測支撐」還是「區間內無方向」？

若兩個 anchors 距離極近，應做去重/視為同一 zone，避免樹上同時出現 99.18、99.20、99.24 三個假精確價位。

## 8. 短期樹

短期通常至少有：

- **修復**：完成日收復 EMA20/壓力，後續 1–數日回踩仍守住；
- **消化**：S1–R1 之間震盪，RV 收斂、量能收縮，等待催化；
- **走弱**：完成日跌破支撐，後續反彈無法收復。

同樣要引用真實的結構價，不用任意 ±5% 當 target。

## 9. 長期樹

長期至少區分：

- **論點強化**：核心營運 KPI、現金流/毛利、競爭位置與資本效率同向改善；
- **有限改善 / 混合**：產品/收入改善，但 margin、FCF、capital intensity、dilution 或競爭抵消；
- **論點轉弱**：核心經濟性惡化或估值/資本成本不再支持；
- **論點失效**：核心因果鏈被多個高品質證據否定，需要建立新 thesis，而不是替舊 thesis 找理由。

具體 KPI 從公司 evidence packet 注入，不可把 INTC、VST、GEV 等別的 ticker 門檻硬編碼到 skill。

## 10. HTML contract

完整報告的 scenario section 必須：

- 使用中文作為主要閱讀語言；
- 顯示真正的 branching map；
- 價格 anchors 顯示具體 `$price` 與顏色；
- 支援 hover/title 或展開看到 `source + method + confidence`；
- 同日動態值與日線結構值用不同顏色；
- 不把 `prior close` 當主要日內錨點；
- 每個 node 至少直接顯示 `條件 / 下一步 / 倉位層級`，展開顯示 `觀察 / 解讀 / 失效 / 行動邊界`；
- 手機版允許樹垂直堆疊。

完整範例應展示 **完整報告**（研究結論、基本面、估值、技術、期權、風險/Kelly、日內/短期/長期情景、治理、證據鏈），不能用只含 risk/scenario 的 partial mock 冒充 full report。
