"""Night restart, wake-up boundaries and non-PV source gaps."""

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


PVNight, SiteLedger = load("pv_night").PVNight, load("site_accounting").SiteLedger


class PVNightTests(unittest.TestCase):
    def setUp(self):
        self.policy = PVNight(["pv"])
        self.ledger = SiteLedger(["a"], require_fresh_reports=False)
        self.raw = {"pv": None, "import": D(100), "export": D(10), "apt:a": D(50)}
        self.day = "2026-10-28"

    def frame(self, now, raw=None, sun="below_horizon", eligible=("pv",)):
        raw = raw if raw is not None else self.raw
        result, times, transition = self.policy.apply(
            raw, dict.fromkeys(raw, now), now, sun, eligible
        )
        if transition:
            self.ledger.interrupt("pv_night_transition")
        return self.ledger.observe(result, times, now, self.day)

    def test_restart_at_night_needs_no_prior_physical_pv_reading(self):
        self.assertFalse(self.frame(10))
        self.assertTrue(self.frame(70, self.raw | {"import": D("100.1"), "apt:a": D("50.1")}))
        self.assertEqual(self.ledger.totals()["apartments"]["a"]["grid"], D(".1"))
        self.assertEqual(self.ledger.totals()["site"]["pv"], 0)
        self.assertIsNone(self.raw["pv"])
        self.assertNotIn("pv", self.policy.last_good)

    def test_daytime_or_unknown_sun_never_replaces_missing_pv(self):
        for sun in ("above_horizon", "unknown", "unavailable", None):
            self.assertFalse(self.frame(10, sun=sun))
            self.assertFalse(self.ledger.available)

    def test_grid_and_battery_are_never_substituted(self):
        self.frame(10)
        self.assertFalse(self.frame(70, self.raw | {"import": None}))
        self.assertIsNone(self.ledger.totals())
        raw = self.raw | {"charge": None, "discharge": None}
        effective, _, _ = self.policy.apply(raw, {}, 100, "below_horizon", {"pv"})
        self.assertIsNone(effective["charge"])
        self.assertIsNone(effective["discharge"])

    def test_wake_up_does_not_book_a_lifetime_counter(self):
        self.frame(10)
        self.frame(70, self.raw | {"import": D("100.1"), "apt:a": D("50.1")})
        awake = self.raw | {"pv": D(5000), "import": D("100.1"), "apt:a": D("50.1")}
        self.assertFalse(self.frame(130, awake, sun="above_horizon"))
        self.assertTrue(
            self.frame(190, awake | {"pv": D("5000.1"), "apt:a": D("50.2")}, sun="above_horizon")
        )
        self.assertEqual(self.ledger.totals()["site"]["pv"], D(".1"))
        self.assertEqual(self.ledger.totals()["apartments"]["a"]["consumption"], D(".2"))

    def test_day_counter_to_night_zero_is_not_a_reset(self):
        self.frame(10, self.raw | {"pv": D(5000)}, sun="above_horizon")
        self.assertFalse(self.frame(70))
        self.assertFalse(self.ledger.review)
        self.assertTrue(self.frame(130, self.raw | {"import": D("100.1"), "apt:a": D("50.1")}))

    def test_saved_counters_are_for_diagnostics_not_backfill(self):
        self.policy.restore({"pv": "1234.5"})
        self.frame(10)
        self.assertEqual(self.policy.snapshot(), {"pv": "1234.5"})
        self.assertIsNone(self.ledger.totals())
        self.assertEqual(self.ledger.baseline["pv"], 0)

    def test_valid_night_pv_production_is_not_forced_to_zero(self):
        self.frame(10, self.raw | {"pv": D(100)})
        self.assertTrue(self.frame(70, self.raw | {"pv": D("100.1"), "apt:a": D("50.1")}))
        self.assertFalse(self.policy.sleeping)
        self.assertEqual(self.ledger.totals()["site"]["pv"], D(".1"))

    def test_disabled_policy_or_invalid_metadata_never_fills(self):
        self.policy.enabled = False
        self.assertFalse(self.frame(10))
        self.policy.enabled = True
        self.assertFalse(self.frame(70, eligible=()))
