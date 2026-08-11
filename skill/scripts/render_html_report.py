#!/usr/bin/env python3
"""Render a modular standalone HTML report from StockEval run artifacts.

The renderer is presentation-only: it does not fetch data and must not upgrade
source/evidence strength. Plot structured artifacts when available; narrative is
read from the supplied Markdown report. Missing/untrusted inputs suppress charts
instead of being converted into meaningful-looking zeros.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

try:
    import mistune
    import plotly.graph_objects as go
    from plotly.offline import get_plotlyjs
    from plotly.subplots import make_subplots
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "render_html_report.py requires 'mistune' and 'plotly'. "
        "Install skill/requirements-html.txt before rendering HTML."
    ) from exc

MD = mistune.create_markdown(plugins=["table", "strikethrough"])
PLOTLY_JS = get_plotlyjs()

MODULE_HEADINGS = {
    "overview": ["Research posture", "Thesis and variant perception", "Executive summary", "Key debates", "What changed since the prior evaluation"],
    "fundamentals": ["Company and industry overview", "Business and fundamentals", "Model summary and driver table", "Catalyst, macro, and expectation context"],
    "valuation": ["Valuation"],
    "technical": ["Technical setup"],
    "options": ["Options-implied risk", "Options & Dealer-Hedging Structure"],
    "governance": ["Claim Graph summary", "Adversarial review", "Research Arbiter"],
    "risk": ["Risk plan"],
    "scenarios": ["Scenarios"],
    "evidence": ["Source register and missing evidence", "Decision-memory record"],
}
DEFAULT_MODULES = list(MODULE_HEADINGS)
CANONICAL_STATES = {
    "RESEARCH_READY", "READY_CONDITIONAL", "WAIT_CONFIRMATION", "NEEDS_EVIDENCE",
    "RISK_BLOCKED", "MONITOR_ONLY", "THESIS_INVALIDATED",
}

CSS = r'''
:root{--bg:#07111f;--panel:#0d1a2b;--text:#e7edf7;--muted:#91a4bd;--line:#233650;--accent:#66d9ef;--good:#64d39b;--warn:#f5c451;--bad:#ff7b86;--shadow:0 12px 34px rgba(0,0,0,.22)}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:radial-gradient(circle at 80% 0,#122541 0,#07111f 38%,#050c16 100%);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI","Noto Sans TC",sans-serif;line-height:1.62}.wrap{max-width:1500px;margin:auto;padding:24px}.hero{display:grid;grid-template-columns:1fr auto;gap:24px;align-items:end;padding:28px;border:1px solid var(--line);background:linear-gradient(145deg,rgba(20,40,66,.96),rgba(9,21,36,.96));border-radius:22px;box-shadow:var(--shadow)}.eyebrow{color:var(--accent);letter-spacing:.12em;text-transform:uppercase;font-size:12px;font-weight:700}.hero h1{font-size:clamp(30px,5vw,56px);margin:6px 0 8px;line-height:1.04}.subtitle{color:var(--muted);max-width:900px}.badge{display:inline-flex;border:1px solid var(--line);border-radius:999px;padding:6px 10px;margin:3px;background:#0a1728;color:#c9d7e9;font-size:12px}.badge.good{border-color:#285b47;color:#8ee5b8}.badge.warn{border-color:#675322;color:#f7d476}.badge.bad{border-color:#6f3239;color:#ff9da6}.nav{position:sticky;top:0;z-index:20;margin:16px 0;padding:10px 12px;background:rgba(6,14,25,.88);backdrop-filter:blur(14px);border:1px solid var(--line);border-radius:14px;overflow:auto;white-space:nowrap}.nav a{display:inline-block;color:#b9c9dc;text-decoration:none;padding:7px 10px;border-radius:9px;font-size:13px}.nav a:hover{background:#15263c;color:white}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:18px 0}.metric{padding:16px 17px;border:1px solid var(--line);background:rgba(13,26,43,.91);border-radius:16px}.metric .k{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}.metric .v{font-size:25px;font-weight:750;margin-top:4px}.metric .s{font-size:12px;color:var(--muted)}section{scroll-margin-top:80px;margin:22px 0;padding:22px;border:1px solid var(--line);background:rgba(10,22,38,.92);border-radius:20px;box-shadow:0 8px 24px rgba(0,0,0,.12)}section h2{font-size:25px;margin:0 0 4px}section .deck{color:var(--muted);margin-bottom:16px}.grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.chart{border:1px solid var(--line);border-radius:15px;padding:8px;background:#081524;min-height:280px;overflow:hidden}.narrative{margin-top:16px;padding:18px;border:1px solid #20344d;border-radius:14px;background:#0b1829}.narrative h2,.narrative h3,.narrative h4{margin-top:22px}.narrative table{border-collapse:collapse;width:100%;font-size:13px;display:block;overflow-x:auto}.narrative th,.narrative td{border-bottom:1px solid #233650;padding:9px 11px;text-align:left;vertical-align:top}.narrative th{color:#dbe7f6;background:#102039}.narrative code{background:#101f33;border:1px solid #243850;padding:2px 5px;border-radius:5px;color:#d8e7fa}.callout{padding:14px 16px;border-radius:12px;border-left:4px solid var(--warn);background:#211b0d;color:#f3dfaa;margin:12px 0}.callout.bad{border-color:var(--bad);background:#241116;color:#ffc0c6}.callout.good{border-color:var(--good);background:#0c2219;color:#b5f0d0}.small{font-size:12px;color:var(--muted)}.footer{text-align:center;color:var(--muted);padding:30px 10px 60px;font-size:12px}@media(max-width:920px){.grid2{grid-template-columns:1fr}.hero{grid-template-columns:1fr}.wrap{padding:12px}section{padding:15px}.hero{padding:20px}}
'''


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def pick_json(run_dir: Path, names: list[str], patterns: list[str] | None = None) -> dict:
    for name in names:
        path = run_dir / name
        if path.exists():
            value = load_json(path)
            if isinstance(value, dict):
                return value
    for pattern in patterns or []:
        for path in sorted(run_dir.glob(pattern)):
            value = load_json(path)
            if isinstance(value, dict):
                return value
    return {}


def parse_h2_sections(text: str) -> dict[str, str]:
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", text, re.M))
    out: dict[str, str] = {}
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out[match.group(1).strip()] = text[start:end].strip()
    return out


def extract_title(text: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return m.group(1).strip() if m else "Stock research report"


def extract_research_state(text: str) -> str:
    patterns = [r"Research state\s*[:：]\s*`([^`]+)`", r"research_state\s*[:：]\s*([^\n]+)"]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(1).strip().replace(" ", "_")
    return "UNSPECIFIED"


def infer_as_of(text: str, stock_eval: dict, override: str | None) -> str:
    if override:
        return override[:10]
    for pattern in [r"As-of\s*[:：]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", r"as_of\s*[:：]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})"]:
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(1)
    value = stock_eval.get("technical", {}).get("as_of") or stock_eval.get("as_of")
    return str(value or date.today().isoformat())[:10]


def ts_to_date(value: Any) -> str:
    if isinstance(value, str):
        return value[:10]
    if isinstance(value, (int, float)):
        seconds = float(value) / (1000.0 if value > 10_000_000_000 else 1.0)
        return datetime.fromtimestamp(seconds, timezone.utc).date().isoformat()
    return ""


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


def sma_series(values: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    acc = 0.0
    for i, value in enumerate(values):
        acc += value
        if i >= n:
            acc -= values[i - n]
        if i >= n - 1:
            out[i] = acc / n
    return out


def fig_html(fig: Any, height: int = 360) -> str:
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="#081524", plot_bgcolor="#081524",
        font_color="#dce8f7", margin=dict(l=45, r=20, t=45, b=45), height=height,
        hovermode="x unified",
    )
    return fig.to_html(full_html=False, include_plotlyjs=False, config={"displaylogo": False, "responsive": True})


def normalize_market_bars(market: dict) -> list[dict]:
    raw = market.get("bars") or market.get("results") or market.get("data") or []
    out = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        def val(long: str, short: str) -> float | None:
            x = row.get(long, row.get(short))
            try:
                x = float(x)
                return x if math.isfinite(x) else None
            except Exception:
                return None
        o, h, l, c, v = val("open", "o"), val("high", "h"), val("low", "l"), val("close", "c"), val("volume", "v")
        if None in (o, h, l, c):
            continue
        out.append({"date": ts_to_date(row.get("date", row.get("t", row.get("time")))), "o": o, "h": h, "l": l, "c": c, "v": v or 0.0})
    return out


def market_chart(market: dict) -> str:
    bars = normalize_market_bars(market)[-260:]
    if not bars:
        return ""
    dates = [x["date"] for x in bars]
    closes = [x["c"] for x in bars]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.76, 0.24], vertical_spacing=0.035)
    fig.add_trace(go.Candlestick(x=dates, open=[x["o"] for x in bars], high=[x["h"] for x in bars], low=[x["l"] for x in bars], close=closes, name="OHLC"), row=1, col=1)
    fig.add_trace(go.Scatter(x=dates, y=ema(closes, 20), name="EMA20", mode="lines"), row=1, col=1)
    fig.add_trace(go.Scatter(x=dates, y=sma_series(closes, 50), name="SMA50", mode="lines"), row=1, col=1)
    fig.add_trace(go.Scatter(x=dates, y=sma_series(closes, 200), name="SMA200", mode="lines"), row=1, col=1)
    fig.add_trace(go.Bar(x=dates, y=[x["v"] for x in bars], name="Volume"), row=2, col=1)
    fig.update_layout(title="Price structure · recent ~1 year", xaxis_rangeslider_visible=False, legend=dict(orientation="h", y=1.02, x=0.01))
    return fig_html(fig, 550)


def technical_state_chart(tech: dict) -> str:
    momentum = tech.get("momentum", {})
    rows = [
        ("20D return", (tech.get("return_20d") or 0) * 100),
        ("90D return", (tech.get("return_90d") or 0) * 100 if tech.get("return_90d") is not None else 0),
        ("RSI14", momentum.get("rsi14") or 0),
        ("RV20 ann.", (tech.get("realized_vol_20d_annualized") or 0) * 100),
    ]
    fig = go.Figure(go.Bar(x=[x[0] for x in rows], y=[x[1] for x in rows], text=[f"{x[1]:.1f}" for x in rows], textposition="outside"))
    fig.update_layout(title="Technical state snapshot", showlegend=False)
    return fig_html(fig, 330)


def support_chart(tech: dict) -> str:
    price = tech.get("last_price")
    if price is None:
        return ""
    sr = tech.get("support_resistance", {})
    supports = [x for x in (sr.get("supports") or [])[:5] if isinstance(x, (int, float))]
    resistances = [x for x in (sr.get("resistances") or [])[:5] if isinstance(x, (int, float))]
    labels = ["Price"] + [f"S{i+1}" for i in range(len(supports))] + [f"R{i+1}" for i in range(len(resistances))]
    values = [price] + supports + resistances
    fig = go.Figure(go.Bar(y=labels, x=values, orientation="h", text=[f"{x:,.2f}" for x in values], textposition="outside"))
    fig.update_layout(title="Observed price levels", showlegend=False)
    return fig_html(fig, 360)


def load_massive_option_summaries(run_dir: Path, spot: float, as_of: str) -> tuple[list[dict], list[dict]]:
    rows: list[dict] = []
    histories: list[dict] = []
    try:
        base = date.fromisoformat(as_of[:10])
    except Exception:
        base = date.today()
    for path in sorted(run_dir.glob("options_massive_*.json")):
        packet = load_json(path)
        options = packet.get("options", []) if isinstance(packet, dict) else []
        expiry = next((str(x.get("expiry")) for x in options if x.get("expiry")), None)
        call = next((x for x in options if x.get("type") == "call"), None)
        put = next((x for x in options if x.get("type") == "put"), None)
        if not expiry or not call or not put:
            continue
        cp = call.get("last", call.get("close"))
        pp = put.get("last", put.get("close"))
        try:
            cp, pp = float(cp), float(pp)
        except Exception:
            continue
        try:
            days = max((date.fromisoformat(expiry[:10]) - base).days, 1)
        except Exception:
            continue
        years = days / 365.0
        straddle = cp + pp
        rows.append({
            "expiry": expiry[:10], "days": days, "strike": call.get("strike"), "call": cp, "put": pp,
            "straddle": straddle, "expected_move_pct": straddle / spot * 100,
            "iv_pct": straddle / spot * math.sqrt(math.pi / (2 * years)) * 100,
        })
        hmap: dict[Any, dict[str, Any]] = {}
        for typ, obj in (("call", call), ("put", put)):
            for bar in obj.get("history", []) or []:
                hmap.setdefault(bar.get("t"), {})[typ] = bar.get("c")
        for stamp, values in hmap.items():
            if values.get("call") is not None and values.get("put") is not None:
                histories.append({"expiry": expiry[:10], "date": ts_to_date(stamp), "straddle": float(values["call"]) + float(values["put"])})
    return rows, histories


def options_proxy_chart(rows: list[dict]) -> str:
    if not rows:
        return ""
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=[r["expiry"] for r in rows], y=[r["expected_move_pct"] for r in rows], name="Straddle / spot", text=[f"{r['expected_move_pct']:.1f}%" for r in rows], textposition="outside"), secondary_y=False)
    fig.add_trace(go.Scatter(x=[r["expiry"] for r in rows], y=[r["iv_pct"] for r in rows], name="Approx IV", mode="lines+markers"), secondary_y=True)
    fig.update_yaxes(title_text="Expected move proxy (%)", secondary_y=False)
    fig.update_yaxes(title_text="Approx IV (%)", secondary_y=True)
    fig.update_layout(title="Bounded ATM straddle / variance proxy")
    return fig_html(fig, 360)


def option_history_chart(rows: list[dict]) -> str:
    if not rows:
        return ""
    fig = go.Figure()
    for expiry in sorted({x["expiry"] for x in rows}):
        subset = sorted([x for x in rows if x["expiry"] == expiry], key=lambda x: x["date"])
        fig.add_trace(go.Scatter(x=[x["date"] for x in subset], y=[x["straddle"] for x in subset], mode="lines+markers", name=expiry))
    fig.update_layout(title="ATM straddle premium history", yaxis_title="Call close + put close")
    return fig_html(fig, 360)


def gamma_coverage(yfinance: dict, gamma: dict) -> dict[str, Any]:
    options = yfinance.get("options", []) if isinstance(yfinance, dict) else []
    oi_observed = oi_positive = valid_quotes = 0
    for row in options:
        if not isinstance(row, dict):
            continue
        oi = row.get("open_interest")
        if oi is not None:
            oi_observed += 1
            try:
                if float(oi) > 0:
                    oi_positive += 1
            except Exception:
                pass
        try:
            if float(row.get("bid")) > 0 and float(row.get("ask")) > 0:
                valid_quotes += 1
        except Exception:
            pass
    rows = gamma.get("strike_structure", []) if isinstance(gamma, dict) else []
    positive_gamma = [x for x in rows if (x.get("total_gross_gamma_notional_per_1pct_spot") or 0) > 0]
    return {
        "chain_rows": len(options), "oi_observed": oi_observed, "oi_positive": oi_positive,
        "valid_quotes": valid_quotes, "positive_gamma_rows": len(positive_gamma),
        "usable": bool(positive_gamma and oi_positive > 0),
    }


def gamma_chart(gamma: dict, coverage: dict[str, Any]) -> str | None:
    if not coverage.get("usable"):
        return None
    rows = [x for x in gamma.get("strike_structure", []) if (x.get("total_gross_gamma_notional_per_1pct_spot") or 0) > 0]
    rows = sorted(rows, key=lambda x: abs(x.get("distance_pct", 999)))[:40]
    rows.sort(key=lambda x: x.get("strike", 0))
    fig = go.Figure(go.Bar(x=[x.get("strike") for x in rows], y=[x.get("total_gross_gamma_notional_per_1pct_spot") for x in rows]))
    fig.update_layout(title="Observed gross gamma by strike (unsigned, OI-weighted)", xaxis_title="Strike", yaxis_title="$ notional per 1% spot move")
    return fig_html(fig, 360)


def quality_cards(coverage: dict[str, Any]) -> str:
    status = "LIMITED" if coverage.get("usable") else "UNAVAILABLE"
    return f'''<div class="cards">
<div class="metric"><div class="k">Full-chain rows</div><div class="v">{coverage['chain_rows']:,}</div><div class="s">raw option rows</div></div>
<div class="metric"><div class="k">OI observed rows</div><div class="v">{coverage['oi_observed']:,}</div><div class="s">missing is not zero</div></div>
<div class="metric"><div class="k">Positive OI rows</div><div class="v">{coverage['oi_positive']:,}</div><div class="s">required for wall ranking</div></div>
<div class="metric"><div class="k">Gamma structure</div><div class="v">{status}</div><div class="s">unsigned; dealer sign not inferred</div></div>
</div>'''


def extract_scenarios(text: str) -> list[dict]:
    section = parse_h2_sections(text).get("Scenarios", "")
    out = []
    for line in section.splitlines():
        if not line.startswith("|") or line.startswith("|---") or "Case" in line:
            continue
        parts = [x.strip() for x in line.strip("|").split("|")]
        if len(parts) < 2:
            continue
        try:
            probability = float(parts[1].replace("%", ""))
        except Exception:
            continue
        out.append({"case": parts[0], "probability": probability})
    return out


def scenario_chart(rows: list[dict]) -> str:
    if not rows:
        return ""
    fig = go.Figure(go.Bar(y=[r["case"] for r in rows], x=[r["probability"] for r in rows], orientation="h", text=[f"{r['probability']:.0f}%" for r in rows], textposition="outside"))
    fig.update_layout(title="Scenario probability assumptions", xaxis_title="%")
    return fig_html(fig, 330)


def extract_risk_levels(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for key in ("Entry", "Stop", "Target"):
        m = re.search(rf"\|\s*{key}\s*\|\s*([\d,.]+)\s*\|", text, re.I)
        if m:
            out[key.lower()] = float(m.group(1).replace(",", ""))
    return out


def risk_chart(levels: dict[str, float]) -> str:
    keys = [k for k in ("stop", "entry", "target") if k in levels]
    if not keys:
        return ""
    fig = go.Figure(go.Bar(y=[k.title() for k in keys], x=[levels[k] for k in keys], orientation="h", text=[f"{levels[k]:,.2f}" for k in keys], textposition="outside"))
    fig.update_layout(title="Risk level ladder", showlegend=False)
    return fig_html(fig, 300)


def has_intraday_evidence(run_dir: Path) -> bool:
    names = [p.name.lower() for p in run_dir.glob("*.json")]
    return any(any(token in name for token in ("intraday", "1min", "1_min", "10sec", "10_sec", "opening", "vwap")) for name in names)


def governance_presence(run_dir: Path) -> dict[str, bool]:
    aliases = {
        "evidence": ["evidence.json", "evidence_packet.json", "evidence_manifest.json"],
        "claims": ["claims.json", "claim_graph.json"],
        "bull": ["bull_review.json"], "bear": ["bear_review.json"], "skeptic": ["skeptic_review.json"],
        "arbitration": ["arbitration.json"],
    }
    return {key: any((run_dir / name).exists() for name in names) for key, names in aliases.items()}


def narrative_for(module: str, sections: dict[str, str]) -> str:
    chunks = [sections[h] for h in MODULE_HEADINGS[module] if h in sections]
    return MD("\n\n".join(chunks)) if chunks else '<p class="small">No narrative section in source Markdown.</p>'


def audit_callout(audit: dict, symbol: str) -> str:
    if not audit:
        return ""
    item = audit.get("ticker_scores", {}).get(symbol) or audit.get("tickers", {}).get(symbol)
    if not isinstance(item, dict):
        return ""
    findings = item.get("findings") or []
    severity = "bad" if str(item.get("status", "")).startswith("critical") else ""
    lis = "".join(f"<li>{html.escape(str(x))}</li>" for x in findings)
    score = item.get("score", "—")
    return f'<div class="callout {severity}"><b>Audit: {html.escape(str(score))}/10 · {html.escape(str(item.get("status", "")))}</b><ul>{lis}</ul></div>'


def page(title: str, symbol: str, as_of: str, state: str, nav: str, body: str, spot: Any) -> str:
    state_class = "warn" if state in CANONICAL_STATES else "bad"
    spot_text = "—" if spot is None else f"{float(spot):,.2f}"
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><style>{CSS}</style><script>{PLOTLY_JS}</script></head><body><div class="wrap">
<header class="hero"><div><div class="eyebrow">Evidence-backed stock research · HTML</div><h1>{html.escape(title)}</h1><div class="subtitle">Standalone interactive rendering of local run artifacts. Visualization does not upgrade evidence strength.</div><div style="margin-top:10px"><span class="badge">{html.escape(symbol)}</span><span class="badge">as-of {html.escape(as_of)}</span><span class="badge {state_class}">{html.escape(state)}</span></div></div><div class="metric"><div class="k">Reference price</div><div class="v">{spot_text}</div><div class="s">from deterministic/market artifact</div></div></header>
<nav class="nav">{nav}</nav>{body}<div class="footer">Generated by stock-eval-system modular HTML renderer · local artifacts only</div></div></body></html>'''


def render(symbol: str, report: Path, run_dir: Path, output: Path, modules: list[str], as_of_override: str | None, audit_path: Path | None) -> None:
    text = report.read_text(encoding="utf-8")
    sections = parse_h2_sections(text)
    stock_eval = pick_json(run_dir, ["stock_eval.json", "golden_output.json"], ["*stock_eval*.json"])
    market = pick_json(run_dir, ["market_massive_daily.json", "market.json", "daily.json"], ["market*daily*.json", "*daily*bars*.json"])
    gamma = pick_json(run_dir, ["options_gamma_structure.json"], ["*gamma*structure*.json"])
    yfinance = pick_json(run_dir, ["options_yfinance_full.json"], ["*yfinance*option*.json"])
    audit = load_json(audit_path) if audit_path else {}
    tech = stock_eval.get("technical", {}) if isinstance(stock_eval, dict) else {}
    market_bars = normalize_market_bars(market)
    spot = tech.get("last_price") or (market_bars[-1]["c"] if market_bars else None)
    as_of = infer_as_of(text, stock_eval, as_of_override)
    state = extract_research_state(text)
    option_rows, option_hist = load_massive_option_summaries(run_dir, float(spot or 1.0), as_of)
    coverage = gamma_coverage(yfinance, gamma)
    governance = governance_presence(run_dir)
    intraday = has_intraday_evidence(run_dir)
    nav = "".join(f'<a href="#{m}">{m.title()}</a>' for m in modules)
    blocks = [audit_callout(audit, symbol)]

    for module in modules:
        charts = ""
        if module == "overview":
            cards = [
                ("20D return", None if tech.get("return_20d") is None else f"{tech['return_20d']*100:+.1f}%"),
                ("90D return", None if tech.get("return_90d") is None else f"{tech['return_90d']*100:+.1f}%"),
                ("RSI14", tech.get("momentum", {}).get("rsi14")),
                ("RV20 ann.", None if tech.get("realized_vol_20d_annualized") is None else f"{tech['realized_vol_20d_annualized']*100:.1f}%"),
            ]
            charts = '<div class="cards">' + "".join(f'<div class="metric"><div class="k">{k}</div><div class="v">{html.escape(str(v if v is not None else "—"))}</div></div>' for k, v in cards) + "</div>"
        elif module == "technical":
            main = market_chart(market)
            state_chart = technical_state_chart(tech) if tech else ""
            support = support_chart(tech) if tech else ""
            charts = (f'<div class="chart">{main}</div>' if main else '<div class="callout bad">No structured daily market bars available.</div>')
            if state_chart or support:
                charts += f'<div class="grid2" style="margin-top:16px"><div class="chart">{state_chart}</div><div class="chart">{support}</div></div>'
            charts += '<div class="callout">Interpret trend by horizon when short/medium/long signals conflict; one MA label must not erase the conflict.</div>'
        elif module == "options":
            charts = quality_cards(coverage)
            proxy = options_proxy_chart(option_rows)
            hist = option_history_chart(option_hist)
            if proxy or hist:
                charts += f'<div class="grid2"><div class="chart">{proxy}</div><div class="chart">{hist}</div></div>'
            gchart = gamma_chart(gamma, coverage)
            if gchart:
                charts += f'<div class="chart" style="margin-top:16px">{gchart}</div><div class="callout">Unsigned OI-weighted gross Gamma is not dealer GEX.</div>'
            else:
                charts += '<div class="callout bad"><b>Gamma plot suppressed:</b> positive/trustworthy OI-Gamma structure is not available. No all-zero strike is promoted to a wall.</div>'
            if option_rows:
                charts += '<div class="callout">Historical bounded call/put pairs are shown as an ATM straddle/variance proxy; do not call this a full volatility surface unless surface coverage exists.</div>'
        elif module == "risk":
            rchart = risk_chart(extract_risk_levels(text))
            if rchart:
                charts += f'<div class="chart">{rchart}</div>'
            if not intraday:
                charts += '<div class="callout"><b>Intraday evidence gate:</b> no explicit same-session intraday/VWAP/opening-range artifact was detected. Treat timing text as next-session/daily-structure planning, not validated today timing.</div>'
        elif module == "scenarios":
            schart = scenario_chart(extract_scenarios(text))
            charts = f'<div class="chart">{schart}</div>' if schart else ""
        elif module == "governance":
            missing = [k for k, present in governance.items() if not present]
            charts = '<div class="callout good">Machine-readable governance artifacts detected for this run.</div>' if not missing else f'<div class="callout"><b>Replay gap:</b> missing governance artifacts: {html.escape(", ".join(missing))}. Narrative review cannot be fully cross-validated locally.</div>'
        elif module == "valuation":
            if not list(run_dir.glob("*valuation*.json")):
                charts = '<div class="callout"><b>Traceability gate:</b> no timestamped valuation snapshot artifact detected. Narrative valuation values are not treated as locally replayable inputs.</div>'
        elif module == "fundamentals":
            primary_files = list(run_dir.glob("*sec*.json")) + list(run_dir.glob("*ir*.json")) + list(run_dir.glob("*fundamental*.json"))
            if not primary_files:
                charts = '<div class="callout"><b>Replay gate:</b> no bundled SEC/IR/fundamental source packet detected. URLs in prose are not a substitute for the frozen primary evidence packet.</div>'
        elif module == "evidence":
            charts = '<div class="callout"><b>Bundle rule:</b> full research should carry source packets, valuation/options artifacts, Evidence Packet, Claim Graph, reviews, arbitration, and decision record needed to reproduce material conclusions.</div>'

        narrative = narrative_for(module, sections)
        blocks.append(f'<section id="{module}"><h2>{module.title()}</h2><div class="deck">Structured artifact visualization + source narrative.</div>{charts}<div class="narrative">{narrative}</div></section>')

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page(extract_title(text), symbol, as_of, state, nav, "\n".join(blocks), spot), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Render modular standalone StockEval HTML")
    ap.add_argument("--report", required=True, help="reader-facing Markdown report")
    ap.add_argument("--run-dir", required=True, help="directory containing structured run artifacts")
    ap.add_argument("--output", required=True)
    ap.add_argument("--modules", default=",".join(DEFAULT_MODULES), help="comma-separated: " + ",".join(DEFAULT_MODULES))
    ap.add_argument("--symbol", help="defaults from report filename")
    ap.add_argument("--as-of", help="optional YYYY-MM-DD override")
    ap.add_argument("--audit-json", help="optional per-run/per-ticker audit JSON; presentation only")
    args = ap.parse_args()
    report = Path(args.report)
    run_dir = Path(args.run_dir)
    symbol = (args.symbol or report.name.split("_")[0]).upper()
    modules = [x.strip() for x in args.modules.split(",") if x.strip()]
    unknown = [x for x in modules if x not in MODULE_HEADINGS]
    if unknown:
        raise SystemExit("Unknown module(s): " + ",".join(unknown))
    render(symbol, report, run_dir, Path(args.output), modules, args.as_of, Path(args.audit_json) if args.audit_json else None)
    print(Path(args.output).resolve())


if __name__ == "__main__":
    main()
