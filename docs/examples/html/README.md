# Versioned HTML report examples

These files are compact, version-controlled examples of the stock-evaluation HTML output contract. They are intentionally kept small enough for normal Git history.

## Examples

- [`GEV_full_example.html`](GEV_full_example.html) — representative full report: fundamentals, technical state, options, scenario/risk and evidence-quality warnings.
- [`XE_technical_example.html`](XE_technical_example.html) — technical-only module output.
- [`XE_options_example.html`](XE_options_example.html) — options-only module output, including the required Gamma suppression behavior when economically meaningful OI/Gamma is unavailable.
- [`INDEX.html`](INDEX.html) — browser-oriented entry page.
- [`example_manifest.json`](example_manifest.json) — machine-readable inventory of the demonstration cases.

## Important distinction

The canonical renderer is [`skill/scripts/render_html_report.py`](../../../skill/scripts/render_html_report.py). Normal generated reports embed Plotly and are standalone/offline HTML files. These repository examples load Plotly from the public CDN so that several examples do not add roughly 15 MB of duplicated Plotly JavaScript to Git history.

The examples are frozen from the 2026-08-11 audited research bundle. They are demonstration artifacts, not live market views and not current investment conclusions. Do not reuse their ticker-specific prices, assumptions, scenario weights or conclusions in a new report.

`GEV_full_example.html` deliberately keeps weak Gamma/OI evidence visible: one economically non-zero OI row is not promoted to a reliable wall. `XE_options_example.html` demonstrates the stricter all-zero case, where Gamma-wall output is suppressed entirely.

## Quality behaviors demonstrated

1. `missing != 0`: missing OI/quote fields are not silently converted to economic zero.
2. Gamma concentration is unsigned unless dealer/customer position sign is independently inferred.
3. Zero or untrusted OI/Gamma must not create a fake Gamma Wall.
4. Kelly variants are labelled separately; exploratory/quarter Kelly is not presented as validated full Kelly.
5. A module-only request still produces a complete, readable HTML document.
6. Full research keeps evidence/data quality visible in the reader-facing report, not only in JSON audit artifacts.
7. Without current-session intraday evidence, technical output is labelled as next-session structure rather than false “today confirmed” timing.

## Regeneration

A normal full report:

```bash
python skill/scripts/render_html_report.py \
  --report runs/GEV/GEV_complete_report.md \
  --run-dir runs/GEV \
  --output runs/GEV/GEV_complete_report.html
```

A single module:

```bash
python skill/scripts/render_html_report.py \
  --report runs/XE/XE_complete_report.md \
  --run-dir runs/XE \
  --output runs/XE/XE_options.html \
  --modules options
```
