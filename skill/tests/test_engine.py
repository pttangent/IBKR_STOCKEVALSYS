from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from stock_eval_engine import evaluate, implied_vol, kelly_analysis, load_json, normalize_bars, pnl_ladder, position_size


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.bars = load_json(ROOT / "tests/fixtures/bars_xe.json")
        self.front = load_json(ROOT / "tests/fixtures/options_front.json")
        self.back = load_json(ROOT / "tests/fixtures/options_back.json")

    def test_bars_and_engine(self):
        result = evaluate("XE", self.bars, self.front, self.back, as_of="2026-02-27", portfolio_value=100000, stop=105)
        self.assertEqual(result["symbol"], "XE")
        self.assertEqual(result["technical"]["observations"], 41)
        self.assertEqual(result["options"]["status"], "ok")
        self.assertEqual(result["options"]["activity_distribution_only"], True)
        self.assertEqual(result["position"]["status"], "sized")
        self.assertIn(result["technical"]["ma_alignment"]["direction"], {"bullish", "bearish", "mixed", "compressed/neutral"})

    def test_iv_is_numerically_inverted(self):
        self.assertGreater(implied_vol(4.0, 109.8, 110, 30 / 365, "call"), 0.01)
        self.assertIsNone(implied_vol(0.10, 100, 90, 30 / 365, "call"))

    def test_kelly_is_qualified_only_with_reserved_oos_trades(self):
        returns = [{"return": 0.02 if i % 2 == 0 else -0.01} for i in range(70)]
        result = kelly_analysis({"trade_log": returns})
        self.assertEqual(result["status"], "qualified")
        self.assertGreater(result["raw_oos_kelly_fraction"], 0)
        self.assertTrue(result["applied_to_position"])

    def test_kelly_reports_exact_data_gap(self):
        result = kelly_analysis({"trade_log": [{"return": 0.01}, {"return": -0.01}]})
        self.assertEqual(result["status"], "conditional_insufficient_data")
        self.assertFalse(result["applied_to_position"])
        self.assertIn("60 total trades", result["out_of_sample"]["reason"])

    def test_kelly_always_exposes_diagnostic_ratio_when_not_validated(self):
        returns = [{"return": 0.04 if i % 2 == 0 else -0.02} for i in range(20)]
        result = kelly_analysis({"trade_log": returns})
        self.assertEqual(result["sample_confidence"]["tier"], "conditional_tactical")
        self.assertIsNotNone(result["diagnostic_fractional_kelly_cap"])
        self.assertEqual(set(result["diagnostic_kelly_scenarios"]), {"full", "half", "quarter"})
        self.assertGreater(result["diagnostic_kelly_scenarios"]["full"]["fraction"],
                           result["diagnostic_kelly_scenarios"]["quarter"]["fraction"])
        self.assertFalse(result["applied_to_position"])

    def test_position_size_exposes_integer_half_share_and_pnl_ladder(self):
        result = position_size(10000, 100, 95, kelly_fraction=0.003,
                              targets=[110], stops=[95])
        self.assertEqual(result["status"], "sized")
        self.assertIn("integer_shares", result)
        self.assertIn("half_share_quantity", result)
        self.assertIn("exact_fractional_shares", result)
        self.assertIn("exact_fractional_notional", result)
        self.assertIn("pnl_ladder", result)
        self.assertEqual(result["integer_shares"], 0)
        self.assertEqual(result["half_share_quantity"], 0.0)
        self.assertEqual(len(result["pnl_ladder"]["rows"]), 2)
        self.assertAlmostEqual(result["exact_fractional_notional"], 30.0)

    def test_pnl_ladder_reports_signed_values_for_both_sizes(self):
        result = pnl_ladder(100, stops=[95], targets=[110], integer_shares=2, half_shares=1.5,
                            risk_budget_dollars=8)
        rows = {row["type"]: row for row in result["rows"]}
        self.assertEqual(rows["stop"]["integer_pnl"], -10)
        self.assertEqual(rows["stop"]["half_pnl"], -7.5)
        self.assertTrue(rows["stop"]["integer_risk_cap_exceeded"])
        self.assertFalse(rows["stop"]["half_risk_cap_exceeded"])
        self.assertEqual(rows["target"]["integer_pnl"], 20)
        self.assertEqual(rows["target"]["half_pnl"], 15)


if __name__ == "__main__":
    unittest.main()
