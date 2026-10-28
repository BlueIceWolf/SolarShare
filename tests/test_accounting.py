"""Executable offline regression tests for the conservative ledger."""

import importlib.util
import sys
import unittest
from decimal import Decimal as D
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "solarshare_accounting",
    Path(__file__).parents[1] / "custom_components/solarshare/accounting.py",
)
accounting = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = accounting
SPEC.loader.exec_module(accounting)
Ledger, energy_kwh = accounting.Ledger, accounting.energy_kwh


class AccountingTests(unittest.TestCase):
    def test_units_and_invalid_states(self):
        for raw in ("unknown", "unavailable", "NaN", "Infinity", "-1", None, True):
            self.assertIsNone(energy_kwh(raw, "kWh"))
        self.assertEqual(energy_kwh("1250", "Wh"), D("1.25"))
        self.assertEqual(energy_kwh("0.5", "MWh"), D(500))
        self.assertIsNone(energy_kwh("123", "W"))

    def test_first_reading_is_baseline_not_consumption(self):
        ledger = Ledger()
        self.assertFalse(ledger.available)
        ledger.observe(D(10000), 10)
        self.assertEqual(ledger.total, 0)
        ledger.observe(D("10000.1"), 70)
        self.assertEqual(ledger.total, D("0.1"))

    def test_unavailable_never_becomes_zero_or_catchup(self):
        ledger = Ledger()
        ledger.observe(D(100), 10)
        ledger.observe(D("100.2"), 70)
        ledger.observe(None, 80)
        ledger.observe(None, 90)
        self.assertFalse(ledger.available)
        self.assertEqual(ledger.gaps, 1)
        self.assertEqual(ledger.total, D("0.2"))
        ledger.observe(D(150), 100)
        ledger.observe(D("150.1"), 160)
        self.assertEqual(ledger.total, D("0.3"))

    def test_restart_discards_even_persisted_baseline(self):
        ledger = Ledger()
        ledger.observe(D(100), 10)
        ledger.observe(D("100.2"), 70)
        restored = Ledger.restore(ledger.snapshot())
        self.assertFalse(restored.available)
        restored.observe(D(999), 1000)
        self.assertEqual(restored.total, D("0.2"))
        restored.observe(D("999.1"), 1060)
        self.assertEqual(restored.total, D("0.3"))

    def test_long_gap_is_not_allocated(self):
        ledger = Ledger()
        ledger.observe(D(10), 10)
        ledger.observe(D(20), 311)
        self.assertEqual(ledger.total, 0)
        self.assertEqual(ledger.gaps, 1)

    def test_reset_and_rebound_are_latched_across_restart(self):
        ledger = Ledger()
        ledger.observe(D(1000), 10)
        ledger.observe(D(0), 20)
        ledger.observe(D(1001), 80)
        self.assertTrue(ledger.review_required)
        self.assertEqual(ledger.total, 0)
        self.assertFalse(ledger.available)
        restored = Ledger.restore(ledger.snapshot())
        restored.observe(D(1002), 140)
        self.assertTrue(restored.review_required)
        self.assertEqual(restored.total, 0)

    def test_startup_zero_then_large_restored_value_is_not_consumption(self):
        ledger = Ledger()
        ledger.observe(D(0), 10)
        ledger.observe(D(10000), 11)
        self.assertTrue(ledger.review_required)
        self.assertEqual(ledger.total, 0)

    def test_duplicate_or_backward_timestamp_breaks_continuity(self):
        for timestamp in (9, 10):
            ledger = Ledger()
            ledger.observe(D(100), 10)
            ledger.observe(D(101), timestamp)
            self.assertFalse(ledger.available)
            self.assertEqual(ledger.total, 0)

    def test_invalid_storage_fails_closed(self):
        for data in (
            {"total": "NaN", "gaps": 0, "review_required": False},
            {"total": "1", "gaps": -1, "review_required": False},
            {"total": "1", "gaps": 0, "review_required": "false"},
        ):
            with self.assertRaises(ValueError):
                Ledger.restore(data)

    def test_wh_conversion_preserves_decimal_precision(self):
        ledger = Ledger()
        ledger.observe(energy_kwh("1000", "Wh"), 10)
        ledger.observe(energy_kwh("1001", "Wh"), 20)
        self.assertEqual(str(ledger.total), "0.001")


if __name__ == "__main__":
    unittest.main()
