import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skill" / "scripts" / "fetch_ibkr_intraday.py"
SPEC = importlib.util.spec_from_file_location("fetch_ibkr_intraday", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MOD)


class IntradayCursorTests(unittest.TestCase):
    def test_future_cursor_is_moved_to_prior_weekday_close(self):
        effective, audit = MOD.normalize_end_cursor("20990101 16:00:00 US/Eastern")
        self.assertTrue(audit["adjusted"])
        self.assertIn("US/Eastern", effective)
        self.assertNotEqual(effective, "20990101 16:00:00 US/Eastern")


if __name__ == "__main__":
    unittest.main()
