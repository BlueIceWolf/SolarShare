"""Configure one complete installation and all apartments in a UI wizard."""

from copy import deepcopy
from uuid import uuid4

import probatio
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import DOMAIN
from .pv_sources import overlapping_growatt_totals, pv_entities, source_entities

ROLES = ("pv", "import", "export", "charge", "discharge")


def energy_selector(multiple=False):
    return selector.EntitySelector(
        selector.EntitySelectorConfig(
            filter={"domain": "sensor", "device_class": "energy"}, multiple=multiple
        )
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
    if overlapping_growatt_totals(sources.get("pv")):
        return "overlapping_pv_sources"
    if any(not sources.get(key) for key in ("pv", "import", "export")):
        return "missing_sources"
    if bool(sources.get("charge")) != bool(sources.get("discharge")):
        return "battery_pair"
    if not config["apartments"]:
        return "apartment_required"
    if any(not item["name"].strip() for item in config["apartments"]):
        return "empty_name"
    meters = source_entities(sources)
    meters += [item["meter"] for item in config["apartments"] if not item.get("paused")]
    if len(meters) != len(set(meters)):
        return "duplicate_meter"
    for meter in meters:
        if error := validate_source(hass, meter):
            return error
    details = pv_entities(config.get("pv_details"))
    if len(details) != len(set(details)):
        return "duplicate_meter"
    for meter in details:
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
                    "pv_measurement": "ac" if old.get("sources") else "unknown",
                    "pv_details": [],
                    "require_fresh_reports": False,
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

    def _errors(self, step):
        if getattr(self, "step_error", None) and self.step_error[0] == step:
            error = self.step_error[1]
            self.step_error = None
            return {"base": error}
        return {}

    def _meter_errors(self, updates):
        candidate = {**self.site["sources"], **updates}
        meters = source_entities(candidate)
        meters += [a["meter"] for a in self.site["apartments"] if not a.get("paused")]
        errors = {"base": "duplicate_meter"} if len(meters) != len(set(meters)) else {}
        if overlapping_growatt_totals(candidate.get("pv")):
            errors["pv" if "pv" in updates else "base"] = "overlapping_pv_sources"
        for key, value in updates.items():
            for meter in pv_entities(value):
                if error := validate_source(self.hass, meter):
                    errors[key] = error
        return errors

    def _meter_field(self, fields, key, current, *, multiple=False, required=True):
        marker = probatio.Required if required else probatio.Optional
        default = {"default": current} if current else {}
        fields[marker(key, **default)] = energy_selector(multiple=multiple)

    async def _after_section(self, next_step):
        if getattr(self, "edit_mode", False):
            return await self.async_step_site_menu()
        return await getattr(self, f"async_step_{next_step}")()

    async def async_step_installation(self, user_input=None):
        self._ensure_config()
        errors = self._errors("installation")
        if user_input is not None:
            if not user_input["name"].strip():
                errors["name"] = "empty_name"
            else:
                self.site["name"] = user_input["name"].strip()
                return await self._after_section("inverters")
        return self.async_show_form(
            step_id="installation",
            data_schema=probatio.Schema(
                {
                    probatio.Required("name", default=(user_input or self.site)["name"]): str,
                }
            ),
            errors=errors,
        )

    async def async_step_inverters(self, user_input=None):
        self._ensure_config()
        values = pv_entities(self.site["sources"].get("pv"))
        if getattr(self, "step_error", None) and self.step_error[0] == "inverters":
            self.step_error = ("inverter", self.step_error[1])
            self.pv_editing = values[0] if values else None
            return await self.async_step_inverter()
        if not values:
            return await self.async_step_add_inverter()
        return self.async_show_menu(
            step_id="inverters",
            description_placeholders={
                "count": str(len(values)),
                "inverters": "\n".join(f"- {self._entity_label(item)}" for item in values),
            },
            menu_options=["add_inverter", "select_inverter", "finish_inverters", "site_menu"],
        )

    async def async_step_add_inverter(self, user_input=None):
        self._ensure_config()
        self.pv_editing = None
        return await self.async_step_inverter()

    async def async_step_select_inverter(self, user_input=None):
        self._ensure_config()
        values = pv_entities(self.site["sources"].get("pv"))
        if not values:
            return await self.async_step_add_inverter()
        if user_input is not None:
            self.pv_editing = user_input["inverter_id"]
            return await self.async_step_inverter()
        return self.async_show_form(
            step_id="select_inverter",
            data_schema=probatio.Schema(
                {
                    probatio.Required("inverter_id"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": item, "label": self._entity_label(item)}
                                for item in values
                            ]
                        )
                    )
                }
            ),
        )

    async def async_step_inverter(self, user_input=None):
        self._ensure_config()
        current = getattr(self, "pv_editing", None)
        values = pv_entities(self.site["sources"].get("pv"))
        others = [value for value in values if value != current]
        errors = self._errors("inverter")
        if user_input is not None:
            if current and user_input.get("remove"):
                self.site["sources"]["pv"] = others
                self.pv_editing = None
                return await self.async_step_inverters()
            meter = user_input.get("pv", "")
            if not meter:
                errors["pv"] = "missing_sources"
            else:
                errors.update(self._meter_errors({"pv": [*others, meter]}))
            if others and user_input["pv_measurement"] != self.site["pv_measurement"]:
                errors["pv_measurement"] = "pv_boundary_mismatch"
            if not errors:
                self.site["sources"]["pv"] = [*others, meter]
                self.site["pv_measurement"] = user_input["pv_measurement"]
                self.pv_editing = None
                return await self.async_step_inverters()
        defaults = user_input or {"pv": current, "pv_measurement": self.site["pv_measurement"]}
        fields = {}
        self._meter_field(fields, "pv", defaults.get("pv"))
        fields[probatio.Required("pv_measurement", default=defaults["pv_measurement"])] = (
            selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=["ac", "dc", "unknown"], translation_key="pv_measurement"
                )
            )
        )
        if current:
            fields[probatio.Optional("remove", default=False)] = bool
        return self.async_show_form(
            step_id="inverter", data_schema=probatio.Schema(fields), errors=errors
        )

    async def async_step_finish_inverters(self, user_input=None):
        self._ensure_config()
        if not pv_entities(self.site["sources"].get("pv")):
            return await self.async_step_add_inverter()
        return await self._after_section("grid")

    async def async_step_grid(self, user_input=None):
        self._ensure_config()
        errors = self._errors("grid")
        if user_input is not None:
            updates = {key: user_input.get(key, "") for key in ("import", "export")}
            errors.update(self._meter_errors(updates))
            if not all(updates.values()):
                errors["base"] = "missing_sources"
            if not errors:
                self.site["sources"].update(updates)
                return await self._after_section("battery")
        defaults = user_input or self.site["sources"]
        fields = {}
        for key in ("import", "export"):
            self._meter_field(fields, key, defaults.get(key))
        return self.async_show_form(
            step_id="grid", data_schema=probatio.Schema(fields), errors=errors
        )

    async def async_step_battery(self, user_input=None):
        self._ensure_config()
        if user_input is not None:
            if user_input["has_battery"]:
                return await self.async_step_battery_meters()
            self.site["sources"].update({"charge": "", "discharge": ""})
            return await self._after_section("apartments")
        return self.async_show_form(
            step_id="battery",
            data_schema=probatio.Schema(
                {
                    probatio.Required(
                        "has_battery", default=bool(self.site["sources"].get("charge"))
                    ): bool,
                }
            ),
        )

    async def async_step_battery_meters(self, user_input=None):
        self._ensure_config()
        errors = self._errors("battery_meters")
        if user_input is not None:
            updates = {key: user_input.get(key, "") for key in ("charge", "discharge")}
            errors.update(self._meter_errors(updates))
            if not all(updates.values()):
                errors["base"] = "battery_pair"
            if not errors:
                self.site["sources"].update(updates)
                self.site["battery_capacity"] = user_input["battery_capacity"]
                return await self._after_section("apartments")
        defaults = user_input or {
            **self.site["sources"],
            "battery_capacity": self.site["battery_capacity"],
        }
        fields = {}
        for key in ("charge", "discharge"):
            self._meter_field(fields, key, defaults.get(key))
        fields[probatio.Required("battery_capacity", default=defaults["battery_capacity"])] = (
            selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.1,
                    max=1000,
                    step=0.1,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="kWh",
                )
            )
        )
        return self.async_show_form(
            step_id="battery_meters", data_schema=probatio.Schema(fields), errors=errors
        )

    async def async_step_pv_details(self, user_input=None):
        self._ensure_config()
        errors = self._errors("pv_details")
        if user_input is not None:
            details = pv_entities(user_input.get("pv_details"))
            if len(details) != len(set(details)):
                errors["pv_details"] = "duplicate_meter"
            for meter in details:
                if error := validate_source(self.hass, meter):
                    errors["pv_details"] = error
            if not errors:
                self.site["pv_details"] = details
                return await self.async_step_site_menu()
        fields = {}
        defaults = user_input or self.site
        self._meter_field(
            fields,
            "pv_details",
            pv_entities(defaults.get("pv_details")),
            multiple=True,
            required=False,
        )
        return self.async_show_form(
            step_id="pv_details", data_schema=probatio.Schema(fields), errors=errors
        )

    async def async_step_advanced(self, user_input=None):
        self._ensure_config()
        if user_input is not None:
            self.site.update(user_input)
            return await self.async_step_site_menu()
        fields = {}
        for key, lower, upper in (("max_power_kw", 1, 1000), ("alignment_seconds", 1, 120)):
            fields[probatio.Required(key, default=self.site[key])] = selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=lower, max=upper, step=1, mode=selector.NumberSelectorMode.BOX
                )
            )
        fields[probatio.Optional("acknowledge", default=self.site.get("acknowledge", False))] = bool
        fields[
            probatio.Optional("require_fresh_reports", default=self.site["require_fresh_reports"])
        ] = bool
        return self.async_show_form(step_id="advanced", data_schema=probatio.Schema(fields))

    async def async_step_site_menu(self, user_input=None):
        self._ensure_config()
        self.edit_mode = True
        return self.async_show_menu(
            step_id="site_menu",
            description_placeholders={"name": self.site["name"]},
            menu_options=[
                "installation",
                "inverters",
                "grid",
                "battery",
                "apartments",
                "pv_details",
                "advanced",
                "finish",
            ],
        )

    async def async_step_apartments(self, user_input=None):
        self._ensure_config()
        return self.async_show_menu(
            step_id="apartments",
            description_placeholders={
                "apartments": ", ".join(item["name"] for item in self.site["apartments"]) or "—"
            },
            menu_options=["add_apartment", "select_apartment", "finish", "site_menu"],
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
                data["meter"] in source_entities(self.site["sources"])
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

    def _entity_label(self, entity_id):
        state = self.hass.states.get(entity_id) if entity_id else None
        return state.attributes.get("friendly_name", entity_id) if state else (entity_id or "—")

    async def async_step_finish(self, user_input=None):
        self._ensure_config()
        if not self.site["apartments"]:
            return await self.async_step_add_apartment()
        sources = self.site["sources"]
        pv = pv_entities(sources.get("pv"))
        apartments = self.site["apartments"]
        return self.async_show_menu(
            step_id="finish",
            menu_options=["save", "site_menu"],
            description_placeholders={
                "name": self.site["name"],
                "pv_count": str(len(pv)),
                "pv": "\n".join(f"- {self._entity_label(item)}" for item in pv) or "—",
                "pv_measurement": {"ac": "AC", "dc": "DC", "unknown": "?"}[
                    self.site["pv_measurement"]
                ],
                "grid_import": self._entity_label(sources.get("import")),
                "grid_export": self._entity_label(sources.get("export")),
                "battery": " / ".join(
                    self._entity_label(sources.get(key)) for key in ("charge", "discharge")
                ),
                "apartment_count": str(len(apartments)),
                "apartments": "\n".join(
                    f"- {item['name']}{' ⏸' if item.get('paused') else ''}: {self._entity_label(item['meter'])}"
                    for item in apartments
                ),
                "detail_count": str(len(self.site["pv_details"])),
            },
        )

    async def async_step_save(self, user_input=None):
        self._ensure_config()
        entry = getattr(self, "config_entry", None)
        if error := validate_config(self.hass, self.site, entry.entry_id if entry else None):
            if error == "apartment_required":
                return await self.async_step_add_apartment()
            if error == "single_site":
                return self.async_abort(reason="single_site")
            target = "battery_meters" if error == "battery_pair" else "inverters"
            if error == "missing_sources" and self.site["sources"].get("pv"):
                target = "grid"
            if error == "empty_name":
                target = "installation"
            self.step_error = (target, error)
            self.edit_mode = True
            return await getattr(self, f"async_step_{target}")()
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
                or data.get("pv_measurement") != old.get("pv_measurement", "ac")
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
        self._ensure_config()
        if self.converting:
            return await self.async_step_installation(user_input)
        return await self.async_step_site_menu(user_input)
