from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_fundamental_layer import build_layer


class FundamentalLayerTests(unittest.TestCase):
    def test_roles_do_not_require_ibkr_for_research_readiness(self):
        sec = {"data": {"canonical_financials": {"facts": {"revenue": {"value": 100}}, "quality": {"ratio_safe": True}}}}
        simfin = {"data": {"statement_mode": "standardized", "endpoints": {"statements": {"status": "ok"}}}}
        av = {"data": {"earnings_estimates": {"collections": {"quarterly": [{"x": 1}]}}}}
        finnhub = {"data": {"endpoints": {"profile": {"status": "ok"}, "calendar": {"status": "ok"}}}}
        alpaca = {"data": {"endpoints": {"snapshot": {"status": "ok"}, "bars": {"status": "ok"}}}}
        layer = build_layer(symbol="KLAC", as_of="2026-08-13", sec=sec, reconciled={"quality": {"ratio_safe": True}}, simfin=simfin, alpha_vantage=av, finnhub=finnhub, ibkr_fundamentals={}, alpaca=alpaca)
        self.assertEqual(layer["data_lane"], "research_non_ibkr")
        self.assertTrue(layer["report_readiness"]["reported_actuals"])
        self.assertTrue(layer["report_readiness"]["peer_standardization"])
        self.assertTrue(layer["report_readiness"]["current_market_expectations"])
        self.assertTrue(layer["report_readiness"]["market_reaction_context"])
        self.assertFalse(layer["report_readiness"]["ibkr_required_for_current_report"])
        self.assertFalse(layer["source_roles"]["market_reaction"]["accounting_fundamentals_allowed"])

    def test_missing_expectations_downgrades_only_expectation_claims(self):
        sec = {"data": {"canonical_financials": {"facts": {"revenue": {"value": 100}}, "quality": {"ratio_safe": True}}}}
        layer = build_layer(symbol="TER", as_of="2026-08-13", sec=sec, reconciled={"quality": {"ratio_safe": True}}, simfin={}, alpha_vantage={}, finnhub={}, ibkr_fundamentals={}, alpaca={})
        self.assertTrue(layer["report_readiness"]["reported_actuals"])
        self.assertFalse(layer["report_readiness"]["current_market_expectations"])
        self.assertIn("Alpha Vantage expectations are unavailable/empty; consensus, revision, and priced-in claims must be downgraded.", layer["limitations"])


if __name__ == "__main__":
    unittest.main()
