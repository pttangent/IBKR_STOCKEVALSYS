from pathlib import Path
import tempfile
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research_memory import calibration_summary, connect, record_decision, record_outcome


class ResearchMemoryTests(unittest.TestCase):
    def test_decision_outcome_and_brier(self):
        with tempfile.TemporaryDirectory() as td:
            conn = connect(Path(td) / "memory.sqlite")
            decision = {
                "symbol": "NVDA",
                "as_of": "2026-08-07",
                "horizon": "20d",
                "evidence_freeze_hash": "a" * 64,
                "thesis_state": "READY_CONDITIONAL",
                "scenarios": {
                    "bear": {"probability": 0.2},
                    "base": {"probability": 0.4},
                    "bull": {"probability": 0.3},
                    "unknown": {"probability": 0.1},
                },
            }
            did = record_decision(conn, decision)
            record_outcome(conn, did, {
                "evaluated_at": "2026-09-04",
                "horizon_label": "T+20",
                "asset_return": 0.08,
                "benchmark_return": 0.02,
                "actual_scenario": "bull",
            })
            summary = calibration_summary(conn, "NVDA")
            self.assertEqual(summary["outcomes"], 1)
            self.assertEqual(summary["scenario_scored_outcomes"], 1)
            self.assertAlmostEqual(summary["mean_alpha"], 0.06)
            self.assertIsNotNone(summary["mean_multiclass_brier_score"])
            conn.close()


if __name__ == "__main__":
    unittest.main()
