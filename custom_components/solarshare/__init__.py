"""SolarShare apartment energy monitoring."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .runtime import SolarShareRuntime
from .site_runtime import SiteRuntime

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Load durable totals before exposing sensors or listening for readings."""
    config = {**entry.data, **entry.options}
    runtime = SiteRuntime(hass, entry) if "sources" in config else SolarShareRuntime(hass, entry)
    await runtime.async_load()
    entry.runtime_data = runtime
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
