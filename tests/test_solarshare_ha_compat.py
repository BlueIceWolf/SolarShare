"""Local-only regression tests for SolarShare's HA compatibility and card registration.

Run: python -m unittest tests.test_solarshare_ha_compat -v
No Home Assistant install, GitHub Actions, or live meter data required.
"""

import ast
import asyncio
import copy
import logging
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "solarshare"


def extract(source_file, function_name, class_name=None):
    tree = ast.parse((ROOT / source_file).read_text(encoding="utf-8"))
    body = tree.body
    if class_name:
        container = next(node for node in body if isinstance(node, ast.ClassDef) and node.name == class_name)
        method = next(node for node in container.body if isinstance(node, ast.FunctionDef) and node.name == function_name)
        container = copy.deepcopy(container)
        container.body = [copy.deepcopy(method)]
        body = [container]
    else:
        body = [copy.deepcopy(next(node for node in body if isinstance(node, ast.AsyncFunctionDef) and node.name == function_name))]
    return compile(ast.fix_missing_locations(ast.Module(body=body, type_ignores=[])), str(ROOT / source_file), "exec")


class DeviceLinkTests(unittest.TestCase):
    def test_existing_device_ids_and_parent_registry_link(self):
        class SensorEntity:
            pass

        namespace = {"SensorEntity": SensorEntity, "DeviceInfo": lambda **kwargs: kwargs, "DOMAIN": "solarshare"}
        exec(extract("site_sensor.py", "__init__", "SiteEntity"), namespace)
        SiteEntity = namespace["SiteEntity"]

        class Registry:
            def __init__(self):
                self.device = SimpleNamespace(id="actual-registry-id")
                self.created = []

            def async_get_or_create(self, **kwargs):
                self.created.append(kwargs)
                return self.device

        registry = Registry()

        class Runtime:
            def __init__(self, hass, entry):
                self.config = {"name": "SolarShare"}
                self.loaded = False

            async def async_load(self):
                self.loaded = True

            def async_start(self):
                pass

        entry = SimpleNamespace(entry_id="existing-entry", data={"name": "SolarShare", "sources": {}}, options={})
        entry.add_update_listener = lambda fn: fn
        entry.async_on_unload = lambda fn: None

        async def forward(entry_value, platforms):
            self.assertEqual(entry_value.runtime_data.site_device_id, "actual-registry-id")
            apartment = SiteEntity(entry_value, "test", "Verbrauch", {"id": "old-flat-id", "name": "Wohnung 1"})
            self.assertEqual(apartment._attr_unique_id, "existing-entry_test")
            self.assertEqual(
                apartment._attr_device_info["identifiers"],
                {("solarshare", "existing-entry_old-flat-id")},
            )
            self.assertEqual(apartment._attr_device_info["via_device_id"], "actual-registry-id")
            self.assertNotIn("via_device", apartment._attr_device_info)

        hass = SimpleNamespace(config_entries=SimpleNamespace(async_forward_entry_setups=forward))
        ns = {
            "HomeAssistant": object, "ConfigEntry": object, "SiteRuntime": Runtime,
            "SolarShareRuntime": Runtime, "dr": SimpleNamespace(async_get=lambda ha: registry),
            "DOMAIN": "solarshare", "PLATFORMS": ["sensor"],
            "async_update_options": lambda *a: None,
        }
        exec(extract("__init__.py", "async_setup_entry"), ns)
        self.assertTrue(asyncio.run(ns["async_setup_entry"](hass, entry)))
        self.assertEqual(registry.created[0]["identifiers"], {("solarshare", "existing-entry")})


class ResourceRegistrationTests(unittest.TestCase):
    class Resources:
        def __init__(self, rows):
            self.loaded = False
            self._initial = [dict(r) for r in rows]
            self.rows = []
            self.load_calls = 0
            self.created = 0
            self.updated = 0

        async def async_load(self):
            self.load_calls += 1
            self.rows = [dict(r) for r in self._initial]
            self.loaded = True

        def async_items(self):
            if not self.loaded:
                raise AssertionError("Read of unloaded resource storage")
            return list(self.rows)

        async def async_create_item(self, data):
            if not self.loaded:
                raise AssertionError("Creation before resource storage load")
            self.created += 1
            self.rows.append({"id": str(len(self.rows) + 1), **data})

        async def async_update_item(self, id_, update):
            if not self.loaded:
                raise AssertionError("Update before resource storage load")
            self.updated += 1
            next(row for row in self.rows if row["id"] == id_).update(update)

    def register(self, rows, mode="storage", repeat=False):
        resources = self.Resources(rows)
        hass = SimpleNamespace(data={"lovelace": SimpleNamespace(resource_mode=mode, resources=resources)})

        async def get_integration(hass_, domain):
            self.assertEqual(domain, "solarshare")
            return SimpleNamespace(version="0.3.1")

        ns = {
            "HomeAssistant": object, "DOMAIN": "solarshare",
            "CARD_PATH": "/solarshare/solarshare-card.js",
            "_LOGGER": logging.getLogger(__name__),
            "async_get_integration": get_integration, "urlsplit": urlsplit,
        }
        exec(extract("frontend_resources.py", "async_register_card_resource"), ns)
        asyncio.run(ns["async_register_card_resource"](hass))
        if repeat:
            asyncio.run(ns["async_register_card_resource"](hass))
        return resources

    def test_register_once_and_preserve_existing_resources(self):
        unrelated = {"id": "other", "url": "/hacsfiles/another-card/card.js", "res_type": "module"}
        resources = self.register([unrelated], repeat=True)
        self.assertEqual(resources.load_calls, 1)
        self.assertEqual(resources.created, 1)
        self.assertEqual(resources.updated, 0)
        self.assertEqual(resources.rows[0], unrelated)
        self.assertEqual(resources.rows[1]["url"], "/solarshare/solarshare-card.js?v=0.3.1")

    def test_update_legacy_unversioned_resource_in_place(self):
        initial = [{"id": "old", "url": "/solarshare/solarshare-card.js", "res_type": "module"}]
        resources = self.register(initial, repeat=True)
        self.assertEqual(resources.created, 0)
        self.assertEqual(resources.updated, 1)
        self.assertEqual(resources.rows[0]["id"], "old")
        self.assertEqual(resources.rows[0]["url"], "/solarshare/solarshare-card.js?v=0.3.1")

    def test_skip_yaml_resource_mode(self):
        resources = self.register([], mode="yaml")
        self.assertEqual(resources.load_calls, 0)
        self.assertEqual(resources.created, 0)


if __name__ == "__main__":
    unittest.main()
