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


SEMANTICS = load_module("finalize_research_semantics", SCRIPTS / "finalize_research_semantics.py")


class ResearchSemanticFinalizationTests(unittest.TestCase):
    def test_negative_net_income_does_not_use_ocf_over_net_income_as_cash_conversion(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = pathlib.Path(tmp)
            sec = {"data": {"canonical_financials": {"facts": {"net_income": {"value": -7126000}}}}}
            stock = {"technical": {"as_of": "2026-08-11"}}
            (run / "sec_research.json").write_text(json.dumps(sec), encoding="utf-8")
            (run / "stock_eval.json").write_text(json.dumps(stock), encoding="utf-8")
            (run / "valuation_snapshot.json").write_text(json.dumps({"status": "conditional_no_pit_consensus"}), encoding="utf-8")
            report = {
                "as_of": "2026-08-12", "global_limitations": [], "modules": {
                    "technical": {"blocks": [{"text": "2026-08-12 可用的最新完整收盤為 $117.18。"}]},
                    "fundamentals": {"blocks": [{"text": "營運現金流只有淨利的 0.46 倍；盈利到現金轉換偏弱。"}]},
                    "valuation": {
                        "status": "conditional", "confidence": "medium", "metrics": {"status": "conditional_no_pit_consensus"},
                        "blocks": [{"title": "估值判斷", "text": "基準情景：價格在支撐 $92.95 附近反覆。"}],
                        "judgments": [{"label": "估值判斷", "conclusion": "支撐 $92.95 是基準。", "why": "價格仍在阻力下方。"}],
                        "limitations": [],
                    },
                }
            }
            final = SEMANTICS.finalize_semantics(report, run)
            fundamental = final["modules"]["fundamentals"]["blocks"][0]["text"]
            self.assertNotIn("0.46 倍", fundamental)
            self.assertIn("不使用 OCF/淨利倍數", fundamental)
            valuation_text = final["modules"]["valuation"]["blocks"][0]["text"]
            self.assertNotIn("$92.95", valuation_text)
            self.assertIn("不輸出以技術支撐/阻力替代", valuation_text)
            self.assertEqual(final["modules"]["valuation"]["confidence"], "low")
            self.assertIn("2026-08-11 可用的最新完整收盤", final["modules"]["technical"]["blocks"][0]["text"])


if __name__ == "__main__":
    unittest.main()
