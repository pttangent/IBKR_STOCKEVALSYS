#!/usr/bin/env python3
"""Render terminal-style Chinese HTML from canonical structured_report.json.

The renderer never parses Markdown for semantics. Kelly guidance and scenario
trees are rendered directly from structured JSON. Scenario prices are rendered
as provenance-bearing colored anchors, not as unsourced prose numbers.
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

try:
    import mistune
    import plotly.graph_objects as go
    from plotly.offline import get_plotlyjs
    from plotly.subplots import make_subplots
except ImportError as exc:  # pragma: no cover
    raise SystemExit("請先安裝 skill/requirements-html.txt（mistune, plotly）") from exc

MD = mistune.create_markdown(plugins=["table", "strikethrough"])
PLOTLY_JS = get_plotlyjs()

CSS = r'''
:root{--bg:#0a0a0a;--fg:#fafafa;--muted:#a1a1aa;--border:#262626;--soft:#171717;--good:#22c55e;--bad:#ef4444;--warn:#f59e0b;--cyan:#22d3ee;--purple:#a78bfa;--blue:#60a5fa}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--fg);font-family:"Space Mono","JetBrains Mono","Noto Sans TC",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13px;line-height:1.58}.shell{max-width:1520px;margin:auto;padding:20px}.top{border-bottom:1px solid var(--border);padding:12px 0 18px;display:grid;grid-template-columns:1fr auto;gap:20px;align-items:end}.kicker,.label,.panel-title,.chart-title{letter-spacing:.08em;font-weight:700}.kicker{font-size:11px;color:var(--muted)}h1{font-size:28px;line-height:1.15;margin:5px 0 0}.meta{text-align:right;color:var(--muted);font-size:11px}.state{display:inline-block;padding:4px 8px;border:1px solid var(--border);color:var(--fg);margin-top:6px}.state.good{color:var(--good);border-color:#14532d}.state.warn{color:var(--warn);border-color:#713f12}.nav{position:sticky;top:0;z-index:10;background:#0a0a0af2;border-bottom:1px solid var(--border);padding:8px 0;white-space:nowrap;overflow:auto}.nav a{color:var(--muted);text-decoration:none;margin-right:18px;font-size:11px}.nav a:hover{color:var(--fg)}.grid12{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:0;border-left:1px solid var(--border);border-top:1px solid var(--border);margin-top:18px}.cell{border-right:1px solid var(--border);border-bottom:1px solid var(--border);padding:14px}.span3{grid-column:span 3}.span4{grid-column:span 4}.span6{grid-column:span 6}.span12{grid-column:span 12}.metric .label{font-size:10px;color:var(--muted)}.metric .value{font-size:21px;font-weight:700;margin-top:6px}.module{margin-top:28px;border-top:1px solid var(--border)}.module-head{display:flex;justify-content:space-between;gap:16px;border-bottom:1px solid var(--border);padding:12px 0}.panel-title{font-size:14px}.statusline{font-size:10px;color:var(--muted)}.body-grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));border-left:1px solid var(--border)}.panel{grid-column:span 12;border-right:1px solid var(--border);border-bottom:1px solid var(--border);padding:16px}.panel h3{font-size:12px;letter-spacing:.08em;margin:0 0 12px}.muted{color:var(--muted)}.block{margin:0 0 14px}.block p{margin:0 0 8px}.block ul{padding-left:18px}.judgment{border-left:2px solid var(--fg);padding:8px 12px;margin:10px 0;background:#111}.judgment .jlabel{color:var(--muted);font-size:10px}.knowledge{border:1px solid #3f3f46;background:#101010;padding:12px;margin:10px 0}.knowledge .kt{color:var(--warn);font-size:10px;font-weight:700;letter-spacing:.08em}.chart-wrap{border:1px solid var(--border);margin:12px 0 20px;background:#080808}.chart-title{padding:10px 12px;border-bottom:1px solid var(--border);font-size:11px}.chart{min-height:280px}.explain{display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid var(--border)}.explain>div{padding:10px;border-right:1px solid var(--border)}.explain>div:last-child{border-right:0}.explain .xk{font-size:9px;color:var(--muted);letter-spacing:.08em;font-weight:700}.explain .xv{font-size:11px;margin-top:5px}.explain .xo{font-size:10px;color:#d4d4d8;border-top:1px dotted #333;margin-top:7px;padding-top:7px}.missing{color:var(--warn)}table{border-collapse:collapse;width:100%;font-size:11px}th,td{border:1px solid var(--border);padding:7px;text-align:left;vertical-align:top}th{color:var(--muted)}.kelly-status{display:flex;flex-wrap:wrap;gap:0;border-left:1px solid var(--border);border-top:1px solid var(--border);margin-bottom:14px}.kelly-status>div{min-width:150px;flex:1;border-right:1px solid var(--border);border-bottom:1px solid var(--border);padding:10px}.kelly-status .k{font-size:9px;color:var(--muted);letter-spacing:.08em}.kelly-status .v{font-size:16px;font-weight:700;margin-top:4px}.kelly-guide{color:var(--good)}.kelly-table td:first-child{font-weight:700}.kelly-table tr.guide td{border-top:2px solid var(--good);border-bottom:2px solid var(--good)}.scenario-wrap{overflow-x:auto;padding:8px 0 18px}.scenario-meta{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;color:var(--muted);font-size:10px}.scenario-meta span{border:1px solid var(--border);padding:3px 6px}.anchor-legend{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0 14px}.anchor-legend span{font-size:9px;border:1px solid var(--border);padding:3px 6px}.tree{min-width:max-content;padding:8px 18px}.tree ul{padding-top:22px;position:relative;display:flex;justify-content:center;margin:0;padding-left:0}.tree li{list-style:none;text-align:center;position:relative;padding:22px 7px 0}.tree li::before,.tree li::after{content:'';position:absolute;top:0;right:50%;border-top:1px solid #3f3f46;width:50%;height:22px}.tree li::after{right:auto;left:50%;border-left:1px solid #3f3f46}.tree li:only-child::after,.tree li:only-child::before{display:none}.tree li:only-child{padding-top:0}.tree li:first-child::before,.tree li:last-child::after{border:0 none}.tree li:last-child::before{border-right:1px solid #3f3f46}.tree ul ul::before{content:'';position:absolute;top:0;left:50%;border-left:1px solid #3f3f46;width:0;height:22px}.tree-card{width:248px;display:inline-block;text-align:left;vertical-align:top;border:1px solid #3f3f46;background:#0f0f0f;padding:10px;white-space:normal}.tree-card.root{border-color:var(--cyan)}.tree-label{font-weight:700;font-size:11px;letter-spacing:.03em}.tree-trigger{font-size:10px;margin-top:7px}.tree-trigger b,.tree-response b{color:var(--warn)}.tree-response{font-size:10px;margin-top:7px}.tree-anchors{display:flex;gap:4px;flex-wrap:wrap;margin-top:8px}.price-anchor{display:inline-flex;gap:4px;align-items:center;border:1px solid #3f3f46;padding:3px 5px;font-size:9px;background:#0b0b0b}.price-anchor .p{font-weight:800}.price-anchor.support,.price-anchor.intraday_support,.price-anchor.volume_node_support{color:var(--good);border-color:#14532d}.price-anchor.resistance,.price-anchor.intraday_resistance,.price-anchor.volume_node_resistance{color:var(--bad);border-color:#7f1d1d}.price-anchor.intraday{color:var(--cyan);border-color:#155e75}.price-anchor.moving_average{color:var(--purple);border-color:#5b21b6}.price-anchor.volatility{color:var(--warn);border-color:#713f12}.price-anchor.current{color:var(--fg);border-color:#737373}.tree-ref{border:1px solid #333;padding:2px 4px;font-size:9px;color:#d4d4d8}.tree-tier{display:inline-block;margin-top:8px;padding:2px 5px;border:1px solid #3f3f46;font-size:9px;color:var(--muted)}.tree-tier.quarter,.tree-tier.half{color:var(--good);border-color:#14532d}.tree-tier.none{color:var(--muted)}.tree-card details{border-top:1px dotted #333;margin-top:8px;padding-top:7px;font-size:9px;color:#d4d4d8}.tree-card summary{cursor:pointer;color:var(--muted)}.tree-detail{margin-top:6px}.tree-detail b{color:var(--muted)}.footer{border-top:1px solid var(--border);margin-top:32px;padding:16px 0 30px;color:var(--muted);font-size:10px}@media(max-width:900px){.shell{padding:12px}.top{grid-template-columns:1fr}.meta{text-align:left}.span3,.span4,.span6{grid-column:span 12}.explain{grid-template-columns:1fr}.explain>div{border-right:0;border-bottom:1px solid var(--border)}.explain>div:last-child{border-bottom:0}.tree{min-width:0}.tree ul{display:block;padding:0}.tree ul ul::before,.tree li::before,.tree li::after{display:none}.tree li{padding:5px 0}.tree-card{width:100%;display:block}}
'''

MODULE_NAV = {
    "overview": "研究結論", "fundamentals": "基本面", "valuation": "估值", "technical": "技術結構",
    "options": "期權/波動", "governance": "治理", "risk": "風險/倉位", "scenarios": "情景樹", "evidence": "證據鏈",
}
TIER_LABEL = {"none": "觀望", "quarter": "1/4 Kelly", "half": "1/2 Kelly", "full_diagnostic": "Full（僅診斷）", "risk_only": "僅風險上限"}


def load(path: Path, default=None):
    if not path.exists():
        return {} if default is None else default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def esc(value) -> str:
    return html.escape("—" if value is None or value == "" else str(value))


def pct(value, digits=1) -> str:
    try:
        return f"{float(value) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "—"


def money(value, digits=0) -> str:
    try:
        return f"${float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def num(value, digits=2) -> str:
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def normalize_bars(data: dict) -> list[tuple]:
    raw = data.get("bars") or data.get("results") or data.get("data") or []
    out = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        try:
            o = float(row.get("open", row.get("o"))); h = float(row.get("high", row.get("h")))
            l = float(row.get("low", row.get("l"))); c = float(row.get("close", row.get("c")))
            v = float(row.get("volume", row.get("v", 0)) or 0)
        except (TypeError, ValueError):
            continue
        date = str(row.get("date") or row.get("datetime") or row.get("time") or row.get("t") or "")[:10]
        out.append((date, o, h, l, c, v))
    return out


def ema(values: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < n:
        return out
    previous = sum(values[:n]) / n; out[n - 1] = previous; alpha = 2 / (n + 1)
    for i in range(n, len(values)):
        previous = alpha * values[i] + (1 - alpha) * previous; out[i] = previous
    return out


def sma(values: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values); acc = 0.0
    for i, value in enumerate(values):
        acc += value
        if i >= n: acc -= values[i - n]
        if i >= n - 1: out[i] = acc / n
    return out


def fig_html(fig, height=380) -> str:
    fig.update_layout(template="plotly_dark", paper_bgcolor="#080808", plot_bgcolor="#080808",
                      font=dict(family="Space Mono, monospace", color="#d4d4d8", size=10),
                      margin=dict(l=48, r=18, t=38, b=40), height=height, hovermode="x unified",
                      legend=dict(orientation="h", y=1.03, x=0))
    fig.update_xaxes(gridcolor="#1f1f1f", zerolinecolor="#262626")
    fig.update_yaxes(gridcolor="#1f1f1f", zerolinecolor="#262626")
    return fig.to_html(full_html=False, include_plotlyjs=False, config={"displaylogo": False, "responsive": True})


def chart_for(chart: dict, run: Path, report: dict) -> str:
    kind = chart.get("kind"); source = run / (chart.get("source_artifact") or "")
    if kind == "price_structure":
        bars = normalize_bars(load(source))[-260:]
        if not bars: return "<div class='panel muted'>沒有可繪製的價格資料</div>"
        x = [row[0] for row in bars]; closes = [row[4] for row in bars]
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[.76, .24], vertical_spacing=.03)
        fig.add_trace(go.Candlestick(x=x, open=[r[1] for r in bars], high=[r[2] for r in bars], low=[r[3] for r in bars], close=closes, name="K線"), row=1, col=1)
        for name, values in [("EMA20", ema(closes, 20)), ("SMA50", sma(closes, 50)), ("SMA200", sma(closes, 200))]:
            fig.add_trace(go.Scatter(x=x, y=values, name=name, mode="lines"), row=1, col=1)
        fig.add_trace(go.Bar(x=x, y=[r[5] for r in bars], name="成交量"), row=2, col=1)
        fig.update_layout(xaxis_rangeslider_visible=False)
        return fig_html(fig, 540)
    if kind in {"technical_snapshot", "level_map"}:
        tech = report.get("modules", {}).get("technical", {}).get("metrics", {})
        if not tech and source.exists(): tech = load(source).get("technical", {})
        if kind == "technical_snapshot":
            momentum = tech.get("momentum", {})
            rows = [("20日報酬", (tech.get("return_20d") or 0) * 100), ("90日報酬", (tech.get("return_90d") or 0) * 100),
                    ("RSI14", momentum.get("rsi14") or 0), ("RV20", (tech.get("realized_vol_20d_annualized") or 0) * 100)]
            fig = go.Figure(go.Bar(x=[r[0] for r in rows], y=[r[1] for r in rows], text=[f"{r[1]:.1f}" for r in rows], textposition="outside"))
            return fig_html(fig, 320)
        price = tech.get("last_price"); sr = tech.get("support_resistance", {})
        if not isinstance(price, (int, float)): return ""
        supports = sorted([x for x in sr.get("supports", []) if isinstance(x, (int, float)) and x < price], reverse=True)[:5]
        resistances = sorted([x for x in sr.get("resistances", []) if isinstance(x, (int, float)) and x > price])[:5]
        levels = [(value, f"支撐 S{i+1}", "#22c55e") for i, value in enumerate(supports)] + [(price, "參考價", "#fafafa")] + [(value, f"壓力 R{i+1}", "#ef4444") for i, value in enumerate(resistances)]
        levels.sort(key=lambda item: item[0])
        fig = go.Figure(go.Bar(y=[i[1] for i in levels], x=[i[0] for i in levels], orientation="h", marker_color=[i[2] for i in levels], text=[f"${i[0]:.2f}" for i in levels], textposition="outside", name="價格結構"))
        fig.update_layout(xaxis_title="價格（USD）", yaxis_title="已計算結構", showlegend=False)
        return fig_html(fig, 340)
    if kind == "options_variance":
        data = load(source); rows = [item for item in data.get("expiry_features", []) if item.get("total_variance") is not None]
        if not rows: return "<div class='panel muted'>期權總變異資料不可用</div>"
        fig = go.Figure(go.Bar(x=[i.get("expiry") for i in rows], y=[i.get("total_variance") for i in rows], text=[f"{i.get('total_variance'):.4f}" for i in rows], textposition="outside", name="總變異"))
        return fig_html(fig, 320)
    if kind == "gamma_structure":
        data = load(source); status = data.get("gamma_status") or data.get("status")
        usable = [i for i in data.get("strike_structure", []) if isinstance(i.get("total_gross_gamma_notional_per_1pct_spot"), (int, float)) and i.get("total_gross_gamma_notional_per_1pct_spot") > 0]
        if not usable: return f"<div class='panel missing'>Gamma 圖已抑制 · {esc(status or '不可用')}</div>"
        fig = go.Figure(go.Bar(x=[i["strike"] for i in usable], y=[i["total_gross_gamma_notional_per_1pct_spot"] for i in usable], name="Gross Gamma / 1%"))
        return fig_html(fig, 340)
    if kind == "kelly_position_ladder":
        guidance = report.get("modules", {}).get("risk", {}).get("metrics", {}).get("position_guidance", {}); variants = guidance.get("variants", {})
        labels = [label for label in ("full", "half", "quarter") if label in variants]
        if not labels: return "<div class='panel muted'>Kelly 階梯不可用 · 請查看僅風險 fallback</div>"
        theoretical = [variants[l].get("theoretical_post_overlay_fraction", 0) * 100 for l in labels]
        final = [variants[l].get("final_fraction", 0) * 100 for l in labels]
        fig = go.Figure(); fig.add_trace(go.Bar(x=[l.upper() for l in labels], y=theoretical, name="風險調整後 Kelly %", text=[f"{x:.2f}%" for x in theoretical], textposition="outside"))
        fig.add_trace(go.Bar(x=[l.upper() for l in labels], y=final, name="套用上限後最終 %", text=[f"{x:.2f}%" for x in final], textposition="outside"))
        fig.update_layout(barmode="group", yaxis_title="NAV %")
        return fig_html(fig, 340)
    data = chart.get("data")
    if isinstance(data, list) and data and all(isinstance(i, dict) for i in data):
        x_key = chart.get("config", {}).get("x"); y_key = chart.get("config", {}).get("y")
        if x_key and y_key:
            return fig_html(go.Figure(go.Bar(x=[i.get(x_key) for i in data], y=[i.get(y_key) for i in data])), 320)
    return "<div class='panel muted'>此圖表類型尚無 renderer</div>"


def _structured_bullets_html(title: str | None, value: str) -> str | None:
    if not isinstance(value, str):
        return None
    labels = ["看什麼：", "讀到什麼：", "為什麼重要：", "限制："]
    if all(label in value for label in labels):
        parts = []
        for index, label in enumerate(labels[:-1]):
            parts.append(f"<li><b>{esc(label[:-1])}</b>：{esc(value.split(label, 1)[1].split(labels[index + 1], 1)[0].strip())}</li>")
        parts.append(f"<li><b>限制</b>：{esc(value.split('限制：', 1)[1].strip())}</li>")
        return "<ul>" + "".join(parts) + "</ul>"
    scenarios = ["下行情景：", "基準情景：", "上行情景："]
    if title and "估值判斷" in title and all(label in value for label in scenarios):
        parts = []
        for index, label in enumerate(scenarios[:-1]):
            parts.append(f"<li><b>{esc(label[:-1])}</b>：{esc(value.split(label, 1)[1].split(scenarios[index + 1], 1)[0].strip())}</li>")
        parts.append(f"<li><b>上行情景</b>：{esc(value.split('上行情景：', 1)[1].strip())}</li>")
        return "<ul>" + "".join(parts) + "</ul>"
    return None


def block_html(block: dict) -> str:
    kind = block.get("type"); title = block.get("title"); body = ""
    if kind in {"paragraph", "callout"}:
        value = str(block.get("text") or "")
        body = _structured_bullets_html(title, value) or f"<p>{esc(value)}</p>"
    elif kind == "markdown": body = MD(block.get("text") or "")
    elif kind == "bullets": body = "<ul>" + "".join(f"<li>{esc(i)}</li>" for i in block.get("items", [])) + "</ul>"
    elif kind == "metric_grid":
        body = "<div class='grid12'>" + "".join(f"<div class='cell span3 metric'><div class='label'>{esc(i.get('label'))}</div><div class='value'>{esc(i.get('value'))}</div></div>" for i in block.get("items", [])) + "</div>"
    return f"<div class='block'>{'<h3>'+esc(title)+'</h3>' if title else ''}{body}</div>"


def explanation(chart: dict) -> str:
    interpretation = chart.get("interpretation", {})
    pairs = [("這是什麼", "what", "what_observed"), ("怎麼看", "read", "read_result"), ("為什麼重要", "why", "why_now"), ("限制", "limit", "limit_effect")]
    return "<div class='explain'>" + "".join(f"<div><div class='xk'>{key}</div><div class='xv'>{esc(interpretation.get(definition,''))}</div><div class='xo'>{esc(interpretation.get(observation,''))}</div></div>" for key, definition, observation in pairs) + "</div>"


def kelly_guidance_html(module: dict) -> str:
    metrics = module.get("metrics", {}); guidance = metrics.get("position_guidance", {}) or {}; kelly = metrics.get("kelly", {}) or {}
    if not guidance: return ""
    formula = kelly.get("out_of_sample_formula", {}) if kelly.get("out_of_sample_formula", {}).get("trades") else kelly.get("full_sample_formula", {})
    empirical = kelly.get("conditional_oos_kelly_fraction") if kelly.get("conditional_oos_kelly_fraction") is not None else kelly.get("exploratory_full_sample_kelly_fraction")
    selected_edge = kelly.get("selected_edge", {}) or {}; setup = guidance.get("setup_match", {}) or {}; sample = guidance.get("sample_confidence", {}) or {}; overlay = guidance.get("risk_overlay_combination", {}) or {}
    status = ("<div class='kelly-status'>"
              f"<div><div class='k'>帳戶</div><div class='v'>{esc(guidance.get('simulation_label'))}</div></div>"
              f"<div><div class='k'>當前 RV20</div><div class='v'>{pct(guidance.get('current_realized_vol_20d_annualized'))}</div></div>"
              f"<div><div class='k'>單日 1σ</div><div class='v'>{pct(guidance.get('daily_sigma'))}</div></div>"
              f"<div><div class='k'>樣本層級</div><div class='v'>{esc(sample.get('tier'))}</div></div>"
        f"<div><div class='k'>設定匹配</div><div class='v'>{esc(setup.get('status'))}</div></div>"
        f"<div><div class='k'>保守參考</div><div class='v kelly-guide'>{esc(guidance.get('guidance_variant'))} · {pct(guidance.get('guidance_fraction'))}</div></div></div>")
    formula_table = ("<table><thead><tr><th>優勢輸入</th><th>數值</th><th>解讀</th></tr></thead><tbody>"
                     f"<tr><td>p / 勝率</td><td>{pct(formula.get('p_win_rate'))}</td><td>優先使用同 setup 歷史樣本</td></tr>"
                     f"<tr><td>b / 平均盈利 ÷ 平均虧損</td><td>{num(formula.get('b_avg_win_over_avg_loss'),3)}</td><td>payoff 不對稱</td></tr>"
                     f"<tr><td>公式 Kelly</td><td>{pct(formula.get('raw_formula_kelly_fraction'))}</td><td>(p·b − (1−p)) / b</td></tr>"
                     f"<tr><td>經驗對數增長</td><td>{pct(empirical)}</td><td>最大化平均 log(1+f·r)</td></tr>"
                     f"<tr><td>選用基礎優勢</td><td>{pct(selected_edge.get('fraction'))}</td><td>{esc(selected_edge.get('source'))}</td></tr>"
                     f"<tr><td>RV / 事件風險折扣</td><td>{pct(overlay.get('combined_haircut'))}</td><td>{esc(overlay.get('policy'))}</td></tr></tbody></table>")
    rows = []
    for label in ("full", "half", "quarter"):
        item = guidance.get("variants", {}).get(label)
        if not item: continue
        klass = " class='guide'" if label == guidance.get("guidance_variant") else ""
        rows.append(f"<tr{klass}><td>{label.upper()}</td><td>{pct(item.get('theoretical_post_overlay_fraction'),2)}</td><td>{pct(item.get('final_fraction'),2)}</td><td>{money(item.get('notional_dollars'),0)}</td><td>{num(item.get('exact_fractional_shares'),2)}</td><td>{pct(item.get('one_day_one_sigma_nav_fraction'),3)}</td><td>{money(item.get('one_day_one_sigma_dollars'),2)}</td><td>{money(item.get('stop_loss_dollars'),2)}</td><td>{esc(item.get('binding_constraint'))}</td></tr>")
    variants_table = ("<table class='kelly-table'><thead><tr><th>層級</th><th>風險折扣後</th><th>最終 NAV</th><th>$10K 金額</th><th>股數</th><th>1日 1σ NAV</th><th>1日 1σ $</th><th>Stop 損失 $</th><th>Binding</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>") if rows else f"<div class='missing'>沒有正 Kelly 變體 · {esc(guidance.get('interpretation'))}</div>"
    return "<div class='panel'><h3>Kelly 計算與 $10,000 倉位指引</h3>" + status + formula_table + "<br>" + variants_table + "</div>"


def _anchor_class(role: str) -> str:
    return role if role in {"support", "resistance", "intraday", "intraday_support", "intraday_resistance", "moving_average", "volatility", "current", "volume_node_support", "volume_node_resistance"} else "current"


def _anchors_html(node: dict) -> str:
    anchors = node.get("price_anchors", [])
    if anchors:
        chips = []
        for anchor in anchors:
            if not isinstance(anchor, dict): continue
            role = _anchor_class(str(anchor.get("role") or "current"))
            title = f"來源: {anchor.get('source','—')} | 方法: {anchor.get('method','—')} | 信心: {anchor.get('confidence','—')} | 狀態: {anchor.get('status','—')}"
            chips.append(f"<span class='price-anchor {esc(role)}' title='{esc(title)}'><span>{esc(anchor.get('label'))}</span><span class='p'>{money(anchor.get('value'),2)}</span></span>")
        return "<div class='tree-anchors'>" + "".join(chips) + "</div>"
    refs = node.get("price_reference", {})
    if not refs: return ""
    return "<div class='tree-anchors'>" + "".join(f"<span class='tree-ref'>{esc(key)}={money(value,2)}</span>" for key, value in refs.items()) + "</div>"


def scenario_node_html(node: dict, root=False) -> str:
    watch = node.get("watch", [])
    details = ("<details><summary>展開：觀察 / 解讀 / 失效條件</summary>"
               f"<div class='tree-detail'><b>觀察：</b> {esc(' · '.join(str(x) for x in watch))}</div>"
               f"<div class='tree-detail'><b>解讀：</b> {esc(node.get('interpretation'))}</div>"
               f"<div class='tree-detail'><b>失效：</b> {esc(node.get('invalidation'))}</div>"
               f"<div class='tree-detail'><b>行動邊界：</b> {esc(node.get('action_boundary'))}</div></details>")
    tier = str(node.get("sizing_tier") or "none")
    card = (f"<div class='tree-card{' root' if root else ''}'><div class='tree-label'>{esc(node.get('label'))}</div>"
            f"<div class='tree-trigger'><b>條件</b> {esc(node.get('trigger'))}</div>{_anchors_html(node)}"
            f"<div class='tree-response'><b>下一步</b> {esc(node.get('response'))}</div>"
            f"<span class='tree-tier {esc(tier)}'>倉位層級={esc(TIER_LABEL.get(tier,tier))}</span>{details}</div>")
    children = node.get("children", [])
    if not children: return f"<li>{card}</li>"
    return f"<li>{card}<ul>{''.join(scenario_node_html(child) for child in children)}</ul></li>"


def scenario_tree_html(tree: dict) -> str:
    meta = (f"<div class='scenario-meta'><span>週期={esc(tree.get('horizon'))}</span><span>證據狀態={esc(tree.get('evidence_status'))}</span>"
            + (f"<span>開盤區間={esc(tree.get('opening_range_minutes'))} 分鐘</span>" if tree.get("opening_range_minutes") else "")
            + (f"<span>生成方式={esc(tree.get('construction_policy'))}</span>" if tree.get("construction_policy") else "") + "</div>")
    legend = "<div class='anchor-legend'><span class='price-anchor support'>支撐</span><span class='price-anchor resistance'>壓力</span><span class='price-anchor intraday'>當日 VWAP/OR</span><span class='price-anchor moving_average'>均線</span><span class='price-anchor volatility'>ATR/波動帶</span><span class='price-anchor current'>參考/當前價</span></div>"
    return f"<div class='panel'><h3>{esc(tree.get('title'))}</h3>{meta}{legend}<div class='scenario-wrap'><div class='tree'><ul>{scenario_node_html(tree.get('root',{}),root=True)}</ul></div></div></div>"


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--structured-report", required=True); ap.add_argument("--run-dir", required=True); ap.add_argument("--output", required=True); ap.add_argument("--modules")
    args = ap.parse_args(); run = Path(args.run_dir); data = load(Path(args.structured_report)); selected = set(args.modules.split(",")) if args.modules else set(data.get("modules", {}))
    state = data.get("research_state", "UNSPECIFIED"); state_class = "good" if state == "RESEARCH_READY" else "warn"; summary = data.get("summary", {})
    header = ("<header class='top'><div><div class='kicker'>股票研究報告 // 證據鏈</div>"
              f"<h1>{esc(data.get('symbol'))} · {esc(data.get('title'))}</h1><span class='state {state_class}'>{esc(state)}</span></div>"
              f"<div class='meta'>RUN {esc(data.get('run_id'))}<br>資料截至 {esc(data.get('as_of'))}<br>證據截止 {esc(data.get('evidence_cutoff'))}<br>價格時間 {esc(data.get('price_timestamp'))}</div></header>")
    nav = "<nav class='nav'>" + "".join(f"<a href='#{esc(name)}'>{esc(MODULE_NAV.get(name,name))}</a>" for name in data.get("modules", {}) if name in selected) + "</nav>"
    summary_cells = []
    for key, label in [("headline", "核心結論"), ("thesis", "投資論點"), ("variant_perception", "差異化判斷"), ("primary_horizon", "主要週期")]:
        if summary.get(key): summary_cells.append(f"<div class='cell span6'><div class='label'>{label}</div><div>{esc(summary.get(key))}</div></div>")
    if not summary_cells: summary_cells = ["<div class='cell span12 muted'>尚未提供結構化摘要</div>"]
    summary_html = "<div class='grid12'>" + "".join(summary_cells) + "</div>"
    modules = []
    for name, module in data.get("modules", {}).items():
        if name not in selected: continue
        pieces = [f"<section class='module' id='{esc(name)}'><div class='module-head'><div class='panel-title'>{esc(module.get('title',name))}</div><div class='statusline'>狀態={esc(module.get('status'))} · 信心={esc(module.get('confidence'))} · 新鮮度={esc(module.get('freshness_status'))}</div></div><div class='body-grid'>"]
        if module.get("blocks"): pieces.append("<div class='panel'>" + "".join(block_html(block) for block in module["blocks"]) + "</div>")
        if module.get("judgments"):
            judgments = "".join(f"<div class='judgment'><div class='jlabel'>{esc(item.get('label'))} · 信心={esc(item.get('confidence'))}</div><strong>{esc(item.get('conclusion'))}</strong>{'<div class=muted>'+esc(item.get('why'))+'</div>' if item.get('why') else ''}</div>" for item in module["judgments"])
            pieces.append("<div class='panel'><h3>關鍵判斷</h3>" + judgments + "</div>")
        if module.get("knowledge_notes"):
            notes = "".join(f"<div class='knowledge'><div class='kt'>判讀知識 · {esc(note.get('title'))}</div><div>{esc(note.get('explanation'))}</div>{'<div class=muted>本報告應用：'+esc(note.get('applied_to_current_report'))+'</div>' if note.get('applied_to_current_report') else ''}</div>" for note in module["knowledge_notes"])
            pieces.append("<div class='panel'><h3>判讀知識</h3>" + notes + "</div>")
        if name == "risk": pieces.append(kelly_guidance_html(module))
        for chart in module.get("charts", []): pieces.append(f"<div class='panel'><div class='chart-wrap'><div class='chart-title'>{esc(chart.get('title'))}{' // '+esc(chart.get('subtitle')) if chart.get('subtitle') else ''}</div><div class='chart'>{chart_for(chart,run,data)}</div>{explanation(chart)}</div></div>")
        for tree in module.get("scenario_trees", []): pieces.append(scenario_tree_html(tree))
        if module.get("missing_fields"):
            resolutions = {item.get("field"): item for item in module.get("evidence_resolution", []) if isinstance(item, dict)}; rows=[]
            for item in module["missing_fields"]:
                resolution=resolutions.get(item,{}); rows.append(f"<li><b>{esc(item)}</b> · 狀態={esc(resolution.get('status','UNRESOLVED'))} · 下一步={esc(resolution.get('next_action','記錄來源並重試'))}</li>")
            pieces.append("<div class='panel missing'><h3>缺失欄位 / 證據解析</h3><ul>" + "".join(rows) + "</ul></div>")
        pieces.append("</div></section>"); modules.append("".join(pieces))
    limitations = ""
    if data.get("global_limitations"): limitations = "<section class='module'><div class='module-head'><div class='panel-title'>全局限制</div></div><div class='panel missing'><ul>" + "".join(f"<li>{esc(i)}</li>" for i in data["global_limitations"]) + "</ul></div></section>"
    document = ("<!doctype html><html lang='zh-Hant'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
                f"<title>{esc(data.get('symbol'))} 股票研究報告</title><style>{CSS}</style><script>{PLOTLY_JS}</script></head><body><div class='shell'>"
                f"{header}{nav}{summary_html}{''.join(modules)}{limitations}"
                "<footer class='footer'>語義來源：structured_report.json · 未提供帳戶規模時預設以 $10,000 模擬 · HTML 僅為呈現層 · 非自動交易指令</footer></div></body></html>")
    Path(args.output).write_text(document, encoding="utf-8"); print(json.dumps({"written": args.output, "modules": sorted(selected)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
