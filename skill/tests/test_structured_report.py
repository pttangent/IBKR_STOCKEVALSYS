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
                        "id": "state", "kind": "technical_snapshot", "title": "STATE",
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
            self.assertIn("1 萬美元", interpretation["what"])
            self.assertIn("四分之一 Kelly", interpretation["read_result"])

    def _technical(self):
        return {
            "last_price": 100.0,
            "ma": {"ema20": 99.2, "sma50": 109.8, "sma200": 80.0},
            "momentum": {"atr14": 6.0, "bollinger": {"upper": 111.0, "lower": 89.0}},
            "realized_vol_20d_annualized": 0.80,
            "support_resistance": {"supports": [95.0, 90.0], "resistances": [105.0, 110.0]},
            "close_weighted_volume_nodes": [{"mid": 96.0, "volume": 1000}, {"mid": 104.0, "volume": 900}],
        }

    def test_scenario_tree_is_compositional_not_gap_template(self):
        trees = build_scenario_trees(self._technical(), {"prior_close": 99.0}, {})
        self.assertEqual([tree["horizon"] for tree in trees], ["intraday", "short_term", "long_term"])
        intraday = trees[0]
        self.assertEqual(intraday["evidence_status"], "next_session_conditional")
        self.assertEqual(intraday["construction_policy"], "compositional_event_tree")
        root_ids = [child["id"] for child in intraday["root"]["children"]]
        self.assertEqual(root_ids, ["upward_impulse", "compression", "downward_impulse"])
        self.assertNotIn("gap_up", root_ids)
        self.assertNotIn("PRIOR_CLOSE", {a["id"] for a in intraday["anchor_book"]})

    def test_intraday_tree_contains_break_retest_hold_and_false_break_paths(self):
        intraday = build_scenario_trees(self._technical(), {}, {})[0]
        upward = intraday["root"]["children"][0]
        breakout = upward["children"][0]
        ids = [child["id"] for child in breakout["children"]]
        self.assertEqual(ids, ["up_break_retest_hold", "up_break_retest_fail"])
        hold = breakout["children"][0]
        self.assertIn("回踩不破", hold["label"])
        self.assertEqual(hold["sizing_tier"], "quarter")
        self.assertTrue(hold["price_anchors"])
        self.assertTrue(all(item.get("source") and item.get("method") for item in hold["price_anchors"]))
        structural = next(item for item in hold["price_anchors"] if item["confidence_interval"])
        self.assertEqual(structural["confidence_interval"]["kind"], "structural_tolerance")
        self.assertLess(structural["confidence_interval"]["lower"], structural["value"])
        self.assertGreater(structural["confidence_interval"]["upper"], structural["value"])

    def test_same_session_tree_uses_real_intraday_anchors_when_present(self):
        intraday_context = {
            "same_session": True,
            "source_artifact": "intraday_1m.json",
            "current_price": 101.2,
            "orh": 102.4,
            "orl": 98.8,
            "vwap": 100.6,
        }
        tree = build_scenario_trees(self._technical(), {}, intraday_context)[0]
        anchors = {item["id"]: item for item in tree["anchor_book"]}
        self.assertEqual(tree["evidence_status"], "same_session")
        self.assertAlmostEqual(anchors["VWAP"]["value"], 100.6)
        self.assertEqual(anchors["VWAP"]["role"], "intraday")
        self.assertIn("intraday_1m.json", anchors["VWAP"]["source"])
        self.assertAlmostEqual(anchors["ORH"]["value"], 102.4)
        self.assertAlmostEqual(anchors["ORL"]["value"], 98.8)
        self.assertEqual(anchors["ORH"]["confidence_interval"]["basis"], "stock_eval.json:technical.momentum.atr14")

    def test_anchor_book_always_contains_current_price_reference(self):
        tree = build_scenario_trees(self._technical(), {}, {})[0]
        current = next(item for item in tree["anchor_book"] if item["role"] == "current")
        self.assertAlmostEqual(current["value"], 100.0)
        self.assertEqual(current["source"], "stock_eval.json:technical.last_price")

    def test_validator_rejects_scenario_anchor_without_provenance(self):
        tree = build_scenario_trees(self._technical(), {}, {})[0]
        bad = tree["root"]["price_anchors"][0]
        bad.pop("source")
        report = {
            "schema_version": "2.1", "run_id": "TEST", "symbol": "TEST", "as_of": "2026-08-12",
            "research_state": "READY_CONDITIONAL",
            "modules": {
                "scenarios": {
                    "title": "SCENARIOS", "status": "complete", "freshness_status": "current",
                    "source_artifacts": ["stock_eval.json"], "missing_fields": [], "scenario_trees": [tree],
                }
            },
        }
        errors = VALIDATOR.validate(report)
        self.assertTrue(any("price_anchors" in error and "source" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
