"""Configure one complete installation and all apartments in a UI wizard."""

from copy import deepcopy
from uuid import uuid4

import probatio
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import DOMAIN

ROLES = ("pv", "import", "export", "charge", "discharge")


def energy_selector():
    return selector.EntitySelector(
        selector.EntitySelectorConfig(filter={"domain": "sensor", "device_class": "energy"})
    )


def validate_source(hass, entity_id):
    source = er.async_get(hass).async_get(entity_id)
    if source and source.platform == DOMAIN:
        return "recursive_meter"
    state = hass.states.get(entity_id)
    if state and state.state not in ("unknown", "unavailable"):
        if state.attributes.get("device_class") != "energy" or state.attributes.get(
            "state_class"
        ) not in ("total", "total_increasing"):
            return "not_cumulative"
        if state.attributes.get("unit_of_measurement") not in ("Wh", "kWh", "MWh"):
            return "unsupported_unit"
    return None


def validate_config(hass, config, entry_id=None):
    if not config["name"].strip():
        return "empty_name"
    sources = config["sources"]
    if any(not sources.get(key) for key in ("pv", "import", "export")):
        return "missing_sources"
    if bool(sources.get("charge")) != bool(sources.get("discharge")):
        return "battery_pair"
    if not config["apartments"]:
        return "apartment_required"
    if any(not item["name"].strip() for item in config["apartments"]):
        return "empty_name"
    meters = [value for value in sources.values() if value]
    meters += [item["meter"] for item in config["apartments"] if not item.get("paused")]
    if len(meters) != len(set(meters)):
        return "duplicate_meter"
    for meter in meters:
        if error := validate_source(hass, meter):
            return error
    for entry in hass.config_entries.async_entries(DOMAIN):
        other = {**entry.data, **entry.options}
        if entry.entry_id != entry_id and "sources" in other:
            return "single_site"
    return None


