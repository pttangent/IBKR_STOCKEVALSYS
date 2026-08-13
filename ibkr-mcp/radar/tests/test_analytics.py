import unittest

from radar.analytics import TradeEvent, absorption_scores, build_footprint, classify_trade, flow_split


class AnalyticsTests(unittest.TestCase):
    def test_quote_rule_classification(self):
        self.assertEqual(classify_trade(100.02, 100.00, 100.02), 1)
        self.assertEqual(classify_trade(100.00, 100.00, 100.02), -1)
        self.assertEqual(classify_trade(100.015, 100.00, 100.02), 1)

    def test_flow_split(self):
        trades = [TradeEvent(1, 100, 20, 1), TradeEvent(2, 100, 10, -1), TradeEvent(3, 100, 5, 0)]
        split = flow_split(trades)
        self.assertEqual(split["buyVolume"], 20)
        self.assertEqual(split["sellVolume"], 10)
        self.assertAlmostEqual(split["pressure"], 100 / 3, places=5)
        self.assertAlmostEqual(split["knownFraction"], 2 / 3, places=5)

    def test_bid_absorption_when_heavy_selling_does_not_move_price(self):
        trades = [TradeEvent(i, 100.00 + (0.0001 if i % 2 else 0.0), 100, -1) for i in range(1, 21)]
        scores = absorption_scores(trades)
        self.assertGreater(scores["bidAbsorption"], 80)
        self.assertLess(scores["offerAbsorption"], 1)

    def test_footprint_aggregates_price_levels(self):
        trades = [TradeEvent(1, 100.00, 10, -1), TradeEvent(2, 100.00, 20, 1), TradeEvent(3, 100.01, 5, 1)]
        rows = build_footprint(trades, tick_size=0.01)
        row100 = next(row for row in rows if abs(row["price"] - 100.0) < 1e-9)
        self.assertEqual(row100["sellAtBid"], 10)
        self.assertEqual(row100["buyAtAsk"], 20)
        self.assertEqual(row100["delta"], 10)


if __name__ == "__main__":
    unittest.main()
