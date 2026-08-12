import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


VALIDATOR = load_module("validate_structured_report", SCRIPTS / "validate_structured_report.py")
BUILDER = load_module("build_structured_report", SCRIPTS / "build_structured_report.py")
from stock_eval_scenarios import build_scenario_trees


class StructuredReportTests(unittest.TestCase):
    def test_chart_explanation_is_a_structural_invariant(self):
        report = {
            "schema_version": "2.1",
            "run_id": "TEST_2026-08-12",
            "symbol": "TEST",
            "as_of": "2026-08-12",
            "research_state": "READY_CONDITIONAL",
            "modules": {
                "technical": {
                    "title": "TECHNICAL",
                    "status": "complete",
                    "freshness_status": "current",
                    "source_artifacts": ["stock_eval.json"],
                    "missing_fields": [],
                    "charts": [{
                        "id": "state",
                        "kind": "technical_snapshot",
                        "title": "STATE",
                        "interpretation": {"what": "x", "what_observed": "x1", "read": "y", "read_result": "y1", "why": "z", "why_now": "z1", "limit": "q", "limit_effect": "q1"},
                    }],
                }
            },
        }
        self.assertEqual(VALIDATOR.validate(report), [])
        del report["modules"]["technical"]["charts"][0]["interpretation"]["limit_effect"]
        self.assertTrue(any("interpretation.limit" in error for error in VALIDATOR.validate(report)))

    def test_default_charts_always_explain_what_read_why_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = pathlib.Path(tmp)
            (run / "market_ibkr_daily_full.json").write_text("{\"bars\": []}\n", encoding="utf-8")
            stock = {"technical": {"last_price": 100.0}}
            charts = BUILDER.default_charts("technical", run, stock, {}, {})
            self.assertGreaterEqual(len(charts), 3)
            for chart in charts:
                required = ["what", "what_observed", "read", "read_result", "why", "why_now", "limit", "limit_effect"]
                self.assertEqual(set(required) - set(chart["interpretation"]), set())
                self.assertTrue(all(str(chart["interpretation"][key]).strip() for key in required))

    def test_risk_module_gets_kelly_ladder_chart_when_variants_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = pathlib.Path(tmp)
            stock = {"technical": {"last_price": 100.0}}
            guidance = {
                "portfolio_value": 10000,
                "current_realized_vol_20d_annualized": 0.8,
                "daily_sigma": 0.8 / (252 ** 0.5),
                "guidance_variant": "quarter",
                "guidance_fraction": 0.03,
                "guidance_notional_dollars": 300,
                "guidance_binding_constraint": "kelly_after_risk_overlay",
                "guidance_status": "conditional",
                "variants": {
                    "full": {"final_fraction": 0.05, "notional_dollars": 500, "exact_fractional_shares": 5, "binding_constraint": "concentration_cap"},
                    "half": {"final_fraction": 0.05, "notional_dollars": 500, "exact_fractional_shares": 5, "binding_constraint": "concentration_cap"},
                    "quarter": {"final_fraction": 0.03, "notional_dollars": 300, "exact_fractional_shares": 3, "binding_constraint": "kelly_after_risk_overlay"},
                },
            }
            charts = BUILDER.default_charts("risk", run, stock, {}, {}, guidance)
            self.assertEqual([chart["kind"] for chart in charts], ["kelly_position_ladder"])
            interpretation = charts[0]["interpretation"]
            self.assertIn("$10k", interpretation["what"])
            self.assertIn("quarter", interpretation["read_result"])

    def test_scenario_tree_has_intraday_short_and_long_horizons(self):
        technical = {
            "last_price": 100.0,
            "ma": {"ema20": 102.0, "sma50": 98.0, "sma200": 80.0},
            "momentum": {"atr14": 6.0},
            "realized_vol_20d_annualized": 0.80,
            "support_resistance": {"supports": [95.0, 90.0], "resistances": [105.0, 110.0]},
        }
        trees = build_scenario_trees(technical, {"prior_close": 99.0}, {})
        self.assertEqual([tree["horizon"] for tree in trees], ["intraday", "short_term", "long_term"])
        intraday = trees[0]
        self.assertEqual(intraday["evidence_status"], "next_session_conditional")
        self.assertEqual([child["id"] for child in intraday["root"]["children"]], ["gap_up", "near_flat", "gap_down"])
        gap_up_children = [child["id"] for child in intraday["root"]["children"][0]["children"]]
        self.assertEqual(gap_up_children, ["gap_up_accept", "gap_up_fade"])
        self.assertEqual(intraday["root"]["children"][0]["children"][0]["sizing_tier"], "quarter")


if __name__ == "__main__":
    unittest.main()
