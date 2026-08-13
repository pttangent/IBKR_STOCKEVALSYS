# 日內 / 短週期 timing：以事件與真實結構價生成，不使用固定 gap 模板

當使用者詢問今天、盤前、開盤後、短週期 timing 時使用本 reference。這一層是完整研究報告的戰術補充，不替代長期基本面與估值。**Canonical 情景樹規則以 [scenario-tree-reasoning.md](scenario-tree-reasoning.md) 為準。** 倉位則讀 [kelly-positioning-knowledge.md](kelly-positioning-knowledge.md)。

最重要的規則：**gap 是背景變數，不是情景樹骨架。** 前收可以用來計算 gap 或說明 overnight repricing，但不能讓所有股票都生成 `高開/平開/低開 → acceptance/fade` 同一棵樹。

## 1. 兩種資料狀態

| 狀態 | 有什麼 | 可以做什麼 | 不可以做什麼 |
|---|---|---|---|
| 盤前 / 尚無同日 bar | completed daily OHLCV、S/R、MA、ATR/RV、事件/期權 proxy | 建立 next-session conditional tree，列出真正的結構價與待形成欄位 | 不可虛構 VWAP、ORH、ORL，不可聲稱 branch 已確認 |
| 同日 bar 已形成 | 上述資料 + current price、VWAP、ORH/ORL、當日量能/區間 | 將動態價位插入情景樹並更新當前 branch | 不可把 bar-count 或 price-signed-volume 當成真實 aggressor flow |

如果 options 沒有可信 bid/ask、OI 或 IV timestamp，只能做 volatility/event proxy；不得把 strike 寫成硬牆。

## 2. 盤前先建立「價格錨點簿」，不要先寫劇本

先從當前 ticker 的 deterministic artifacts 取：

- `S1/S2/...`：最近支撐候選；
- `R1/R2/...`：最近壓力候選；
- `EMA20/SMA50/SMA200`；
- `ATR14` 與 `±1 ATR` 波動空間；
- Bollinger 等風險帶（若使用）；
- close-weighted volume node 只能標低信心，因為不是 intraday volume profile；
- options implied move 只有在 quote/IV 品質通過時才能加入。

同日開始後，再加入：

- `VWAP`；
- `ORH/ORL`（明確窗口，預設 15 分鐘）；
- 其他已由算法實際算出的當日高低/成交節點。

每個具體價格都必須帶 `source + method + confidence + status`。如果只有昨天 completed close，它只能是 `reference_only`。

## 3. Session phase

1. **盤前**：overnight 事件、最新可用參考價、S/R/MA/ATR/RV、可辯護的 options event risk、哪些同日欄位尚未形成。
2. **開盤形成期**：第一輪主動價格行為先測哪個結構；ORH/ORL/VWAP 開始形成。
3. **驗證期**：突破後回踩、跌破後反抽、支撐測試後反彈、區間壓縮後突破等第二步事件。
4. **延續/失效期**：再突破、守住但停滯、假突破、bear trap、支撐轉壓力等。
5. **收盤/隔夜**：重新區分 intraday risk 與 overnight risk，不把日內 setup 自動延伸到隔夜。

## 4. 日內事件 grammar

Agent 應從市場實際走出的事件組合，而非照固定順序全部輸出。

### 向上鏈

```text
測試上方結構
├─ 有效突破
│  ├─ 回踩不破
│  │  ├─ 二次放量突破 / 再攻下一壓力
│  │  └─ 守住但無法再攻 / 高位整理
│  └─ 回踩失守
│     ├─ 中軸/VWAP/EMA20 止跌 → 二次嘗試
│     └─ 中軸/支撐再失守 → 假突破擴大
└─ 未突破即受阻
   ├─ 淺回踩支撐不破 → 二次攻壓力
   └─ 深回踩失守 → 壓力拒絕確認
```

其中「**衝高回踩不破**」應寫成可驗證條件，而不是文字形容：

