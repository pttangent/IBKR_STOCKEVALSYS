from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from research_governance import validate_arbitration, validate_claim_graph, validate_review
from research_memory import brier_score, freeze_decision, range_coverage, summarize


class ResearchGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.evidence_ids = {"SEC-1", "FRED-1", "IBKRNEWS-1"}
        self.graph = {
            "run_id": "NVDA-20260807-A",
            "symbol": "NVDA",
            "as_of": "2026-08-07",
            "claims": [
                {
                    "claim_id": "C1",
                    "statement": "Reported revenue increased.",
                    "claim_type": "FACT",
                    "horizon": "reported-quarter",
                    "direction": "positive",
                    "status": "supported",
                    "confidence": 0.95,
                    "supporting_evidence_ids": ["SEC-1"],
                    "counterevidence_ids": [],
                    "depends_on": [],
                    "invalidation_conditions": [],
                },
                {
                    "claim_id": "C2",
                    "statement": "Demand remains supportive over the primary horizon.",
                    "claim_type": "INFERENCE",
                    "horizon": "6-12m",
                    "direction": "positive",
                    "status": "contested",
                    "confidence": 0.65,
                    "supporting_evidence_ids": ["IBKRNEWS-1"],
                    "counterevidence_ids": [],
                    "depends_on": ["C1"],
                    "invalidation_conditions": ["guidance cut"],
                },
            ],
        }

    def test_valid_claim_graph(self):
        self.assertEqual(validate_claim_graph(self.graph, self.evidence_ids), [])

    def test_fact_requires_evidence(self):
        self.graph["claims"][0]["supporting_evidence_ids"] = []
        errors = validate_claim_graph(self.graph, self.evidence_ids)
        self.assertTrue(any("FACT requires" in e for e in errors))

    def test_review_cannot_reference_unknown_claim(self):
        review = {
            "run_id": "NVDA-20260807-A",
            "reviewer": "bear",
            "claim_reviews": [{
                "claim_id": "DOES_NOT_EXIST",
                "assessment": "weaken",
                "reason": "test",
                "evidence_ids": ["SEC-1"],
                "confidence_delta": -0.1,
            }],
            "scenario_probability_deltas": {"bear": 0.05, "base": -0.05},
            "evidence_requests": [],
        }
        errors = validate_review(review, {"C1", "C2"}, self.evidence_ids)
        self.assertTrue(any("unknown claim_id" in e for e in errors))

    def test_arbitration_probabilities_must_sum_to_one(self):
        arbitration = {
            "research_state": "READY_CONDITIONAL",
            "material_supported_claims": ["C1"],
            "material_contested_claims": ["C2"],
            "material_unresolved_claims": [],
            "scenario_probabilities": {"bull": 0.3, "base": 0.4, "bear": 0.2, "unknown": 0.1},
        }
        self.assertEqual(validate_arbitration(arbitration, {"C1", "C2"}), [])
        arbitration["scenario_probabilities"]["unknown"] = 0.2
        self.assertTrue(any("sum to 1.0" in e for e in validate_arbitration(arbitration, {"C1", "C2"})))


class ResearchMemoryTests(unittest.TestCase):
    def decision(self):
        return {
            "run_id": "NVDA-20260807-A",
            "symbol": "NVDA",
            "as_of": "2026-08-07",
            "primary_horizon": "20d",
            "research_state": "READY_CONDITIONAL",
            "scenario_probabilities": {"bull": 0.3, "base": 0.4, "bear": 0.2, "unknown": 0.1},
            "expected_range": {"lower": 100, "upper": 120, "reference_price": 110},
            "thesis_claim_ids": ["C2"],
            "key_invalidation_conditions": ["guidance cut"],
        }

    def test_freeze_and_brier(self):
        frozen = freeze_decision(self.decision())
        self.assertIn("frozen_at", frozen)
        self.assertAlmostEqual(brier_score(frozen["scenario_probabilities"], "base"), 0.50)

    def test_range_coverage(self):
        cov = range_coverage(self.decision(), {"end_price": 115})
        self.assertTrue(cov["covered"])
        self.assertAlmostEqual(cov["range_width_pct"], 20 / 110)

    def test_summary(self):
        record = freeze_decision(self.decision())
        record["outcome"] = {"observed_scenario": "base", "end_price": 115, "alpha": 0.03}
        summary = summarize([record])
        self.assertEqual(summary["completed"], 1)
        self.assertEqual(summary["range_coverage_rate"], 1.0)
        self.assertAlmostEqual(summary["mean_alpha"], 0.03)


if __name__ == "__main__":
    unittest.main()
