"""SolarShare apartment energy monitoring."""

from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN

from .runtime import SolarShareRuntime
from .site_runtime import SiteRuntime

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Load durable totals before exposing sensors or listening for readings."""
    config = {**entry.data, **entry.options}
    runtime = SiteRuntime(hass, entry) if "sources" in config else SolarShareRuntime(hass, entry)
    await runtime.async_load()
    entry.runtime_data = runtime
    if "sources" in config:
        # Publish the card once per Home Assistant process; reloading the entry
        # must not try to register an existing HTTP route again.
        if not hass.data.get("_solarshare_card_registered"):
            await hass.http.async_register_static_paths([
                StaticPathConfig(
                    "/solarshare/solarshare-card.js",
                    str(Path(__file__).parent / "www" / "solarshare-card.js"),
                    False,
                )
            ])
            hass.data["_solarshare_card_registered"] = True
        # Register the parent before adding apartment devices. Home Assistant's
        # via_device_id expects a registry ID, not an identifier tuple.
        site_device = dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, entry.entry_id)},
            name=config["name"],
            manufacturer="SolarShare",
            model="Energieanlage",
        )
        runtime.site_device_id = site_device.id
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    runtime.async_start()
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Retain v0.1 apartment data until the user maps the building sources."""
    if entry.version == 1:
        hass.config_entries.async_update_entry(entry, version=2)
    return entry.version == 2


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry):
    """Reload to atomically change an assignment and discard the old baseline."""
    if dict(entry.options) != entry.runtime_data.options:
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Stop incoming work, drain pending writes, then unload sensors."""
    runtime = entry.runtime_data
    await runtime.async_stop()
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unloaded:
        runtime.async_start()
    return unloaded
