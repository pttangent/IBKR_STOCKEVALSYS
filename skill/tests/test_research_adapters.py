from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from fetch_alpha_vantage_research import compact_estimates
from fetch_finra_short_volume import aggregate_rows
from fetch_fred_macro import build_observation_url, normalize_observations
from fetch_polymarket_context import normalize_market
from fetch_sec_research import extract_canonical_financials, normalize_cik, parse_form4_xml
from normalize_ibkr_news import normalize_news


class ResearchAdapterTests(unittest.TestCase):
    def test_sec_cik_and_canonical_fact_cutoff(self):
        self.assertEqual(normalize_cik(320193), "0000320193")
        facts = {
            "facts": {"us-gaap": {"RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
                {"val": 100, "end": "2025-12-31", "filed": "2026-02-01", "form": "10-K", "fy": 2025, "fp": "FY", "accn": "x"},
                {"val": 130, "end": "2026-03-31", "filed": "2026-05-01", "form": "10-Q", "fy": 2026, "fp": "Q1", "accn": "y"},
            ]}}}}
        }
        result = extract_canonical_financials(facts, "2026-03-01")
        self.assertEqual(result["facts"]["revenue"]["value"], 100)
        self.assertEqual(result["facts"]["revenue"]["evidence_label"], "FACT")

    def test_form4_parser_preserves_transaction_code(self):
        xml = """<ownershipDocument>
        <periodOfReport>2026-08-01</periodOfReport>
        <issuer><issuerCik>1</issuerCik><issuerName>Example</issuerName><issuerTradingSymbol>EX</issuerTradingSymbol></issuer>
        <reportingOwner><reportingOwnerId><rptOwnerCik>2</rptOwnerCik><rptOwnerName>Jane Doe</rptOwnerName></reportingOwnerId>
        <reportingOwnerRelationship><isDirector>1</isDirector><isOfficer>0</isOfficer><isTenPercentOwner>0</isTenPercentOwner></reportingOwnerRelationship></reportingOwner>
        <nonDerivativeTable><nonDerivativeTransaction>
        <securityTitle><value>Common</value></securityTitle><transactionDate><value>2026-08-01</value></transactionDate>
        <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
        <transactionAmounts><transactionShares><value>100</value></transactionShares><transactionPricePerShare><value>10.5</value></transactionPricePerShare><transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts>
        <postTransactionAmounts><sharesOwnedFollowingTransaction><value>1000</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
        <ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature>
        </nonDerivativeTransaction></nonDerivativeTable></ownershipDocument>"""
        result = parse_form4_xml(xml)
        self.assertEqual(result["transactions"][0]["transaction_code"], "P")
        self.assertEqual(result["transactions"][0]["shares"], "100")

    def test_fred_url_is_point_in_time_when_as_of_set(self):
        url = build_observation_url(series_id="CPIAUCSL", api_key="x", observation_start="2025-01-01", observation_end="2026-01-01", as_of="2026-01-01")
        self.assertIn("realtime_start=2026-01-01", url)
        self.assertIn("realtime_end=2026-01-01", url)
        rows = normalize_observations({"observations": [{"date": "2026-01-01", "value": "."}, {"date": "2026-02-01", "value": "3.5"}]})
        self.assertIsNone(rows[0]["value"])
        self.assertEqual(rows[1]["value"], 3.5)

    def test_finra_aggregates_facilities_but_labels_flow_proxy(self):
        rows = [
            {"securitiesInformationProcessorSymbolIdentifier": "NVDA", "tradeReportDate": "2026-08-01", "shortParQuantity": 40, "shortExemptParQuantity": 2, "totalParQuantity": 100},
            {"securitiesInformationProcessorSymbolIdentifier": "NVDA", "tradeReportDate": "2026-08-01", "shortParQuantity": 10, "shortExemptParQuantity": 0, "totalParQuantity": 50},
        ]
        out = aggregate_rows(rows, "NVDA")
        self.assertEqual(out[0]["short_sale_volume"], 50)
        self.assertAlmostEqual(out[0]["short_sale_volume_ratio"], 1/3)
        self.assertEqual(out[0]["label"], "SHORT_SALE_FLOW_PROXY")

    def test_polymarket_probability_is_market_implied(self):
        m = normalize_market({"id": "1", "question": "Will X?", "outcomes": '["Yes","No"]', "outcomePrices": '["0.65","0.35"]'})
        self.assertEqual(m["outcomes"][0]["market_implied_probability"], 0.65)
        self.assertEqual(m["label"], "MARKET_IMPLIED_EXPECTATION")

    def test_ibkr_news_normalizer_does_not_create_direction(self):
        rows = normalize_news({"articles": [{"time": "2026-08-07", "providerCode": "DJNL", "articleId": "a", "headline": "Company reports results"}]})
        self.assertEqual(rows[0]["evidence_label"], "FACT")
        self.assertNotIn("sentiment", rows[0])

    def test_alpha_vantage_estimate_shape_is_preserved(self):
        payload = {"annualEarningsEstimates": [{"fiscalDateEnding": "2027-01-01"}], "other": "x"}
        compact = compact_estimates(payload)
        self.assertIn("annualEarningsEstimates", compact["collections"])
        self.assertEqual(compact["raw"]["other"], "x")


if __name__ == "__main__":
    unittest.main()

