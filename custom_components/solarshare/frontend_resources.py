"""Expose and register the SolarShare card without touching unrelated resources."""

import logging
from pathlib import Path
from urllib.parse import urlsplit

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
CARD_PATH = "/solarshare/solarshare-card.js"
CARD_FILE = Path(__file__).parent / "www" / "solarshare-card.js"


async def async_register_card_path(hass: HomeAssistant) -> None:
    """Serve the bundled card once, without using configuration/www."""
    if hass.data.get("_solarshare_card_path_registered"):
        return
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_PATH, str(CARD_FILE), False)]
    )
    hass.data["_solarshare_card_path_registered"] = True


async def async_register_card_resource(hass: HomeAssistant) -> None:
    """Install/update exactly our resource in Lovelace storage mode.

    Never modify YAML-managed resources, and never inspect an unloaded
    storage collection: doing so can overwrite unrelated dashboard resources.
    """
    lovelace = hass.data.get("lovelace")
    if lovelace is None:
        _LOGGER.info("Lovelace not loaded; SolarShare card resource can be added manually")
        return
    if lovelace.resource_mode != "storage":
        _LOGGER.info("Lovelace resources are YAML-managed; skipping auto-registration")
        return

    resources = lovelace.resources
    if not resources.loaded:
        await resources.async_load()
    integration = await async_get_integration(hass, DOMAIN)
    url = f"{CARD_PATH}?v={integration.version}"
    existing = [
        item for item in resources.async_items()
        if urlsplit(item["url"]).path == CARD_PATH
    ]
    if existing:
        # Reuse the existing resource rather than creating a duplicate. This
        # also migrates a manually installed unversioned resource.
        current = existing[0]
        if current["url"] != url or current["res_type"] != "module":
            await resources.async_update_item(
                current["id"], {"url": url, "res_type": "module"}
            )
            _LOGGER.info("Updated bundled SolarShare dashboard resource")
        if len(existing) > 1:
            _LOGGER.warning(
                "Found %s SolarShare card resources; kept existing entries to avoid"
                " deleting a user-managed resource. Remove duplicates manually.",
                len(existing),
            )
        return
    await resources.async_create_item({"url": url, "res_type": "module"})
    _LOGGER.info("Registered bundled SolarShare dashboard card")
