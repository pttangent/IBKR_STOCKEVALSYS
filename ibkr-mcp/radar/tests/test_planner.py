import unittest

from radar.planner import build_plan


class PlannerTests(unittest.TestCase):
    def test_default_five_symbol_flow_uses_true_trade_ticks_plus_mktdata_quotes(self):
        plan = build_plan(["TER", "KLAC", "AEHR", "COHU", "FORM"], mode="auto", market_data_lines=100)
        self.assertEqual(plan.mode, "flow")
        self.assertEqual(plan.tick_by_tick_slots, 5)
        self.assertEqual(plan.tick_by_tick_requests_required, 5)
        self.assertEqual(plan.max_flow_symbols, 5)
        self.assertEqual(plan.quality, "TBT_TRADES_MKTDATA_QUOTES")

    def test_more_than_default_tbt_capacity_falls_back_to_radar(self):
        plan = build_plan([f"S{i}" for i in range(12)], mode="auto", market_data_lines=100)
        self.assertEqual(plan.mode, "radar")
        self.assertEqual(plan.tick_by_tick_requests_required, 0)
        self.assertEqual(plan.market_data_lines_required, 12)

    def test_true_bidask_costs_two_tbt_requests_per_symbol(self):
        plan = build_plan(["TER", "KLAC"], mode="flow", market_data_lines=100, flow_quote_source="tick")
        self.assertEqual(plan.tick_by_tick_requests_required, 4)
        self.assertEqual(plan.max_flow_symbols, 2)
        self.assertEqual(plan.quality, "TBT_TRADES_TBT_QUOTES")

    def test_three_true_bidask_symbols_warns_on_default_allocation(self):
        plan = build_plan(["TER", "KLAC", "AEHR"], mode="flow", market_data_lines=100, flow_quote_source="tick")
        self.assertEqual(plan.tick_by_tick_requests_required, 6)
        self.assertTrue(any("requires 6" in warning for warning in plan.warnings))


if __name__ == "__main__":
    unittest.main()
