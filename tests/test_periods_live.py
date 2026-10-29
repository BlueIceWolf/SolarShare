"""Pure local-only tests for last-week/month billing and live power.

Run locally with:
    python -m unittest discover -s tests -p 'test_*accounting.py' -v
    python -m unittest tests.test_periods_live -v
No GitHub Actions or Home Assistant installation required.
"""

import importlib.util
import sys
import types
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).parents[1] / "custom_components" / "solarshare"
PACKAGE = "_solarshare_calendar_tests"
if PACKAGE not in sys.modules:
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(ROOT)]
    sys.modules[PACKAGE] = package


def load(name):
    spec = importlib.util.spec_from_file_location(f"{PACKAGE}.{name}", ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


periods = load("periods")
live = load("site_live")
observed = load("observed_consumption")
tariffs = load("tariff_accounting")


class CalendarPeriodsTests(unittest.TestCase):
    def test_previous_week_is_monday_to_sunday(self):
        self.assertEqual(periods.period_key("week", "2026-10-29"), "week:2026-10-26")
        self.assertEqual(periods.period_key("last_week", "2026-10-29"), "week:2026-10-19")
        self.assertEqual(periods.period_key("last_week", "2026-11-02"), "week:2026-10-26")

    def test_previous_month_across_year_boundary(self):
        self.assertEqual(periods.period_key("last_month", "2027-01-05"), "month:2026-12")
        self.assertEqual(periods.period_key("last_month", "2026-03-01"), "month:2026-02")

    def test_observed_meter_week_and_month_retained_after_restore(self):
        tracker = observed.ObservedConsumption(max_power_kw=200)
        tracker.observe("w1", 100, 0, "2026-10-25")
        tracker.observe("w1", 101, 60, "2026-10-25")
        tracker.invalidate("w1")
        tracker.observe("w1", 110, 120, "2026-10-26")
        tracker.observe("w1", 112, 180, "2026-10-26")
        recovered = observed.ObservedConsumption()
        recovered.restore(tracker.snapshot())
        self.assertEqual(recovered.value("w1", "last_week", "2026-10-29"), Decimal("1"))
        self.assertEqual(recovered.value("w1", "week", "2026-10-29"), Decimal("2"))
        self.assertEqual(recovered.value("w1", "month", "2026-10-29"), Decimal("3"))
        self.assertIsNone(recovered.value("w1", "last_month", "2026-10-29"))

    def test_tariff_history_has_previous_period_cost(self):
        t = tariffs.TariffLedger()
        a = {"w1": {"solar": Decimal(1), "grid": Decimal(2),
                    "unknown": Decimal(0), "consumption": Decimal(3)}}
        self.assertTrue(t.record(a, "2026-09-20", {"solar":"0.20","grid":"0.35"}))
        self.assertTrue(t.record(a, "2026-10-20", {"solar":"0.21","grid":"0.36"}))
        recovered = tariffs.TariffLedger()
        recovered.restore(t.snapshot())
        old = recovered.value("w1", "last_month", "2026-10-29")
        self.assertEqual(old["solar_eur"] + old["grid_eur"], Decimal("0.90"))
        self.assertEqual(recovered.value("w1", "month", "2026-10-29")["solar_eur"], Decimal("0.21"))


class LivePowerTests(unittest.TestCase):
    def test_simple_direct_measurement(self):
        v = live.live_autarky({"load":4000,"import":1000}, battery=True)
        self.assertEqual(v["autarky"], 75)
        self.assertEqual(v["measured"], "direct_load")

    def test_battery_power_balance(self):
        v = live.live_autarky({"pv":1000,"import":800,"export":0,
                               "charge":300,"discharge":500}, battery=True)
        self.assertEqual(v["load_w"], 2000)
        self.assertEqual(v["autarky"], 60)

    def test_missing_or_stale_inputs_must_not_produce_guessed_live_value(self):
        self.assertIsNone(live.live_autarky({"import":200}, battery=False))
        self.assertIsNone(live.live_autarky({"pv":1000,"import":0,"export":0}, battery=True))
        self.assertIsNone(live.live_autarky({"load":0,"import":0}))
        self.assertIsNone(live.live_autarky({"load":300,"import":900}))


if __name__ == "__main__":
    unittest.main()
