"""Building/apartment conservation, temporal boundaries and uncertainty regressions."""

import importlib.util
import sys
import unittest
from decimal import Decimal as D
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "site_accounting", Path(__file__).parents[1] / "custom_components/solarshare/site_accounting.py"
)
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)
SiteLedger = module.SiteLedger


class SiteTests(unittest.TestCase):
    def setUp(self):
        self.site = SiteLedger(["a", "b"])
        self.values = {key: D(100) for key in self.site.required}
        self.day = "2026-10-28"
        self.frame(10)

    def frame(self, now, changes=None, day=None, times=None):
        for key, delta in (changes or {}).items():
            self.values[key] += D(str(delta))
        return self.site.observe(
            self.values, times or dict.fromkeys(self.values, now), now, day or self.day
        )

    def test_proportional_allocation_has_40_percent_autarky_for_both_apartments(self):
        self.assertTrue(self.frame(70, {"pv": ".4", "import": ".6", "apt:a": ".3", "apt:b": ".5"}))
        bucket = self.site.totals()
        self.assertEqual(bucket["apartments"]["a"]["solar"], D(".12"))
        self.assertEqual(bucket["apartments"]["b"]["solar"], D(".20"))
        self.assertEqual(module.apartment_metric(bucket["apartments"]["a"], "autarky"), D(40))
        self.assertEqual(bucket["site"]["residual"], D(".2"))
        self.assertEqual(bucket["apartments"]["a"]["grid"], D(".18"))
        self.assertEqual(self.site.totals("day", self.day), bucket)

    def test_grid_only_and_pv_only(self):
        self.frame(70, {"import": 1, "apt:a": ".5", "apt:b": ".5"})
        self.assertEqual(
            module.apartment_metric(self.site.interval["apartments"]["a"], "autarky"), 0
        )
        self.frame(130, {"pv": 1, "apt:a": ".5", "apt:b": ".5"})
        self.assertEqual(
            module.apartment_metric(self.site.interval["apartments"]["a"], "autarky"), 100
        )

    def test_time_of_consumption_changes_apartment_autarky(self):
        self.frame(70, {"pv": 1, "apt:a": 1})
        self.frame(130, {"import": 1, "apt:b": 1})
        apartments = self.site.totals()["apartments"]
        self.assertEqual(module.apartment_metric(apartments["a"], "autarky"), 100)
        self.assertEqual(module.apartment_metric(apartments["b"], "autarky"), 0)

    def test_export_not_allocated_to_apartments(self):
        self.frame(70, {"pv": 1, "export": ".6", "apt:a": ".4"})
        self.assertEqual(self.site.interval["apartments"]["a"]["solar"], D(".4"))

    def test_all_energy_is_conserved_for_apartments(self):
        self.frame(70, {"pv": ".8", "import": ".2", "apt:a": ".3", "apt:b": ".6"})
        for values in self.site.interval["apartments"].values():
            self.assertEqual(
                values["consumption"], values["solar"] + values["grid"] + values["unknown"]
            )

    def test_missing_one_apartment_blocks_every_allocation_and_no_catchup(self):
        self.site.observe(
            self.values | {"apt:b": None}, dict.fromkeys(self.values, 20), 20, self.day
        )
        self.assertFalse(self.site.available)
        self.frame(70, {"pv": 1, "apt:a": ".5", "apt:b": ".5"})
        self.assertIsNone(self.site.totals())
        self.frame(130, {"pv": 1, "apt:a": ".5", "apt:b": ".5"})
        self.assertEqual(self.site.totals()["apartments"]["a"]["consumption"], D(".5"))

    def test_readings_require_every_source_to_report_again(self):
        times = dict.fromkeys(self.values, 70) | {"apt:b": 10}
        self.assertFalse(self.frame(70, {"pv": 1, "apt:a": ".5", "apt:b": ".5"}, times=times))
        self.assertIsNone(self.site.totals())
        self.assertTrue(self.frame(130))

    def test_skew_and_stale_reports_break_continuity(self):
        self.assertFalse(self.frame(100, times=dict.fromkeys(self.values, 100) | {"pv": 10}))
        self.assertEqual(self.site.reason, "sources_not_aligned")
        self.assertFalse(self.frame(400, times=dict.fromkeys(self.values, 10)))
        self.assertEqual(self.site.reason, "stale_source")

    def test_reset_latches_until_review(self):
        self.frame(70, {"pv": -100})
        self.assertTrue(self.site.review)
        self.frame(130, {"pv": 101, "apt:a": 1})
        self.assertIsNone(self.site.totals())

    def test_restart_preserves_totals_without_baseline(self):
        self.frame(70, {"pv": 1, "apt:a": 1})
        snapshot = self.site.snapshot()
        self.site = SiteLedger(["a", "b"])
        self.site.restore(snapshot)
        self.frame(130, {"pv": 10, "apt:a": 10})
        self.assertEqual(self.site.totals()["apartments"]["a"]["consumption"], 1)

    def test_midnight_does_not_assign_cross_day_energy_to_new_day(self):
        self.frame(70, {"pv": 1, "apt:a": 1})
        self.assertFalse(self.frame(130, {"pv": 1, "apt:a": 1}, day="2026-10-29"))
        self.assertIsNone(self.site.totals("day", "2026-10-29"))
        self.frame(190, {"pv": 1, "apt:a": 1}, day="2026-10-29")
        self.assertEqual(self.site.totals("day", "2026-10-29")["apartments"]["a"]["consumption"], 1)
        self.assertEqual(self.site.totals()["apartments"]["a"]["consumption"], 2)

    def test_impossible_balance_and_mixed_directions_are_not_billed(self):
        self.assertFalse(self.frame(70, {"pv": ".2", "apt:a": 1}))
        self.assertEqual(self.site.reason, "inconsistent_energy_balance")
        self.frame(130)
        self.assertFalse(self.frame(190, {"import": 1, "export": 1, "pv": 1}))
        self.assertEqual(self.site.reason, "mixed_direction_interval")
        self.assertIsNone(self.site.totals())

    def test_zero_load_has_no_invented_percentage(self):
        self.frame(70)
        self.assertIsNone(module.apartment_metric(self.site.interval["apartments"]["a"], "autarky"))

    def test_battery_origin_unknown_is_not_autarky(self):
        self.site = SiteLedger(["a"], battery=True, capacity=1)
        self.values = dict.fromkeys(self.site.required, D(100))
        self.frame(10)
        self.frame(70, {"discharge": ".5", "apt:a": ".5"})
        values = self.site.interval["apartments"]["a"]
        self.assertEqual(values["unknown"], D(".5"))
        self.assertEqual(values["battery"], D(".5"))
        self.assertIsNone(module.apartment_metric(values, "autarky"))

    def test_battery_grid_charging_is_not_solar(self):
        self.site = SiteLedger(["a"], battery=True, capacity=1)
        self.values = dict.fromkeys(self.site.required, D(100))
        self.frame(10)
        self.frame(70, {"import": 1, "charge": 1})
        self.frame(130, {"discharge": ".5", "apt:a": ".5"})
        values = self.site.interval["apartments"]["a"]
        self.assertEqual(values["solar"], 0)
        self.assertGreater(values["grid"], 0)
        self.assertEqual(values["grid"] + values["unknown"], values["consumption"])

    def test_solar_charging_is_not_counted_twice(self):
        self.site = SiteLedger(["a"], battery=True, capacity=1)
        self.values = dict.fromkeys(self.site.required, D(100))
        self.frame(10)
        self.frame(70, {"pv": 1, "charge": 1})
        self.assertEqual(self.site.totals()["apartments"]["a"]["solar"], 0)
        self.frame(130, {"discharge": ".5", "apt:a": ".5"})
        self.assertLessEqual(self.site.totals()["apartments"]["a"]["solar"], D(".5"))
        self.assertEqual(self.site.totals()["site"]["pv"], 1)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.site = SiteLedger(["a"], require_fresh_reports=False)
        self.readings = dict.fromkeys(self.site.required, D(100))
        self.times = dict.fromkeys(self.site.required, 10)
        self.day = "2026-10-28"
        self.site.observe(self.readings, self.times, 4000, self.day)

    def test_available_night_pv_counter_can_remain_unchanged(self):
        changed = self.readings | {"import": D("100.2"), "apt:a": D("100.2")}
        self.assertTrue(self.site.observe(changed, self.times, 4060, self.day))
        apartment = self.site.totals()["apartments"]["a"]
        self.assertEqual(apartment["solar"], 0)
        self.assertEqual(apartment["grid"], D(".2"))
        self.assertEqual(module.apartment_metric(apartment, "autarky"), 0)

    def test_missing_source_is_not_zero_and_gap_is_not_recovered(self):
        self.assertFalse(
            self.site.observe(self.readings | {"pv": None}, self.times, 4060, self.day)
        )
        self.assertEqual(self.site.reason, "source_unavailable")
        self.site.observe(
            self.readings | {"import": D(200), "apt:a": D(200)}, self.times, 4120, self.day
        )
        self.assertIsNone(self.site.totals())

    def test_runtime_outage_still_breaks_continuity(self):
        self.assertFalse(
            self.site.observe(
                self.readings | {"import": D(101), "apt:a": D(101)}, self.times, 4400, self.day
            )
        )
        self.assertIsNone(self.site.totals())


if __name__ == "__main__":
    unittest.main()
