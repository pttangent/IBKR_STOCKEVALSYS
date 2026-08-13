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


FINALIZER = load_module("finalize_structured_report", SCRIPTS / "finalize_structured_report.py")
VALIDATOR = load_module("validate_structured_report_final", SCRIPTS / "validate_structured_report.py")


class ReportFinalizationTests(unittest.TestCase):
    def _technical(self):
        return {
            "as_of": "2026-08-11",
            "last_price": 100.0,
            "ma": {"ema20": 96.0, "sma50": 92.0, "sma200": 70.0},
            "momentum": {"atr14": 5.0, "bollinger": {"upper": 106.0, "lower": 84.0}},
            "realized_vol_20d_annualized": 1.2,
            "support_resistance": {"supports": [95.0, 90.0], "resistances": [105.0, 110.0]},
            "close_weighted_volume_nodes": [],
        }

    def _kelly(self):
        return {
            "full_sample": {"status": "ok", "trades": 1, "kelly_fraction": 1.0, "at_grid_cap": True},
            "full_sample_formula": {"trades": 1, "p_win_rate": 1.0, "raw_formula_kelly_fraction": None},
            "out_of_sample": {"status": "insufficient_oos", "trades": 0},
            "sample_confidence": {"label": "very_low", "tier": "exploratory"},
            "setup_match": {"status": "unknown"},
            "selected_edge": {"status": "ok", "fraction": 1.0, "source": "full_sample_empirical_log_growth"},
            "guidance_status": "exploratory",
            "guidance_variant": "quarter",
            "guidance_kelly_scenarios": {
                "full": {"post_overlay_fraction": 0.60},
                "half": {"post_overlay_fraction": 0.30},
                "quarter": {"post_overlay_fraction": 0.15},
            },
            "risk_overlay_combination": {"combined_haircut": 0.60},
        }

    def _module(self, title):
        return {"title": title, "status": "complete", "freshness_status": "current", "source_artifacts": [], "missing_fields": [], "evidence_resolution": [], "metrics": {}, "blocks": [], "judgments": [], "knowledge_notes": [], "charts": [], "scenario_trees": [], "limitations": []}

    def test_finalize_repairs_aehr_class_contradictions(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = pathlib.Path(tmp)
            stock = {
                "technical": self._technical(),
                "kelly": self._kelly(),
                "position": {},
            }
            (run / "stock_eval.json").write_text(json.dumps(stock), encoding="utf-8")
            (run / "report_manifest.json").write_text(json.dumps({"run_id": "TEST_2026-08-12", "as_of": "2026-08-12"}), encoding="utf-8")
            (run / "options_gamma_structure.json").write_text(json.dumps({"data_quality": {"rows_with_positive_open_interest": 12}}), encoding="utf-8")
            (run / "intraday_1m_30d.json").write_text(json.dumps({"bars": [{"date": "2026-08-11T15:59:00-04:00", "open": 101, "high": 102, "low": 100, "close": 101.5, "volume": 1000}]}), encoding="utf-8")
            (run / "research_content.json").write_text(json.dumps({"modules": {"scenarios": {"long_term_context": {
                "watch": ["收入與現金流", "現價與支撐"],
                "strengthen_trigger": "收入與現金流同步改善，且價格能守住 $95。",
                "mixed_trigger": "收入改善但現金流未改善；價格在支撐與阻力間反覆。",
                "weaken_trigger": "現金流惡化，或價格跌破支撐。",
            }}}}, ensure_ascii=False), encoding="utf-8")

            modules = {name: self._module(name) for name in ("technical", "options", "risk", "scenarios")}
            modules["technical"]["module_as_of"] = "2026-08-12"
            modules["options"]["missing_fields"] = ["positive_open_interest", "dealer_sign"]
            modules["options"]["evidence_resolution"] = [
                {"field": "positive_open_interest", "status": "NOT_AVAILABLE_AT_CUTOFF", "attempts": []},
                {"field": "dealer_sign", "status": "NOT_AVAILABLE_AT_CUTOFF", "attempts": []},
            ]
            modules["options"]["metrics"] = {"gamma": {"data_quality": {"rows_with_positive_open_interest": 12}}}
            modules["risk"]["metrics"] = {
                "kelly": self._kelly(),
                "position": {},
                "position_guidance": {
                    "portfolio_value": 10000.0, "portfolio_value_source": "user_provided", "simulation_label": "USER PORTFOLIO",
                    "current_realized_vol_20d_annualized": 1.2, "daily_sigma": 0.075,
                    "risk_budget_pct": 0.005, "concentration_cap_pct": 0.05,
                    "guidance_variant": "quarter", "guidance_status": "exploratory", "guidance_fraction": 0.05,
                    "guidance_notional_dollars": 500.0,
                    "variants": {
                        "full": {"final_fraction": 0.05, "notional_dollars": 500},
                        "half": {"final_fraction": 0.05, "notional_dollars": 500},
                        "quarter": {"final_fraction": 0.05, "notional_dollars": 500},
                    },
                },
            }
            report = {
                "schema_version": "2.1", "run_id": "TEST_2026-08-12", "symbol": "TEST", "as_of": "2026-08-12",
                "generated_at": "2026-08-12T14:16:00+00:00",
                "evidence_cutoff": "2026-08-12T23:59:59+08:00",
                "price_timestamp": "2026-08-12T16:00:00-04:00",
                "research_state": "READY_CONDITIONAL", "global_limitations": [], "modules": modules,
                "package_hints": {"default_simulation_portfolio_value": 10000.0},
            }

            final = FINALIZER.finalize(report, run)
            self.assertLessEqual(FINALIZER._parse_time(final["evidence_cutoff"]), FINALIZER._parse_time(final["generated_at"]))
            self.assertLessEqual(FINALIZER._parse_time(final["price_timestamp"]), FINALIZER._parse_time(final["generated_at"]))
            self.assertEqual(final["modules"]["technical"]["module_as_of"], "2026-08-11")
            self.assertEqual(final["modules"]["technical"]["freshness_status"], "previous_completed_session")
            self.assertNotIn("positive_open_interest", final["modules"]["options"]["missing_fields"])
            self.assertEqual(final["modules"]["risk"]["metrics"]["position_guidance"]["guidance_status"], "severe_data_gap")
            self.assertEqual(final["modules"]["risk"]["metrics"]["position_guidance"]["variants"], {})

            intraday = final["modules"]["scenarios"]["scenario_trees"][0]
            current = next(item for item in intraday["anchor_book"] if item["id"] == "CURRENT")
            self.assertAlmostEqual(current["value"], 100.0)
            self.assertEqual(current["source"], "stock_eval.json:technical.last_price")
            self.assertEqual(intraday["evidence_status"], "next_session_conditional")

            long_tree = final["modules"]["scenarios"]["scenario_trees"][2]
            long_inputs = " ".join(child["trigger"] for child in long_tree["root"]["children"])
            for token in ("支撐", "阻力", "跌破", "$95"):
                self.assertNotIn(token, long_inputs)
            self.assertEqual(VALIDATOR.validate(final), [])

    def test_validator_rejects_future_timestamp_and_tiny_sample_variants(self):
        risk = self._module("risk")
        risk["metrics"] = {
            "kelly": self._kelly(),
            "position_guidance": {
                "portfolio_value": 10000.0,
                "portfolio_value_source": "default_10000_simulation",
                "variants": {
                    "full": {"final_fraction": 0.05, "notional_dollars": 500},
                    "half": {"final_fraction": 0.04, "notional_dollars": 400},
                    "quarter": {"final_fraction": 0.03, "notional_dollars": 300},
                },
            },
        }
        report = {
            "schema_version": "2.1", "run_id": "TEST", "symbol": "TEST", "as_of": "2026-08-12",
            "generated_at": "2026-08-12T14:00:00+00:00", "evidence_cutoff": "2026-08-12T15:00:00+00:00",
            "research_state": "READY_CONDITIONAL", "modules": {"risk": risk},
        }
        errors = VALIDATOR.validate(report)
        self.assertTrue(any("evidence_cutoff" in error for error in errors))
        self.assertTrue(any("fewer than 10" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
