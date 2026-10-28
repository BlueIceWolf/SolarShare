"""Observed consumption, unavailable whenever source continuity is broken."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfEnergy
from homeassistant.helpers.dispatcher import async_dispatcher_connect


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ApartmentEnergy(entry)])


class ApartmentEnergy(SensorEntity):
    """Stable apartment identity survives renaming and meter replacement."""

    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, entry):
        self.runtime = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_observed_energy"
        self._attr_name = f"SolarShare {self.runtime.config['name']} observed energy"

    async def async_added_to_hass(self):
        self.async_on_remove(
            async_dispatcher_connect(self.hass, self.runtime.signal, self.async_write_ha_state)
        )

    @property
    def available(self):
        return self.runtime.ledger.available

    @property
    def native_value(self):
        return self.runtime.ledger.total

    @property
    def extra_state_attributes(self):
        ledger = self.runtime.ledger
        return {
            "source_entity": self.runtime.meter,
            "status": ledger.reason,
            "gap_count": ledger.gaps,
            "review_required": ledger.review_required,
            "last_observed_total_kwh": str(ledger.total),
            "accounting_scope": "observed_intervals_only",
        }