class InstallationWizard:
    def _ensure_config(self):
        if hasattr(self, "site"):
            return
        entry = getattr(self, "config_entry", None)
        old = {**entry.data, **entry.options} if entry else {}
        self.site = deepcopy(
            {
                key: old.get(key, default)
                for key, default in {
                    "name": "SolarShare",
                    "sources": {},
                    "apartments": [],
                    "max_power_kw": 100,
                    "alignment_seconds": 60,
                    "battery_capacity": 10,
                    "revision": uuid4().hex,
                }.items()
            }
        )
        self.converting = bool(entry and "sources" not in old)
        if self.converting:
            self.site["name"] = "SolarShare"
            self.site["max_power_kw"] = 100
            self.site["apartments"] = [
                {"id": entry.entry_id, "name": old["name"], "meter": old["meter"], "paused": False}
            ]
        self.editing = None

    async def async_step_installation(self, user_input=None):
        self._ensure_config()
        errors = {"base": self.pending_error} if getattr(self, "pending_error", None) else {}
        self.pending_error = None
        if user_input is not None:
            sources = {key: user_input.get(key, "") for key in ROLES}
            if not user_input["name"].strip():
                errors["name"] = "empty_name"
            elif bool(sources["charge"]) != bool(sources["discharge"]):
                errors["base"] = "battery_pair"
            else:
                used = [meter for meter in sources.values() if meter]
                if len(used) != len(set(used)):
                    errors["base"] = "duplicate_meter"
                for key, meter in sources.items():
                    if meter and (error := validate_source(self.hass, meter)):
                        errors[key] = error
            if not errors:
                self.site.update(
                    {key: value for key, value in user_input.items() if key not in ROLES}
                )
                self.site["sources"] = sources
                return await self.async_step_apartments()
        defaults = user_input or {**self.site, **self.site["sources"]}
        fields = {probatio.Required("name", default=defaults.get("name", "SolarShare")): str}
        for key in ROLES:
            field = probatio.Required if key in ("pv", "import", "export") else probatio.Optional
            kwargs = {"default": defaults[key]} if defaults.get(key) else {}
            fields[field(key, **kwargs)] = energy_selector()
        for key, lower, upper, step in (
            ("max_power_kw", 1, 1000, 1),
            ("alignment_seconds", 1, 120, 1),
            ("battery_capacity", 0.1, 1000, 0.1),
        ):
            fields[probatio.Required(key, default=defaults[key])] = selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=lower, max=upper, step=step, mode=selector.NumberSelectorMode.BOX
                )
            )
        fields[probatio.Optional("acknowledge", default=False)] = bool
        return self.async_show_form(
            step_id="installation", data_schema=probatio.Schema(fields), errors=errors
        )

    async def async_step_apartments(self, user_input=None):
        self._ensure_config()
        return self.async_show_menu(
            step_id="apartments",
            description_placeholders={
                "apartments": ", ".join(item["name"] for item in self.site["apartments"]) or "—"
            },
            menu_options=["add_apartment", "select_apartment", "installation", "finish"],
        )

    async def async_step_add_apartment(self, user_input=None):
        self._ensure_config()
        self.editing = None
        return await self.async_step_apartment()

    async def async_step_select_apartment(self, user_input=None):
        self._ensure_config()
        if not self.site["apartments"]:
            return await self.async_step_add_apartment()
        if user_input is not None:
            self.editing = user_input["apartment_id"]
            return await self.async_step_apartment()
        return self.async_show_form(
            step_id="select_apartment",
            data_schema=probatio.Schema(
                {
                    probatio.Required("apartment_id"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": item["id"], "label": item["name"]}
                                for item in self.site["apartments"]
                            ]
                        )
                    )
                }
            ),
        )

    async def async_step_apartment(self, user_input=None):
        self._ensure_config()
        current = next((item for item in self.site["apartments"] if item["id"] == self.editing), {})
        errors = {}
        if user_input is not None:
            data = {
                "id": current.get("id", uuid4().hex),
                "name": user_input["name"].strip(),
                "meter": user_input["meter"],
                "paused": user_input.get("paused", False),
            }
            if user_input.get("remove"):
                self.site["apartments"] = [
                    item for item in self.site["apartments"] if item["id"] != data["id"]
                ]
                return await self.async_step_apartments()
            if not data["name"]:
                errors["name"] = "empty_name"
            elif error := validate_source(self.hass, data["meter"]):
                errors["meter"] = error
            elif not data["paused"] and (
                data["meter"] in self.site["sources"].values()
                or any(
                    item["id"] != data["id"]
                    and not item.get("paused")
                    and item["meter"] == data["meter"]
                    for item in self.site["apartments"]
                )
            ):
                errors["meter"] = "duplicate_meter"
            if not errors:
                self.site["apartments"] = [
                    item for item in self.site["apartments"] if item["id"] != data["id"]
                ] + [data]
                return await self.async_step_apartments()
        defaults = user_input or current
        fields = {
            probatio.Required("name", default=defaults.get("name", "")): str,
            probatio.Required(
                "meter", **({"default": defaults["meter"]} if defaults.get("meter") else {})
            ): energy_selector(),
            probatio.Optional("paused", default=defaults.get("paused", False)): bool,
        }
        if current:
            fields[probatio.Optional("remove", default=False)] = bool
        return self.async_show_form(
            step_id="apartment", data_schema=probatio.Schema(fields), errors=errors
        )

    async def async_step_finish(self, user_input=None):
        self._ensure_config()
        entry = getattr(self, "config_entry", None)
        if error := validate_config(self.hass, self.site, entry.entry_id if entry else None):
            if error == "apartment_required":
                return await self.async_step_add_apartment()
            self.pending_error = error
            return await self.async_step_installation()
        data = deepcopy(self.site)
        acknowledge = data.pop("acknowledge", False)
        if acknowledge:
            data["review_token"] = uuid4().hex
        elif entry:
            old_config = {**entry.data, **entry.options}
            if "review_token" in old_config:
                data["review_token"] = old_config["review_token"]
        if entry:
            old = {**entry.data, **entry.options}
            if (
                acknowledge
                or data["sources"] != old.get("sources")
                or sorted((a["id"], a["meter"], a.get("paused", False)) for a in data["apartments"])
                != sorted(
                    (a["id"], a["meter"], a.get("paused", False)) for a in old.get("apartments", [])
                )
            ):
                data["revision"] = uuid4().hex
            self.hass.config_entries.async_update_entry(entry, title=data["name"])
        return self.async_create_entry(title="" if entry else data["name"], data=data)


class SolarShareConfigFlow(InstallationWizard, config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    async def async_step_user(self, user_input=None):
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if "sources" in {**entry.data, **entry.options}:
                return self.async_abort(reason="single_site")
        return await self.async_step_installation(user_input)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SolarShareOptionsFlow()


class SolarShareOptionsFlow(InstallationWizard, config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        return await self.async_step_installation(user_input)
