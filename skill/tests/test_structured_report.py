import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


VALIDATOR = load_module("validate_structured_report", SCRIPTS / "validate_structured_report.py")
BUILDER = load_module("build_structured_report", SCRIPTS / "build_structured_report.py")


class StructuredReportTests(unittest.TestCase):
    def test_chart_explanation_is_a_structural_invariant(self):
        report = {
            "schema_version": "2.0",
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
                        "interpretation": {"what": "x", "read": "y", "why": "z", "limit": "q"},
                    }],
                }
            },
        }
        self.assertEqual(VALIDATOR.validate(report), [])
        del report["modules"]["technical"]["charts"][0]["interpretation"]["limit"]
        self.assertTrue(any("interpretation.limit" in error for error in VALIDATOR.validate(report)))

    def test_default_charts_always_explain_what_read_why_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = pathlib.Path(tmp)
            (run / "market_ibkr_daily_full.json").write_text("{\"bars\": []}\n", encoding="utf-8")
            stock = {"technical": {"last_price": 100.0}}
            charts = BUILDER.default_charts("technical", run, stock, {}, {})
            self.assertGreaterEqual(len(charts), 3)
            for chart in charts:
                self.assertEqual(set(["what", "read", "why", "limit"]) - set(chart["interpretation"]), set())
                self.assertTrue(all(str(chart["interpretation"][key]).strip() for key in ["what", "read", "why", "limit"]))


if __name__ == "__main__":
    unittest.main()
