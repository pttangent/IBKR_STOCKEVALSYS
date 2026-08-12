#!/usr/bin/env python3
"""Render terminal-style HTML from canonical structured_report.json.

The renderer never parses Markdown for semantics. Every chart is followed by a
WHAT / READ / WHY / LIMIT explanation block taken from the structured report.
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
    raise SystemExit("Install skill/requirements-html.txt (mistune, plotly)") from exc

MD = mistune.create_markdown(plugins=["table", "strikethrough"])
PLOTLY_JS = get_plotlyjs()

CSS = r'''
:root{--bg:#0a0a0a;--fg:#fafafa;--muted:#a1a1aa;--border:#262626;--soft:#171717;--good:#22c55e;--bad:#ef4444;--warn:#f59e0b}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--fg);font-family:"Space Mono","JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13px;line-height:1.55}.shell{max-width:1480px;margin:auto;padding:20px}.top{border-bottom:1px solid var(--border);padding:12px 0 18px;display:grid;grid-template-columns:1fr auto;gap:20px;align-items:end}.kicker,.label,.panel-title,.chart-title{text-transform:uppercase;letter-spacing:.12em;font-weight:700}.kicker{font-size:11px;color:var(--muted)}h1{font-size:28px;line-height:1.1;margin:5px 0 0}.meta{text-align:right;color:var(--muted);font-size:11px}.state{display:inline-block;padding:4px 8px;border:1px solid var(--border);color:var(--fg);margin-top:6px}.state.good{color:var(--good);border-color:#14532d}.state.warn{color:var(--warn);border-color:#713f12}.nav{position:sticky;top:0;z-index:10;background:#0a0a0af2;border-bottom:1px solid var(--border);padding:8px 0;white-space:nowrap;overflow:auto}.nav a{color:var(--muted);text-decoration:none;margin-right:18px;font-size:11px;text-transform:uppercase}.nav a:hover{color:var(--fg)}.grid12{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:0;border-left:1px solid var(--border);border-top:1px solid var(--border);margin-top:18px}.cell{border-right:1px solid var(--border);border-bottom:1px solid var(--border);padding:14px}.span3{grid-column:span 3}.span6{grid-column:span 6}.span12{grid-column:span 12}.metric .label{font-size:10px;color:var(--muted)}.metric .value{font-size:21px;font-weight:700;margin-top:6px}.module{margin-top:28px;border-top:1px solid var(--border)}.module-head{display:flex;justify-content:space-between;gap:16px;border-bottom:1px solid var(--border);padding:12px 0}.panel-title{font-size:14px}.statusline{font-size:10px;color:var(--muted)}.body-grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));border-left:1px solid var(--border)}.panel{grid-column:span 12;border-right:1px solid var(--border);border-bottom:1px solid var(--border);padding:16px}.panel h3{font-size:12px;text-transform:uppercase;letter-spacing:.1em;margin:0 0 12px}.muted{color:var(--muted)}.block{margin:0 0 14px}.block p{margin:0 0 8px}.block ul{padding-left:18px}.judgment{border-left:2px solid var(--fg);padding:8px 12px;margin:10px 0;background:#111}.judgment .jlabel{color:var(--muted);font-size:10px;text-transform:uppercase}.knowledge{border:1px solid #3f3f46;background:#101010;padding:12px;margin:10px 0}.knowledge .kt{color:var(--warn);font-size:10px;text-transform:uppercase;font-weight:700;letter-spacing:.1em}.chart-wrap{border:1px solid var(--border);margin:12px 0 20px;background:#080808}.chart-title{padding:10px 12px;border-bottom:1px solid var(--border);font-size:11px}.chart{min-height:280px}.explain{display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid var(--border)}.explain>div{padding:10px;border-right:1px solid var(--border)}.explain>div:last-child{border-right:0}.explain .xk{font-size:9px;color:var(--muted);letter-spacing:.12em;font-weight:700}.explain .xv{font-size:11px;margin-top:5px}.missing{color:var(--warn)}table{border-collapse:collapse;width:100%;font-size:11px}th,td{border:1px solid var(--border);padding:7px;text-align:left;vertical-align:top}th{color:var(--muted);text-transform:uppercase}.footer{border-top:1px solid var(--border);margin-top:32px;padding:16px 0 30px;color:var(--muted);font-size:10px}@media(max-width:900px){.shell{padding:12px}.top{grid-template-columns:1fr}.meta{text-align:left}.span3,.span6{grid-column:span 12}.explain{grid-template-columns:1fr}.explain>div{border-right:0;border-bottom:1px solid var(--border)}.explain>div:last-child{border-bottom:0}}
'''


def load(path: Path, default=None):
    if not path.exists():
        return {} if default is None else default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def esc(value) -> str:
    return html.escape("—" if value is None or value == "" else str(value))


def normalize_bars(data: dict) -> list[tuple]:
    raw = data.get("bars") or data.get("results") or data.get("data") or []
    out = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        try:
            o = float(row.get("open", row.get("o")))
            h = float(row.get("high", row.get("h")))
            l = float(row.get("low", row.get("l")))
            c = float(row.get("close", row.get("c")))
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
    previous = sum(values[:n]) / n
    out[n - 1] = previous
    alpha = 2 / (n + 1)
    for i in range(n, len(values)):
        previous = alpha * values[i] + (1 - alpha) * previous
        out[i] = previous
    return out


def sma(values: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    acc = 0.0
    for i, value in enumerate(values):
        acc += value
        if i >= n:
            acc -= values[i - n]
        if i >= n - 1:
            out[i] = acc / n
    return out


def fig_html(fig, height=380) -> str:
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#080808",
        plot_bgcolor="#080808",
        font=dict(family="Space Mono, monospace", color="#d4d4d8", size=10),
        margin=dict(l=48, r=18, t=38, b=40),
        height=height,
        hovermode="x unified",
        legend=dict(orientation="h", y=1.03, x=0),
    )
    fig.update_xaxes(gridcolor="#1f1f1f", zerolinecolor="#262626")
    fig.update_yaxes(gridcolor="#1f1f1f", zerolinecolor="#262626")
    return fig.to_html(full_html=False, include_plotlyjs=False, config={"displaylogo": False, "responsive": True})


def chart_for(chart: dict, run: Path, report: dict) -> str:
    kind = chart.get("kind")
    source = run / (chart.get("source_artifact") or "")
    if kind == "price_structure":
        bars = normalize_bars(load(source))[-260:]
        if not bars:
            return "<div class='panel muted'>NO PLOTTABLE PRICE DATA</div>"
        x = [row[0] for row in bars]
        closes = [row[4] for row in bars]
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[.76, .24], vertical_spacing=.03)
        fig.add_trace(go.Candlestick(x=x, open=[row[1] for row in bars], high=[row[2] for row in bars], low=[row[3] for row in bars], close=closes, name="OHLC"), row=1, col=1)
        for name, values in [("EMA20", ema(closes, 20)), ("SMA50", sma(closes, 50)), ("SMA200", sma(closes, 200))]:
            fig.add_trace(go.Scatter(x=x, y=values, name=name, mode="lines"), row=1, col=1)
        fig.add_trace(go.Bar(x=x, y=[row[5] for row in bars], name="VOLUME"), row=2, col=1)
        fig.update_layout(xaxis_rangeslider_visible=False)
        return fig_html(fig, 540)

    if kind in {"technical_snapshot", "level_map"}:
        tech = report.get("modules", {}).get("technical", {}).get("metrics", {})
        if not tech and source.exists():
            tech = load(source).get("technical", {})
        if kind == "technical_snapshot":
            momentum = tech.get("momentum", {})
            rows = [
                ("20D", (tech.get("return_20d") or 0) * 100),
                ("90D", (tech.get("return_90d") or 0) * 100),
                ("RSI14", momentum.get("rsi14") or 0),
                ("RV20", (tech.get("realized_vol_20d_annualized") or 0) * 100),
            ]
            fig = go.Figure(go.Bar(x=[row[0] for row in rows], y=[row[1] for row in rows], text=[f"{row[1]:.1f}" for row in rows], textposition="outside"))
            return fig_html(fig, 320)
        price = tech.get("last_price")
        sr = tech.get("support_resistance", {})
        if not isinstance(price, (int, float)):
            return ""
        # Keep the current price between the two sides of the map.  Provider
        # labels can be stale or loosely ordered, so enforce the numeric
        # relationship instead of drawing a misleading categorical chart.
        supports = sorted(
            [x for x in sr.get("supports", []) if isinstance(x, (int, float)) and x < price],
            reverse=True,
        )[:5]
        resistances = sorted(
            [x for x in sr.get("resistances", []) if isinstance(x, (int, float)) and x > price],
        )[:5]
        levels = [(value, f"S{i+1}", "#22c55e") for i, value in enumerate(supports)]
        levels += [(price, "PRICE", "#fafafa")]
        levels += [(value, f"R{i+1}", "#ef4444") for i, value in enumerate(resistances)]
        levels.sort(key=lambda item: item[0])
        labels = [item[1] for item in levels]
        values = [item[0] for item in levels]
        colors = [item[2] for item in levels]
        fig = go.Figure(go.Bar(y=labels, x=values, orientation="h", marker_color=colors, text=[f"{value:.2f}" for value in values], textposition="outside", name="PRICE LEVEL"))
        fig.update_layout(xaxis_title="PRICE (USD)", yaxis_title="OBSERVED LEVEL", showlegend=False)
        return fig_html(fig, 340)

    if kind == "options_variance":
        data = load(source)
        rows = [item for item in data.get("expiry_features", []) if item.get("total_variance") is not None]
        if not rows:
            return "<div class='panel muted'>OPTION VARIANCE UNAVAILABLE</div>"
        fig = go.Figure(go.Bar(x=[item.get("expiry") for item in rows], y=[item.get("total_variance") for item in rows], text=[f"{item.get('total_variance'):.4f}" for item in rows], textposition="outside", name="TOTAL VARIANCE"))
        return fig_html(fig, 320)

    if kind == "gamma_structure":
        data = load(source)
        status = data.get("gamma_status") or data.get("status")
        usable = [item for item in data.get("strike_structure", []) if isinstance(item.get("total_gross_gamma_notional_per_1pct_spot"), (int, float)) and item.get("total_gross_gamma_notional_per_1pct_spot") > 0]
        if not usable:
            return f"<div class='panel missing'>GAMMA CHART SUPPRESSED · {esc(status or 'UNAVAILABLE')}</div>"
        fig = go.Figure(go.Bar(x=[item["strike"] for item in usable], y=[item["total_gross_gamma_notional_per_1pct_spot"] for item in usable], name="GROSS GAMMA / 1%"))
        return fig_html(fig, 340)

    data = chart.get("data")
    if isinstance(data, list) and data and all(isinstance(item, dict) for item in data):
        x_key = chart.get("config", {}).get("x")
        y_key = chart.get("config", {}).get("y")
        if x_key and y_key:
            fig = go.Figure(go.Bar(x=[item.get(x_key) for item in data], y=[item.get(y_key) for item in data]))
            return fig_html(fig, 320)
    return "<div class='panel muted'>NO RENDERER FOR THIS CHART KIND</div>"


def block_html(block: dict) -> str:
    kind = block.get("type")
    title = block.get("title")
    body = ""
    if kind in {"paragraph", "callout"}:
        body = f"<p>{esc(block.get('text'))}</p>"
    elif kind == "markdown":
        body = MD(block.get("text") or "")
    elif kind == "bullets":
        body = "<ul>" + "".join(f"<li>{esc(item)}</li>" for item in block.get("items", [])) + "</ul>"
    elif kind == "metric_grid":
        body = "<div class='grid12'>" + "".join(
            f"<div class='cell span3 metric'><div class='label'>{esc(item.get('label'))}</div><div class='value'>{esc(item.get('value'))}</div></div>"
            for item in block.get("items", [])
        ) + "</div>"
    return f"<div class='block'>{'<h3>'+esc(title)+'</h3>' if title else ''}{body}</div>"


def explanation(chart: dict) -> str:
    interpretation = chart.get("interpretation", {})
    pairs = [("WHAT", "what", "what_observed"), ("READ", "read", "read_result"),
             ("WHY", "why", "why_now"), ("LIMIT", "limit", "limit_effect")]
    return "<div class='explain'>" + "".join(
        f"<div><div class='xk'>{key}</div><div class='xv'>{esc(interpretation.get(definition, ''))}</div>"
        f"<div class='xo'>{esc(interpretation.get(observation, ''))}</div></div>"
        for key, definition, observation in pairs
    ) + "</div>"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--structured-report", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--modules")
    args = ap.parse_args()

    run = Path(args.run_dir)
    data = load(Path(args.structured_report))
    selected = set(args.modules.split(",")) if args.modules else set(data.get("modules", {}))
    state = data.get("research_state", "UNSPECIFIED")
    state_class = "good" if state == "RESEARCH_READY" else "warn"
    summary = data.get("summary", {})

    header = (
        "<header class='top'><div><div class='kicker'>STOCK_EVAL_REPORT // EVIDENCE-CHAIN</div>"
        f"<h1>{esc(data.get('symbol'))} · {esc(data.get('title'))}</h1>"
        f"<span class='state {state_class}'>{esc(state)}</span></div>"
        f"<div class='meta'>RUN {esc(data.get('run_id'))}<br>AS_OF {esc(data.get('as_of'))}<br>"
        f"CUTOFF {esc(data.get('evidence_cutoff'))}<br>PRICE_TS {esc(data.get('price_timestamp'))}</div></header>"
    )
    nav = "<nav class='nav'>" + "".join(
        f"<a href='#{esc(name)}'>{esc(name)}</a>" for name in data.get("modules", {}) if name in selected
    ) + "</nav>"

    summary_cells = []
    for key, label in [("headline", "HEADLINE"), ("thesis", "THESIS"), ("variant_perception", "VARIANT PERCEPTION"), ("primary_horizon", "PRIMARY HORIZON")]:
        if summary.get(key):
            summary_cells.append(f"<div class='cell span6'><div class='label'>{label}</div><div>{esc(summary.get(key))}</div></div>")
    if not summary_cells:
        summary_cells = ["<div class='cell span12 muted'>STRUCTURED SUMMARY NOT PROVIDED</div>"]
    summary_html = "<div class='grid12'>" + "".join(summary_cells) + "</div>"

    modules = []
    for name, module in data.get("modules", {}).items():
        if name not in selected:
            continue
        pieces = [
            f"<section class='module' id='{esc(name)}'><div class='module-head'><div class='panel-title'>{esc(module.get('title', name))}</div>"
            f"<div class='statusline'>STATUS={esc(module.get('status'))} · CONF={esc(module.get('confidence'))} · FRESH={esc(module.get('freshness_status'))}</div></div><div class='body-grid'>"
        ]
        if module.get("blocks"):
            pieces.append("<div class='panel'>" + "".join(block_html(block) for block in module["blocks"]) + "</div>")
        if module.get("judgments"):
            judgments = "".join(
                f"<div class='judgment'><div class='jlabel'>{esc(item.get('label'))} · CONF={esc(item.get('confidence'))}</div>"
                f"<strong>{esc(item.get('conclusion'))}</strong>"
                f"{'<div class=muted>'+esc(item.get('why'))+'</div>' if item.get('why') else ''}</div>"
                for item in module["judgments"]
            )
            pieces.append("<div class='panel'><h3>KEY JUDGMENTS / 關鍵判斷</h3>" + judgments + "</div>")
        if module.get("knowledge_notes"):
            notes = "".join(
                f"<div class='knowledge'><div class='kt'>KNOWLEDGE · {esc(note.get('title'))}</div><div>{esc(note.get('explanation'))}</div>"
                f"{'<div class=muted>APPLIED: '+esc(note.get('applied_to_current_report'))+'</div>' if note.get('applied_to_current_report') else ''}</div>"
                for note in module["knowledge_notes"]
            )
            pieces.append("<div class='panel'><h3>KNOWLEDGE NOTES / 判讀知識</h3>" + notes + "</div>")
        for chart in module.get("charts", []):
            pieces.append(
                f"<div class='panel'><div class='chart-wrap'><div class='chart-title'>{esc(chart.get('title'))}"
                f"{' // '+esc(chart.get('subtitle')) if chart.get('subtitle') else ''}</div>"
                f"<div class='chart'>{chart_for(chart, run, data)}</div>{explanation(chart)}</div></div>"
            )
        if module.get("missing_fields"):
            resolutions = {item.get("field"): item for item in module.get("evidence_resolution", []) if isinstance(item, dict)}
            rows = []
            for item in module["missing_fields"]:
                resolution = resolutions.get(item, {})
                rows.append(f"<li><b>{esc(item)}</b> · STATUS={esc(resolution.get('status', 'UNRESOLVED'))} · ACTION={esc(resolution.get('next_action', 'record exact source route and retry'))}</li>")
            pieces.append("<div class='panel missing'><h3>MISSING / RESOLUTION AUDIT</h3><ul>" + "".join(rows) + "</ul></div>")
        pieces.append("</div></section>")
        modules.append("".join(pieces))

    limitations = ""
    if data.get("global_limitations"):
        limitations = "<section class='module'><div class='module-head'><div class='panel-title'>GLOBAL LIMITATIONS</div></div><div class='panel missing'><ul>" + "".join(f"<li>{esc(item)}</li>" for item in data["global_limitations"]) + "</ul></div></section>"

    document = (
        "<!doctype html><html lang='zh-Hant'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{esc(data.get('symbol'))} StockEval</title><style>{CSS}</style><script>{PLOTLY_JS}</script></head><body><div class='shell'>"
        f"{header}{nav}{summary_html}{''.join(modules)}{limitations}"
        "<footer class='footer'>CANONICAL SOURCE: structured_report.json · HTML IS PRESENTATION ONLY · NOT A RECOMMENDATION</footer>"
        "</div></body></html>"
    )
    Path(args.output).write_text(document, encoding="utf-8")
    print(json.dumps({"written": args.output, "modules": sorted(selected)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
