import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skill" / "stock_eval_core.py"
SPEC = importlib.util.spec_from_file_location("stock_eval_core", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MOD)


class StockEvalOptionMissingFieldTests(unittest.TestCase):
    def test_missing_oi_is_not_zero_and_ratio_requires_complete_coverage(self):
        packet = {
            "options": [
                {"type": "call", "expiry": "2026-08-21", "strike": 100, "bid": 2.9, "ask": 3.1, "volume": 120, "open_interest": 1000, "iv": 0.40},
                {"type": "put", "expiry": "2026-08-21", "strike": 100, "bid": 3.0, "ask": 3.2, "volume": 150, "open_interest": None, "iv": 0.42},
            ]
        }
        result = MOD.option_analysis(packet, 100.0, "2026-08-11")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["call_open_interest"], 1000.0)
        self.assertIsNone(result["put_open_interest"])
        self.assertEqual(result["put_open_interest_observed_sum"], None)
        self.assertEqual(result["put_open_interest_coverage"]["coverage_ratio"], 0.0)
        self.assertIsNone(result["put_call_oi_ratio"])
        self.assertAlmostEqual(result["put_call_volume_ratio"], 150 / 120)

    def test_atm_straddle_requires_both_option_prices(self):
        packet = {
            "options": [
                {"type": "call", "expiry": "2026-08-21", "strike": 100, "last": 3.0, "volume": 1, "open_interest": 1},
                {"type": "put", "expiry": "2026-08-21", "strike": 100, "last": None, "volume": 1, "open_interest": 1},
            ]
        }
        result = MOD.option_analysis(packet, 100.0, "2026-08-11")
        self.assertIsNone(result["atm_straddle_approximation_diagnostic"])


if __name__ == "__main__":
    unittest.main()
