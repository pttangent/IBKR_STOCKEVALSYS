import importlib.util
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "skill" / "scripts"
SCRIPT = SCRIPT_DIR / "options_gamma_structure.py"
sys.path.insert(0, str(SCRIPT_DIR))
SPEC = importlib.util.spec_from_file_location("options_gamma_structure", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MOD)


class OptionsGammaStructureTests(unittest.TestCase):
    def test_missing_oi_stays_missing_and_sign_is_not_inferred(self):
        packet = {
            "provider": "yfinance",
            "retrieved_at": "2026-08-11T06:00:00+00:00",
            "symbol": "TEST",
            "spot": 100.0,
            "request": {"full_chain": True},
            "options": [
                {"type": "call", "expiry": "2026-08-21", "strike": 100, "iv": 0.40, "open_interest": 1000, "last": 3.0},
                {"type": "put", "expiry": "2026-08-21", "strike": 100, "iv": 0.42, "open_interest": 800, "last": 3.2},
                {"type": "call", "expiry": "2026-08-21", "strike": 105, "iv": 0.38, "open_interest": 5000, "last": 1.5},
                {"type": "put", "expiry": "2026-08-21", "strike": 95, "iv": 0.45, "open_interest": None, "last": 1.4},
            ],
        }
        result = MOD.summarize(packet, "2026-08-11")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["gamma_status"], "AVAILABLE_GROSS_ONLY")
        self.assertEqual(result["data_quality"]["oi_coverage_ratio"], 0.75)
        self.assertEqual(result["summary"]["largest_upper_gamma_concentration"]["strike"], 105.0)
        self.assertEqual(result["gamma_flip"]["status"], "UNAVAILABLE_WITHOUT_POSITION_SIGN")
        self.assertEqual(result["signed_gex_scenarios"]["status"], "ASSUMPTION_ONLY")

    def test_all_zero_oi_does_not_create_fake_gamma_wall(self):
        packet = {
            "provider": "yfinance",
            "retrieved_at": "2026-08-11T06:00:00+00:00",
            "symbol": "ZERO",
            "spot": 100.0,
            "request": {"full_chain": True},
            "options": [
                {"type": "call", "expiry": "2026-08-21", "strike": 95, "iv": 0.40, "open_interest": 0, "last": 6.0},
                {"type": "put", "expiry": "2026-08-21", "strike": 95, "iv": 0.42, "open_interest": 0, "last": 1.0},
                {"type": "call", "expiry": "2026-08-21", "strike": 105, "iv": 0.38, "open_interest": 0, "last": 1.5},
                {"type": "put", "expiry": "2026-08-21", "strike": 105, "iv": 0.45, "open_interest": 0, "last": 6.2},
            ],
        }
        result = MOD.summarize(packet, "2026-08-11")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["gamma_status"], "UNAVAILABLE_ZERO_OR_UNTRUSTED_OI")
        self.assertEqual(result["data_quality"]["rows_with_positive_open_interest"], 0)
        self.assertEqual(result["data_quality"]["positive_gamma_strikes"], 0)
        self.assertIsNone(result["summary"]["largest_upper_gamma_concentration"])
        self.assertIsNone(result["summary"]["largest_lower_gamma_concentration"])
        self.assertEqual(result["summary"]["top_gamma_concentrations"], [])
        self.assertIsNone(result["signed_gex_scenarios"])


if __name__ == "__main__":
    unittest.main()
