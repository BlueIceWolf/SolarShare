"""SolarShare apartment energy monitoring."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .frontend_resources import async_register_card_path, async_register_card_resource
from .runtime import SolarShareRuntime
from .site_runtime import SiteRuntime

PLATFORMS = [Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Serve and register the card before the dashboard can be opened.

    Lovelace and HTTP are hard dependencies, so both are initialized first.
    Registration is idempotent: upgrades do not create a duplicate resource.
    """
    try:
        await async_register_card_path(hass)
    except Exception:
        _LOGGER.exception("Unable to serve the bundled SolarShare card")

    try:
        await async_register_card_resource(hass)
    except Exception:
        _LOGGER.exception(
            "Unable to register SolarShare dashboard resource automatically; "
            "check Dashboard > Resources for /solarshare/solarshare-card.js"
        )
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Load durable totals before exposing sensors or listening for readings."""
    config = {**entry.data, **entry.options}
    runtime = SiteRuntime(hass, entry) if "sources" in config else SolarShareRuntime(hass, entry)
    await runtime.async_load()
    entry.runtime_data = runtime
    # Recover from an earlier frontend registration error during setup.
    # This never alters stored energy data or creates duplicate resources.
    if not hass.data.get("_solarshare_card_resource_registered"):
        try:
            await async_register_card_path(hass)
            await async_register_card_resource(hass)
        except Exception:
            _LOGGER.exception("SolarShare card could not be auto-registered")
    if "sources" in config:
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
