"""Integration checks against real Home Assistant (Linux, see CI)."""

import tempfile
import unittest
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntries
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.solarshare.config_flow import (
    SolarShareConfigFlow,
    SolarShareOptionsFlow,
    validate,
)
from custom_components.solarshare.runtime import SolarShareRuntime
from custom_components.solarshare.sensor import ApartmentEnergy

ATTRS = {"device_class": "energy", "state_class": "total_increasing", "unit_of_measurement": "kWh"}


def entry(**overrides):
    """Minimal object for direct boundary tests, without config-entry internals."""
    return SimpleNamespace(
        entry_id="apartment-1",
        title="Apartment 1",
        data={
            "name": "Apartment 1",
            "meter": "sensor.meter",
            "max_power_kw": 25,
            "revision": "first",
            "ledger_initialized": True,
        },
        options={},
        **overrides,
    )


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.temp.name)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        dr.async_setup(self.hass)
        await dr.async_load(self.hass)
        await er.async_load(self.hass)
        self.entry = entry()
        self.runtime = SolarShareRuntime(self.hass, self.entry)
        self.runtime.store = AsyncMock()
        self.runtime.store.async_load.return_value = {
            "ledger": {"total": "4.2", "gaps": 0, "review_required": False},
            "revision": "first",
            "identity": None,
        }
        await self.runtime.async_load()

    async def asyncTearDown(self):
        await self.runtime.async_stop()
        await self.hass.async_stop()
        self.temp.cleanup()

    async def process(self, value, now, **attrs):
        await self.runtime._process(State("sensor.meter", value, ATTRS | attrs), now)

    async def test_missing_startup_then_recovery_no_false_zero(self):
        sensor = ApartmentEnergy(SimpleNamespace(runtime_data=self.runtime, entry_id="a"))
        await self.runtime._process(None, 10)
        self.assertFalse(sensor.available)
        self.assertEqual(sensor.native_value, Decimal("4.2"))
        await self.process("100", 20)
        await self.process("100.1", 80)
        self.assertTrue(sensor.available)
        self.assertEqual(sensor.native_value, Decimal("4.3"))
        await self.process("unavailable", 90)
        await self.process("200", 100)
        self.assertEqual(sensor.native_value, Decimal("4.3"))

    async def test_restored_stale_and_wrong_metadata_are_rejected(self):
        await self.process("100", 10, restored=True)
        self.assertFalse(self.runtime.ledger.available)
        state = State(
            "sensor.meter", "100", ATTRS, last_updated=dt_util.utcnow() - timedelta(minutes=20)
        )
        await self.runtime._process(state, 20)
        self.assertFalse(self.runtime.ledger.available)
        await self.process("100", 30, state_class="measurement")
        self.assertFalse(self.runtime.ledger.available)

    async def test_storage_failure_stops_future_observation(self):
        await self.process("100", 10)
        self.runtime.store.async_save.side_effect = OSError("disk full")
        with self.assertLogs("custom_components.solarshare.runtime", level="ERROR"):
            await self.process("100.1", 70)
        self.assertFalse(self.runtime.ledger.available)
        self.assertTrue(self.runtime.storage_failed)
        calls = self.runtime.store.async_save.call_count
        await self.process("100.2", 130)
        self.assertEqual(self.runtime.store.async_save.call_count, calls)

    async def test_missing_initialized_storage_fails_setup(self):
        self.runtime.store.async_load.return_value = None
        with self.assertRaises(Exception):
            await self.runtime.async_load()
        self.assertEqual(self.runtime.ledger.total, Decimal("4.2"))

    async def test_reassignment_preserves_total_and_clears_only_review(self):
        self.runtime.config["revision"] = "new-meter"
        self.runtime.store.async_load.return_value["ledger"]["review_required"] = True
        await self.runtime.async_load()
        self.assertFalse(self.runtime.ledger.review_required)
        await self.process("5000", 10)
        self.assertEqual(self.runtime.ledger.total, Decimal("4.2"))

    async def test_serialized_writes_and_stop_drains_work(self):
        self.runtime.active = True
        self.runtime._queue(State("sensor.meter", "100", ATTRS), 10)
        self.runtime._queue(State("sensor.meter", "100.1", ATTRS), 70)
        await self.runtime.async_stop()
        self.assertEqual(self.runtime.ledger.total, Decimal("4.3"))
        saved = self.runtime.store.async_save.call_args.args[0]
        self.assertEqual(saved["ledger"]["total"], "4.3")
        calls = self.runtime.store.async_save.call_count
        self.runtime._queue(State("sensor.meter", "200", ATTRS), 100)
        self.assertEqual(self.runtime.store.async_save.call_count, calls)

    async def test_silent_meter_expires_without_zero(self):
        self.runtime.active = True
        await self.process("100", 10)
        with patch("custom_components.solarshare.runtime.time.time", return_value=311):
            self.runtime._expire(None)
        await self.hass.async_block_till_done()
        self.assertFalse(self.runtime.ledger.available)
        self.assertEqual(self.runtime.ledger.total, Decimal("4.2"))


class FlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.temp.name)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        dr.async_setup(self.hass)
        await dr.async_load(self.hass)
        await er.async_load(self.hass)
        self.data = {"name": "Apartment 1", "meter": "sensor.meter", "max_power_kw": 25}
        self.hass.states.async_set("sensor.meter", "100", ATTRS)

    async def asyncTearDown(self):
        await self.hass.async_stop()
        self.temp.cleanup()

    async def test_user_setup_and_unavailable_meter(self):
        flow = SolarShareConfigFlow()
        flow.hass = self.hass
        result = await flow.async_step_user()
        self.assertEqual(result["type"], "form")
        self.hass.states.async_set("sensor.meter", "unavailable", ATTRS)
        result = await flow.async_step_user(self.data)
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["meter"], "sensor.meter")

    async def test_validation_duplicate_blank_and_non_cumulative(self):
        with patch.object(self.hass.config_entries, "async_entries", return_value=[entry()]):
            self.assertEqual(validate(self.hass, self.data), {"meter": "meter_assigned"})
            self.assertEqual(validate(self.hass, self.data, "apartment-1"), {})
        self.assertEqual(validate(self.hass, self.data | {"name": " "}), {"name": "empty_name"})
        self.hass.states.async_set("sensor.meter", "100", ATTRS | {"state_class": "measurement"})
        self.assertEqual(validate(self.hass, self.data), {"meter": "not_cumulative"})

    async def test_options_reassign_and_acknowledge(self):
        config_entry = entry()
        for acknowledge, meter, changed in (
            (False, "sensor.meter", False),
            (True, "sensor.meter", True),
            (False, "sensor.replacement", True),
        ):
            flow = SolarShareOptionsFlow()
            flow.hass = self.hass
            with (
                patch.object(
                    SolarShareOptionsFlow,
                    "config_entry",
                    new_callable=lambda: property(lambda _: config_entry),
                ),
                patch.object(self.hass.config_entries, "async_update_entry"),
            ):
                result = await flow.async_step_init(
                    self.data | {"meter": meter, "acknowledge": acknowledge}
                )
            self.assertEqual(result["type"], "create_entry")
            self.assertEqual(result["data"]["revision"] != "first", changed)

    async def test_paused_apartment_releases_assignment(self):
        old = entry()
        old.options = {"paused": True}
        with patch.object(self.hass.config_entries, "async_entries", return_value=[old]):
            self.assertEqual(validate(self.hass, self.data), {})
            old.options = {}
            self.assertEqual(validate(self.hass, self.data | {"paused": True}), {})


if __name__ == "__main__":
    unittest.main()
