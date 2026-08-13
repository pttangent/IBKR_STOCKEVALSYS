# 完整 HTML 報告範例

這個目錄只保留目前 report contract 的**完整中文範例**。舊的 GEV/XE legacy 與前一版 partial INTC v2 mock 均已淘汰。

## 目前範例

- [`INTC_full_report_example.html`](INTC_full_report_example.html) — 完整中文報告：研究結論、基本面、估值、技術、期權、Kelly/$10k 倉位、日內/短期/長期情景樹、治理與證據鏈。
- [`INTC_full_structured_report.mock.json`](INTC_full_structured_report.mock.json) — 對應的完整 structured semantic mock。
- [`INDEX.html`](INDEX.html) — 瀏覽器入口。
- [`example_manifest.json`](example_manifest.json) — machine-readable inventory。

範例明確標示 **DEMO / 部分 MOCK**。部分數字來自前一輪 frozen INTC evidence，部分只為了把完整 UI 展示出來；它不是即時 INTC 投資結論。

## 日內情景樹已改成 compositional event tree

Canonical tree 不再是：

```text
高開 / 平開 / 低開
```

而是先建立有來源的價格錨點，再由市場實際事件組合：

```text
價格錨點
  → 第一個被測試的結構
  → 突破 / 受阻 / 跌破
  → 回踩 / 反抽
  → 守住 / 失守
  → 再攻 / 假突破 / bear trap / 高位整理 / 弱勢延續
```

完整範例特別展示：

- `突破 R1 → 回踩不破 → 二次突破 / 高位整理`；
- `突破 R1 → 回踩失守 → EMA20/S1 承接或假突破擴大`；
- `衝高未突破 R1 → 淺回踩不破 → 二次攻壓力`；
- `測試 S1 → 支撐不破 → 收復 EMA20 + 回踩不破`；
- `跌破 S1 → 反抽不過 → 原支撐轉壓力`；
- `跌破 S1 → 迅速收復 + 回踩不破 → bear trap 候選`；
- 區間壓縮 → 上破/等待/下破。

這些是 **事件 primitives / grammar**，不是要求每支股票都渲染一模一樣的所有枝節。實際 builder 會依當前存在的 S/R、MA、VWAP、ORH/ORL、ATR 等裁剪並填入真實價位。

## 價格不是裝飾數字

所有 scenario numeric price 應有：

- `value`
- `role`
- `source`
- `method`
- `confidence`
- `status`

HTML 顏色語義：

- 綠：支撐；
- 紅：壓力；
- 青：同日 VWAP / ORH / ORL；
- 紫：均線；
- 琥珀：ATR / volatility room；
- 白/灰：current/reference price。

只有上一個 completed-session close 時，它只能標成 `reference_only`。前收可用來說明 gap，但不應成為日內結構樹的主 trigger。

## 完整報告而非 partial mock

目前範例固定展示：

1. 研究結論；
2. 基本面；
3. 估值；
4. 技術與真實結構價；
5. 期權與波動；
6. Kelly full / half / quarter 與 $10,000 倉位；
7. 日內 / 短期 / 長期情景；
8. 治理與 Bull/Bear/Skeptic；
9. 證據鏈。

正式 production flow 仍是：

```text
raw / normalized evidence
  -> deterministic artifacts
  -> structured_report.json
       -> Markdown
       -> HTML
  -> evidence-chain ZIP
```

Canonical renderer：[`skill/scripts/render_html_report.py`](../../../skill/scripts/render_html_report.py)。情景樹知識：[`skill/references/scenario-tree-reasoning.md`](../../../skill/references/scenario-tree-reasoning.md)。
