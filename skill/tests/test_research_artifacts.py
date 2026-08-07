from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research_artifacts import (
    build_evidence_packet,
    validate_arbitration,
    validate_claim_graph,
    validate_evidence_packet,
    validate_review,
)


class ResearchArtifactTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "schema_version": "1.0",
            "source_id": "sec:NVDA:2026-08-07",
            "provider": "SEC_EDGAR",
            "source_type": "filings",
            "as_of": "2026-08-07",
            "available_at": "2026-08-07",
            "retrieved_at": "2026-08-07T12:00:00Z",
            "reliability": "primary",
            "source_url": "https://data.sec.gov/example",
            "warnings": [],
            "metadata": {},
            "data": {"x": 1},
        }
        self.evidence = build_evidence_packet("NVDA", "2026-08-07", [self.source])
        self.claims = {
            "schema_version": "1.0",
            "symbol": "NVDA",
            "as_of": "2026-08-07",
            "evidence_freeze_hash": self.evidence["evidence_freeze_hash"],
            "claims": [
                {
                    "claim_id": "NVDA-FUND-001",
                    "label": "INFERENCE",
                    "claim": "Margins remain resilient under the base case.",
                    "direction": "positive",
                    "horizon": "6-12m",
                    "evidence_refs": ["sec:NVDA:2026-08-07"],
                    "invalidation": ["gross-margin guidance is cut"],
                }
            ],
        }

    def test_pit_evidence_packet_and_hash_validate(self):
        self.assertEqual(validate_evidence_packet(self.evidence, pit_strict=True), [])
        tampered = {**self.evidence, "symbol": "AMD"}
        self.assertIn("evidence_freeze_hash does not match packet content", validate_evidence_packet(tampered))

    def test_pit_strict_rejects_unproven_current_provider(self):
        source = {**self.source, "source_id": "av:NVDA:now", "provider": "ALPHA_VANTAGE", "available_at": None}
        evidence = build_evidence_packet("NVDA", "2025-01-01", [source])
        errors = validate_evidence_packet(evidence, pit_strict=True)
        self.assertTrue(any("cannot prove PIT" in e for e in errors))

    def test_claim_graph_cannot_cite_outside_freeze(self):
        bad = {**self.claims, "claims": [{**self.claims["claims"][0], "evidence_refs": ["web:unknown"]}]}
        errors = validate_claim_graph(bad, self.evidence)
        self.assertTrue(any("unknown evidence" in e for e in errors))

    def test_review_cannot_smuggle_new_evidence(self):
        review = {
            "role": "bear",
            "findings": [{"claim_id": "NVDA-FUND-001", "reason": "test", "evidence_refs": ["new:source"]}],
            "evidence_requests": [],
        }
        errors = validate_review(review, self.claims, self.evidence)
        self.assertTrue(any("outside freeze" in e for e in errors))

    def test_arbitration_probabilities_must_sum_to_one(self):
        arbitration = {
            "scenarios": {
                "bear": {"probability": 0.2},
                "base": {"probability": 0.4},
                "bull": {"probability": 0.3},
                "unknown": {"probability": 0.2},
            },
            "claim_adjustments": [],
        }
        errors = validate_arbitration(arbitration, self.claims, self.evidence)
        self.assertTrue(any("not 1" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
