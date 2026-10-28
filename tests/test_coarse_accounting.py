"""Coarse upstream counters and fine apartment meters share one bounded window."""

import importlib.util
import unittest
from decimal import Decimal as D
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "coarse_ledger", Path(__file__).parents[1] / "custom_components/solarshare/site_accounting.py"
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class CoarseMeterTests(unittest.TestCase):
    def setUp(self):
        self.ledger = module.SiteLedger(["a"], require_fresh_reports=False, aggregation_seconds=300)
        self.values = dict.fromkeys(self.ledger.required, D(100))
        self.frame(0)

    def frame(self, now, changes=None, day="2026-10-28"):
        self.values.update({key: D(str(value)) for key, value in (changes or {}).items()})
        return self.ledger.observe(self.values, dict.fromkeys(self.values, now), now, day)

    def test_fine_consumption_waits_for_coarse_point_one_kwh_register(self):
        for now in range(60, 601, 60):
            self.assertFalse(self.frame(now, {"apt:a": D(100) + D(now) / 6000}))
            self.assertEqual(self.ledger.reason, "waiting_for_meter_window")
            self.assertEqual(self.ledger.gaps, 0)
            self.assertEqual(self.ledger.frame_time, 0)
            self.assertIsNone(self.ledger.totals())
        self.assertTrue(self.frame(660, {"import": "100.1"}))
        apartment = self.ledger.totals()["apartments"]["a"]
        self.assertEqual(apartment["consumption"], D(".1"))
        self.assertEqual(apartment["grid"], D(".1"))
        self.assertEqual(apartment["unknown"], 0)
        self.assertEqual(self.ledger.interval["seconds"], 660)
        self.assertEqual(self.ledger.pending_seconds, 0)

    def test_wait_keeps_published_totals_and_does_not_reuse_average_power(self):
        for now in range(60, 300, 60):
            self.frame(now)
        self.assertTrue(self.frame(300, {"import": "100.1", "apt:a": "100.1"}))
        total = self.ledger.snapshot()["periods"]
        self.assertFalse(self.frame(360, {"apt:a": "100.11"}))
        self.assertTrue(self.ledger.available)
        self.assertIsNone(self.ledger.interval)
        self.assertEqual(self.ledger.snapshot()["periods"], total)

    def test_real_missing_source_discards_pending_window_without_catchup(self):
        self.frame(60, {"apt:a": "100.01"})
        self.values["import"] = None
        self.frame(120)
        self.assertEqual(self.ledger.reason, "source_unavailable")
        self.assertEqual(self.ledger.gaps, 1)
        self.frame(180, {"import": 101, "apt:a": 101})
        self.assertIsNone(self.ledger.totals())
        self.assertEqual(self.ledger.frame_time, 180)

    def test_real_runtime_gap_and_midnight_do_not_bridge_pending_window(self):
        for next_time, day in ((500, "2026-10-28"), (120, "2026-10-29")):
            with self.subTest(day=day):
                self.setUp()
                self.frame(60, {"apt:a": "100.01"})
                self.frame(next_time, {"import": 101, "apt:a": 101}, day=day)
                self.assertEqual(self.ledger.reason, "baseline_ready")
                self.assertEqual(self.ledger.frame_time, next_time)
                self.assertIsNone(self.ledger.totals())

    def test_permanent_imbalance_stops_after_one_hour(self):
        for now in range(60, 3600, 60):
            self.frame(now, {"apt:a": D(100) + D(now) / 6000})
        self.frame(3600, {"apt:a": "100.6"})
        self.assertEqual(self.ledger.reason, "inconsistent_energy_balance")
        self.assertEqual(self.ledger.gaps, 1)
        self.assertIsNone(self.ledger.totals())

    def test_reset_above_original_baseline_is_still_detected_while_waiting(self):
        self.frame(60, {"import": "100.1"})
        self.frame(120, {"import": "100.05"})
        self.assertTrue(self.ledger.review)
        self.assertEqual(self.ledger.reason, "meter_reset_or_implausible_jump")
        self.assertIsNone(self.ledger.totals())

    def test_mixed_directions_still_block_billing(self):
        for now in range(60, 300, 60):
            self.frame(now)
        self.frame(300, {"import": "100.1", "export": "100.1"})
        self.assertEqual(self.ledger.reason, "mixed_direction_interval")
        self.assertIsNone(self.ledger.totals())

    def test_restart_does_not_restore_pending_baseline(self):
        self.frame(60, {"apt:a": "100.01"})
        snapshot = self.ledger.snapshot()
        self.ledger = module.SiteLedger(["a"], require_fresh_reports=False, aggregation_seconds=300)
        self.ledger.restore(snapshot)
        self.frame(120, {"import": 101, "apt:a": 101})
        self.assertEqual(self.ledger.reason, "baseline_ready")
        self.assertEqual(self.ledger.frame_time, 120)
        self.assertIsNone(self.ledger.totals())
