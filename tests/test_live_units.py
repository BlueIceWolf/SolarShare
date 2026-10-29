"""Local-only regression for proportional live home/EV charger views.

Run with python -m unittest tests.test_live_units -v.
This module loads only the two runtime methods under test; HA need not be installed.
"""

import ast
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).parents[1] / "custom_components" / "solarshare" / "site_runtime.py"


def runtime_live_methods():
    source = ast.parse(ROOT.read_text(encoding="utf-8"))
    cls = next(node for node in source.body
               if isinstance(node, ast.ClassDef) and node.name == "SiteRuntime")
    selected = [node for node in cls.body
                if isinstance(node, ast.FunctionDef)
                and node.name in ("live_unit_metrics", "_live_unit_power")]
    new_class = ast.ClassDef(name="SiteRuntime", bases=[], keywords=[],
                             body=selected, decorator_list=[])
    exec(compile(ast.fix_missing_locations(
        ast.Module(body=[new_class], type_ignores=[])), str(ROOT), "exec"),
         namespace := {"time": time})
    return namespace["SiteRuntime"]


def power(value, unit="W", age=1):
    return SimpleNamespace(
        state=str(value), attributes={"unit_of_measurement": unit, "device_class": "power"},
        last_reported=SimpleNamespace(timestamp=lambda: time.time() - age),
    )


class UnitLiveTests(unittest.TestCase):
    def setUp(self):
        cls = runtime_live_methods()
        self.runtime = cls()
        self.runtime.hass = SimpleNamespace(states={
            "sensor.flat1_power": power(2000),
            "sensor.flat2_power": power(1000),
            "sensor.wallbox_power": power(500),
        })
        self.flat1 = {"id": "a", "power": "sensor.flat1_power"}
        self.flat2 = {"id": "b", "power": "sensor.flat2_power"}
        self.wallbox = {"id": "c", "power": "sensor.wallbox_power", "kind": "wallbox"}
        self.runtime.units = [self.flat1, self.flat2, self.wallbox]
        self.runtime.live_metrics = lambda: {"autarky": 60.0, "load_w": 5000, "import_w": 2000}

    def test_each_unit_has_same_percentage_but_different_allocated_watts(self):
        first = self.runtime.live_unit_metrics(self.flat1)
        second = self.runtime.live_unit_metrics(self.flat2)
        charger = self.runtime.live_unit_metrics(self.wallbox)
        self.assertEqual(first["autarky"], 60)
        self.assertEqual(second["autarky"], 60)
        self.assertEqual(first["local_w"], 1200)
        self.assertEqual(first["grid_w"], 800)
        self.assertEqual(second["local_w"], 600)
        self.assertEqual(charger["grid_w"], 200)
        self.assertEqual(first["accounting_scope"], "display_only_not_billable")

    def test_missing_and_stale_readings_are_not_guessed(self):
        self.assertIsNone(self.runtime.live_unit_metrics({"id": "x"}))
        self.runtime.hass.states["sensor.flat1_power"] = power(1000, age=360)
        self.assertIsNone(self.runtime.live_unit_metrics(self.flat1))

    def test_overlapping_watts_are_rejected(self):
        self.runtime.hass.states["sensor.flat1_power"] = power(4500)
        self.runtime.hass.states["sensor.flat2_power"] = power(2000)
        self.assertIsNone(self.runtime.live_unit_metrics(self.flat1))

    def test_paused_unit_has_no_live_allocation(self):
        self.assertIsNone(self.runtime.live_unit_metrics(
            {**self.flat1, "paused": True}))


if __name__ == "__main__":
    unittest.main()
