"""Real HA boundary tests for installation setup, migration and generated points."""

import tempfile
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.solarshare.site_flow import SolarShareConfigFlow, SolarShareOptionsFlow
from custom_components.solarshare.site_runtime import SiteRuntime
from custom_components.solarshare.site_sensor import EnergyPoint, entities

ATTRS = {"device_class": "energy", "state_class": "total_increasing", "unit_of_measurement": "kWh"}


class InstallationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.temp.name)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        dr.async_setup(self.hass)
        await dr.async_load(self.hass)
        await er.async_load(self.hass)
        for name in ("pv", "import", "export", "a", "b"):
            self.hass.states.async_set(f"sensor.{name}", "100", ATTRS)
        self.settings = {
            "name": "Haus",
            "pv": "sensor.pv",
            "import": "sensor.import",
            "export": "sensor.export",
            "max_power_kw": 100,
            "alignment_seconds": 60,
            "battery_capacity": 10,
        }

    async def asyncTearDown(self):
        await self.hass.async_stop()
        self.temp.cleanup()

    async def configured_flow(self):
        flow = SolarShareConfigFlow()
        flow.hass = self.hass
        self.assertEqual((await flow.async_step_user())["step_id"], "installation")
        self.assertEqual(
            (await flow.async_step_installation({"name": "Haus"}))["step_id"], "inverter"
        )
        self.assertEqual(
            (await flow.async_step_inverter({"pv": "sensor.pv", "pv_measurement": "ac"}))[
                "step_id"
            ],
            "inverters",
        )
        self.assertEqual((await flow.async_step_finish_inverters())["step_id"], "grid")
        self.assertEqual(
            (await flow.async_step_grid({"import": "sensor.import", "export": "sensor.export"}))[
                "step_id"
            ],
            "battery",
        )
        self.assertEqual(
            (await flow.async_step_battery({"has_battery": False}))["step_id"], "apartments"
        )
        for apartment in ("a", "b"):
            await flow.async_step_add_apartment()
            await flow.async_step_apartment({"name": apartment, "meter": f"sensor.{apartment}"})
        return flow

    async def test_setup_creates_one_installation_with_two_apartments(self):
        flow = await self.configured_flow()
        review = await flow.async_step_finish()
        self.assertEqual(review["type"], "menu")
        self.assertIn("save", review["menu_options"])
        result = await flow.async_step_save()
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(len(result["data"]["apartments"]), 2)
        self.assertEqual(result["data"]["sources"]["pv"], ["sensor.pv"])

    async def test_duplicate_meter_and_unpaired_battery_rejected(self):
        flow = await self.configured_flow()
        await flow.async_step_add_apartment()
        result = await flow.async_step_apartment({"name": "duplicate", "meter": "sensor.a"})
        self.assertEqual(result["errors"], {"meter": "duplicate_meter"})
        result = await flow.async_step_battery_meters(
            {"charge": "sensor.charge", "battery_capacity": 10}
        )
        self.assertEqual(result["errors"]["base"], "battery_pair")

    async def test_options_conversion_retains_old_apartment_identity(self):
        old = SimpleNamespace(
            entry_id="old",
            data={"name": "Altwohnung", "meter": "sensor.a", "max_power_kw": 25, "revision": "old"},
            options={},
        )
        flow = SolarShareOptionsFlow()
        flow.hass = self.hass
        with patch.object(SolarShareOptionsFlow, "config_entry", property(lambda _: old)):
            result = await flow.async_step_init()
            self.assertEqual(result["step_id"], "installation")
            self.assertEqual(flow.site["apartments"][0]["id"], "old")
            self.assertEqual(flow.site["apartments"][0]["meter"], "sensor.a")

    async def test_devices_points_and_apartment_autarky(self):
        flow = await self.configured_flow()
        config = (await flow.async_step_save())["data"]
        entry = SimpleNamespace(
            entry_id="site", data=config | {"site_ledger_initialized": True}, options={}
        )
        runtime = SiteRuntime(self.hass, entry)
        entry.runtime_data = runtime
        runtime.store = AsyncMock()
        runtime.store.async_load.return_value = {
            "ledger": runtime.ledger.snapshot(),
            "revision": config["revision"],
            "identities": {},
            "legacy_total": "3.2",
        }
        await runtime.async_load()
        all_entities = entities(entry)
        self.assertEqual(len(all_entities), 89)
        self.assertEqual(len({entity.unique_id for entity in all_entities}), 89)
        apartment = config["apartments"][0]
        point = EnergyPoint(entry, "autarky", "day", apartment)
        self.assertFalse(point.available)
        from homeassistant.util import dt as dt_util

        day = dt_util.now().date().isoformat()
        initial = dict.fromkeys(runtime.ledger.required, Decimal(100))
        runtime.ledger.observe(initial, dict.fromkeys(initial, 10), 10, day)
        changed = dict(initial)
        changed["pv"] += Decimal(".4")
        changed["import"] += Decimal(".6")
        changed[f"apt:{apartment['id']}"] += Decimal(1)
        runtime.ledger.observe(changed, dict.fromkeys(changed, 70), 70, day)
        self.assertTrue(point.available)
        self.assertEqual(point.native_value, Decimal(40))
        runtime.ledger.interrupt("source_unavailable")
        self.assertFalse(point.available)

    async def test_meter_edit_keeps_apartment_id(self):
        flow = await self.configured_flow()
        original = flow.site["apartments"][0]["id"]
        await flow.async_step_select_apartment({"apartment_id": original})
        await flow.async_step_apartment({"name": "Umbenannt", "meter": "sensor.a"})
        self.assertIn(original, [item["id"] for item in flow.site["apartments"]])

    async def test_monitoring_string_does_not_join_building_balance(self):
        flow = await self.configured_flow()
        config = (await flow.async_step_save())["data"]
        config["pv_details"] = ["sensor.string2"]
        entry = SimpleNamespace(entry_id="site", data=config, options={})
        runtime = SiteRuntime(self.hass, entry)
        detail_key = "pv_detail:sensor.string2"
        self.assertIn(detail_key, runtime.meters)
        self.assertNotIn(detail_key, runtime.ledger.required)
        self.assertNotIn(detail_key, runtime.accounting_keys)
        runtime.active = True
        runtime.ledger.available = True
        runtime._changed(SimpleNamespace(data={"entity_id": "sensor.string2", "new_state": None}))
        self.assertTrue(runtime.ledger.available)

    async def test_three_inverters_and_battery_branch(self):
        flow = SolarShareConfigFlow()
        flow.hass = self.hass
        await flow.async_step_installation({"name": "Haus"})
        inverters = ["sensor.pv", "sensor.pv2", "sensor.pv3"]
        for inverter in inverters:
            await flow.async_step_add_inverter()
            result = await flow.async_step_inverter({"pv": inverter, "pv_measurement": "ac"})
            self.assertEqual(result["step_id"], "inverters")
        self.assertEqual(result["description_placeholders"]["count"], "3")
        result = await flow.async_step_finish_inverters()
        self.assertEqual(result["step_id"], "grid")
        await flow.async_step_grid({"import": "sensor.import", "export": "sensor.export"})
        result = await flow.async_step_battery({"has_battery": True})
        self.assertEqual(result["step_id"], "battery_meters")
        result = await flow.async_step_battery_meters(
            {"charge": "sensor.charge", "discharge": "sensor.discharge", "battery_capacity": 10}
        )
        self.assertEqual(result["step_id"], "apartments")
        await flow.async_step_add_apartment()
        await flow.async_step_apartment({"name": "Wohnung", "meter": "sensor.a"})
        result = await flow.async_step_finish()
        self.assertEqual(result["description_placeholders"]["pv_count"], "3")
        self.assertEqual(flow.site["pv_details"], [])

    async def test_edit_section_preserves_other_assignments(self):
        flow = await self.configured_flow()
        old_sources = dict(flow.site["sources"])
        old_ids = [item["id"] for item in flow.site["apartments"]]
        await flow.async_step_site_menu()
        result = await flow.async_step_installation({"name": "Neuer Name"})
        self.assertEqual(result["step_id"], "site_menu")
        self.assertEqual(flow.site["sources"], old_sources)
        self.assertEqual([item["id"] for item in flow.site["apartments"]], old_ids)

    async def test_restart_with_unavailable_night_pv_and_live_grid(self):
        flow = await self.configured_flow()
        config = (await flow.async_step_save())["data"]
        entry = SimpleNamespace(
            entry_id="site", data=config | {"site_ledger_initialized": True}, options={}
        )
        runtime = SiteRuntime(self.hass, entry)
        runtime.store = AsyncMock()
        self.hass.states.async_set("sun.sun", "below_horizon")
        self.hass.states.async_set("sensor.pv", "unavailable", ATTRS)
        with patch("custom_components.solarshare.site_runtime.time.time", return_value=10):
            await runtime._sample()
        self.assertEqual(runtime.night.sleeping, frozenset({"pv"}))
        self.assertIsNone(runtime.readings["pv"])
        self.hass.states.async_set("sensor.import", "100.1", ATTRS)
        self.hass.states.async_set("sensor.a", "100.1", ATTRS)
        with patch("custom_components.solarshare.site_runtime.time.time", return_value=70):
            await runtime._sample()
        self.assertTrue(runtime.ledger.available)
        self.assertEqual(runtime.ledger.reason, "observing_pv_night")
        self.assertEqual(runtime.ledger.totals()["site"]["pv"], 0)
        self.hass.states.async_set("sun.sun", "above_horizon")
        with patch("custom_components.solarshare.site_runtime.time.time", return_value=130):
            await runtime._sample()
        self.assertFalse(runtime.ledger.available)
        self.assertFalse(runtime.night.sleeping)

    async def test_restored_sun_is_not_confirmed_night(self):
        flow = await self.configured_flow()
        config = (await flow.async_step_save())["data"]
        runtime = SiteRuntime(self.hass, SimpleNamespace(entry_id="site", data=config, options={}))
        self.hass.states.async_set("sun.sun", "below_horizon", {"restored": True})
        self.assertIsNone(runtime._sun_state())
