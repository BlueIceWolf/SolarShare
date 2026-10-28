"""Multiple PV source conservation and independently detected inverter resets."""

import importlib.util
import unittest
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).parents[1] / "custom_components/solarshare"


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


model, sources = load("site_accounting"), load("pv_sources")


class MultiPVTests(unittest.TestCase):
    def setUp(self):
        self.site = model.SiteLedger(["a"], pv_keys=("pv:wr1", "pv:wr2"))
        self.values = dict.fromkeys(self.site.required, D(100))
        self.frame(10)

    def frame(self, now, changes=None):
        for key, value in (changes or {}).items():
            self.values[key] += D(str(value))
        return self.site.observe(self.values, dict.fromkeys(self.values, now), now, "2026-10-28")

    def test_multiple_inverters_feed_one_pv_allocation(self):
        self.assertTrue(
            self.frame(70, {"pv:wr1": ".1", "pv:wr2": ".3", "import": ".6", "apt:a": 1})
        )
        totals = self.site.totals()
        self.assertEqual(totals["site"]["pv"], D(".4"))
        self.assertEqual(totals["apartments"]["a"]["solar"], D(".4"))
        self.assertEqual(model.apartment_metric(totals["apartments"]["a"], "autarky"), 40)

    def test_one_reset_cannot_hide_behind_other_inverter_growth(self):
        self.assertFalse(self.frame(70, {"pv:wr1": -1, "pv:wr2": "1.1", "apt:a": ".1"}))
        self.assertTrue(self.site.review)
        self.assertIsNone(self.site.totals())

    def test_missing_one_source_does_not_reduce_pv_to_partial_sum(self):
        readings = self.values | {"pv:wr1": None}
        self.site.observe(readings, dict.fromkeys(readings, 70), 70, "2026-10-28")
        self.assertFalse(self.site.available)
        self.assertIsNone(sources.total_pv(readings, self.site.pv_keys))
        self.frame(130, {"pv:wr1": 1, "apt:a": 1})
        self.assertIsNone(self.site.totals())

    def test_old_single_source_assignments_remain_supported(self):
        self.assertEqual(
            sources.source_meters({"pv": "sensor.pv", "import": "sensor.grid"}),
            {"pv": "sensor.pv", "import": "sensor.grid"},
        )
        self.assertEqual(sources.source_meters({"pv": ["sensor.pv"]}), {"pv": "sensor.pv"})

    def test_individual_sources_have_stable_keys(self):
        first = sources.source_meters({"pv": ["sensor.one", "sensor.two"]})
        second = sources.source_meters({"pv": ["sensor.two", "sensor.one"]})
        self.assertEqual(first, second)
        self.assertEqual(set(first), {"pv:sensor.one", "pv:sensor.two"})

    def test_duplicate_source_is_visible_to_validation(self):
        entities = sources.source_entities(
            {"pv": ["sensor.pv", "sensor.pv"], "import": "sensor.grid"}
        )
        self.assertNotEqual(len(entities), len(set(entities)))

    def test_two_growatt_totals_of_same_inverter_are_detected(self):
        ac = "sensor.growatt_mod_4000_tl_3_total_power_generation"
        other = "sensor.growatt_mod_4000_tl_3_total_solar_energy"
        self.assertEqual(sources.overlapping_growatt_totals([ac, other]), [[ac, other]])
        self.assertEqual(
            sources.overlapping_growatt_totals([ac, "sensor.growatt_mod_6000_total_solar_energy"]),
            [],
        )

    def test_total_is_not_the_first_source_and_missing_never_becomes_zero(self):
        self.assertEqual(sources.total_pv({"one": D(1), "two": D(2)}, ["one", "two"]), 3)
        self.assertIsNone(sources.total_pv({"one": D(1)}, ["one", "two"]))
