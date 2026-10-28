"""UI setup: one stable entry per apartment, with editable meter assignment."""

from uuid import uuid4

import probatio
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import CONF_MAX_POWER, CONF_METER, CONF_REVISION, DOMAIN


def schema(defaults):
    """Allow temporarily absent entities by not validating their current state."""
    return probatio.Schema(
        {
            probatio.Required("name", default=defaults.get("name", "")): str,
            probatio.Required(
                CONF_METER, default=defaults.get(CONF_METER, "")
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="energy")
            ),
            probatio.Required(
                CONF_MAX_POWER, default=defaults.get(CONF_MAX_POWER, 25)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.1,
                    max=1000,
                    step=0.1,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="kW",
                )
            ),
        }
    )


def validate(hass, data, entry_id=None):
    """Reject duplicate assignment, empty names and recursive SolarShare sources."""
    from homeassistant.helpers import entity_registry as er

    if not data["name"].strip():
        return {"name": "empty_name"}
    for entry in hass.config_entries.async_entries(DOMAIN):
        if (
            not data.get("paused")
            and not entry.options.get("paused")
            and entry.entry_id != entry_id
            and entry.options.get(CONF_METER, entry.data.get(CONF_METER)) == data[CONF_METER]
        ):
            return {CONF_METER: "meter_assigned"}
    registry_entry = er.async_get(hass).async_get(data[CONF_METER])
    if registry_entry and registry_entry.platform == DOMAIN:
        return {CONF_METER: "recursive_meter"}
    state = hass.states.get(data[CONF_METER])
    if state and state.state not in ("unknown", "unavailable"):
        if state.attributes.get("device_class") != "energy" or state.attributes.get(
            "state_class"
        ) not in ("total", "total_increasing"):
            return {CONF_METER: "not_cumulative"}
        if state.attributes.get("unit_of_measurement") not in ("Wh", "kWh", "MWh"):
            return {CONF_METER: "unsupported_unit"}
    return {}


class SolarShareConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Add another apartment using Add integration again."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            errors = validate(self.hass, user_input)
            if not errors:
                user_input = {
                    **user_input,
                    "name": user_input["name"].strip(),
                    CONF_REVISION: uuid4().hex,
                }
                return self.async_create_entry(title=user_input["name"], data=user_input)
        return self.async_show_form(
            step_id="user", data_schema=schema(user_input or {}), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SolarShareOptionsFlow()


class SolarShareOptionsFlow(config_entries.OptionsFlow):
    """Keep the apartment identity and total when editing/replacing its meter."""

    async def async_step_init(self, user_input=None):
        defaults = {**self.config_entry.data, **self.config_entry.options}
        errors = {}
        if user_input is not None:
            errors = validate(self.hass, user_input, self.config_entry.entry_id)
            if not errors:
                acknowledge = user_input.pop("acknowledge", False)
                revision = defaults[CONF_REVISION]
                if acknowledge or user_input[CONF_METER] != defaults[CONF_METER]:
                    revision = uuid4().hex
                user_input[CONF_REVISION] = revision
                user_input["name"] = user_input["name"].strip()
                self.hass.config_entries.async_update_entry(
                    self.config_entry, title=user_input["name"]
                )
                return self.async_create_entry(title="", data=user_input)
        fields = dict(schema(user_input or defaults).schema)
        fields[probatio.Optional("paused", default=defaults.get("paused", False))] = bool
        fields[probatio.Optional("acknowledge", default=False)] = bool
        return self.async_show_form(
            step_id="init", data_schema=probatio.Schema(fields), errors=errors
        )