- 先明確說突破的是哪一個有來源的錨點，例如 `R1=$103.66`；
- 第一次回踩最低價/收盤沒有有效跌回該 zone；
- 若 VWAP/ORH 已形成，可要求至少一個同日動態錨點保持同向；
- 回踩量能若可比較，最好下降；
- 再攻時要看前高/R2 距離是否仍有足夠 risk/reward；
- 若回踩跌回突破位並反抽不過，切換假突破分支。

### 向下鏈

```text
測試下方結構
├─ 支撐不破
│  ├─ 反彈收復 VWAP/EMA20 + 回踩不破 → 反轉候選
│  └─ 反彈在中軸受阻 → 再測支撐
└─ 跌破支撐
   ├─ 反抽原支撐不過 → 原支撐轉壓力 / 弱勢確認
   └─ 快速收復 + 回踩不破 → bear trap 候選
```

### 壓縮鏈

```text
窄幅震盪 / 量能收縮
├─ 上破 → 回踩驗證
├─ 繼續區間 → 不強迫方向
└─ 下破 → 反抽驗證
```

不是每支股票都必須同時渲染所有節點。若沒有可信上方壓力，向上分支可以縮短；若 same-session data 尚未存在，VWAP/ORH/ORL 必須保留為「待形成」，而不是填假數字。

## 5. 哪些價格可以當 trigger

優先使用市場結構：

1. same-session VWAP / ORH / ORL；
2. deterministic S1/S2/R1/R2；
3. EMA20 / SMA50 等中軸；
4. 有方法支持的成交節點；
5. ATR / Bollinger 只作 risk/volatility room，不作支撐壓力。

`prior_close` 只用於 gap 與背景。除非它恰好與其他結構形成 confluence，否則不要寫「跌破昨天 close 所以看空」或「高於昨天 close 所以看多」作為主條件。

## 6. Stop / target 與情景節點

不要使用固定 ±3%、±5%。

- stop：失敗的結構錨點 + 合理波動 buffer；
- target：下一個真實壓力/支撐/流動性區；
- 若下一壓力太近，例如小於預定 stop distance，該 branch 即使方向正確也可能沒有足夠 reward/risk；
- ATR 是波動尺度，不是神奇 target。

## 7. Kelly 與 branch 不能互相創造 edge

Kelly 的 `p/b` 來自相同 setup/timeframe/exit rule 的歷史樣本。日內 branch 只能決定「當前 setup 是否更接近歷史定義、是否允許使用某個 sizing tier」，不能因為今天突破 R1 就重新發明一個較高勝率。

常見層級：

- 未確認 / 矛盾：`none`；
- 完成第一級結構確認，例如突破後回踩不破：`quarter`；
- 完成更完整的再突破鏈，且 same-setup 樣本/OOS 也足夠：可以展示 `half`；
- `full` 原則上保持理論/診斷上限，除非策略治理另有明確規則。

沒有 standard OOS 不等於整段空白。可計算時顯示 exploratory/conditional/proxy；若 Kelly edge 不可用但 stop/risk 可定義，顯示 risk-only。

## 8. Confidence contract

短週期報告至少要有：

- `data_confidence`：freshness、same-session coverage、provider conflict；
- `setup_confidence`：目前事件鏈與歷史 setup 的匹配；
- `sample_confidence`：交易數、OOS 數、regime coverage；
- `overall_confidence`；
- `confidence_reasons`；
- `action_boundary`。

Confidence 是證據品質，不是「上漲機率」。

## 9. 完整報告輸出

完整研究報告的 timing 區應呈現：

- 盤前有哪些事件/資料要注意；
- 價格錨點簿（有來源、有顏色、有方法）；
- 日內 compositional event tree；
- 短期數日—數週 tree；
- 長期季度以上 tree；
- Kelly full/half/quarter 與 $10k risk translation；
- 每一個重要圖表的「這是什麼 / 怎麼看 / 為什麼重要 / 限制」。

不要再生成固定的 Gap-up/Gap-down minimum table 作 canonical tree。Gap 可以保留為 metadata 或某一個特定事件的補充條件，但不是全體報告的共同骨架。
