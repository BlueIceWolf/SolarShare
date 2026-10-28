"""Site and apartment devices with automatically created energy/ratio points."""

from decimal import Decimal

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .site_accounting import apartment_metric, percentage

PERIODS = {"lifetime": "Gesamt", "day": "Heute", "month": "Monat", "year": "Jahr"}
APARTMENT_METRICS = {
    "consumption": ("Verbrauch", "mdi:home-lightning-bolt"),
    "solar": ("Solarenergie", "mdi:solar-power"),
    "direct_solar": ("Direkter PV-Anteil", "mdi:solar-power-variant"),
    "grid": ("Netzenergie inkl. Speicher", "mdi:transmission-tower"),
    "battery": ("Batterieversorgung", "mdi:battery-charging"),
    "unknown": ("Ungeklärte Energieherkunft", "mdi:help-circle-outline"),
    "autarky": ("Autarkie", "mdi:home-percent-outline"),
}
SITE_METRICS = {
    "pv": ("PV-Erzeugung", "mdi:solar-power"),
    "import": ("Netzbezug", "mdi:transmission-tower-import"),
    "export": ("Einspeisung", "mdi:transmission-tower-export"),
    "charge": ("Batterieladung", "mdi:battery-arrow-up"),
    "discharge": ("Batterieentladung", "mdi:battery-arrow-down"),
    "consumption": ("Gebäudeverbrauch", "mdi:home-lightning-bolt"),
    "residual": ("Allgemeinverbrauch und Messdifferenz", "mdi:home-group"),
    "self_consumption": ("PV-Eigenverbrauchsquote", "mdi:solar-power"),
}


def entities(entry):
    runtime = entry.runtime_data
    result = [SiteStatus(entry)]
    for period in PERIODS:
        for metric in SITE_METRICS:
            if metric in ("charge", "discharge") and not runtime.ledger.battery:
                continue
            result.append(EnergyPoint(entry, metric, period))
        for apartment in runtime.apartments:
            for metric in APARTMENT_METRICS:
                result.append(EnergyPoint(entry, metric, period, apartment))
    for key in runtime.meters:
        result.append(SourceReading(entry, key))
    for apartment in runtime.apartments:
        result.append(AveragePower(entry, apartment))
    if runtime.legacy_total is not None:
        result.append(LegacyArchive(entry))
    return result


class SiteEntity(SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, entry, key, name, apartment=None):
        self.runtime = entry.runtime_data
        self.apartment = apartment
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        device_id = f"{entry.entry_id}_{apartment['id']}" if apartment else entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=apartment["name"] if apartment else self.runtime.config["name"],
            manufacturer="SolarShare",
            model="Wohnung" if apartment else "Energieanlage",
            **({"via_device": (DOMAIN, entry.entry_id)} if apartment else {}),
        )

    async def async_added_to_hass(self):
        self.async_on_remove(
            async_dispatcher_connect(self.hass, self.runtime.signal, self.async_write_ha_state)
        )

    @property
    def extra_state_attributes(self):
        return {
            "status": self.runtime.ledger.reason,
            "gap_count": self.runtime.ledger.gaps,
            "review_required": self.runtime.ledger.review,
            "allocation_method": "aligned_interval_proportional_pv_first",
            "origin_model": "virtual_battery_inventory_95_percent_efficiency",
            "accounting_scope": "complete_observed_intervals_only",
        }


class EnergyPoint(SiteEntity):
    def __init__(self, entry, metric, period, apartment=None):
        self.metric, self.period = metric, period
        names = APARTMENT_METRICS if apartment else SITE_METRICS
        label, icon = names[metric]
        scope = apartment["id"] if apartment else "site"
        super().__init__(
            entry, f"{scope}_{metric}_{period}", f"{label} {PERIODS[period]}", apartment
        )
        self._attr_icon = icon
        ratio = metric in ("autarky", "self_consumption")
        self._attr_native_unit_of_measurement = PERCENTAGE if ratio else UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = None if ratio else SensorDeviceClass.ENERGY
        self._attr_state_class = (
            SensorStateClass.MEASUREMENT
            if ratio
            else (
                SensorStateClass.TOTAL_INCREASING
                if period == "lifetime"
                else SensorStateClass.TOTAL
            )
        )

    @property
    def last_reset(self):
        if self.period == "lifetime" or self.metric in ("autarky", "self_consumption"):
            return None
        boundary = dt_util.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if self.period == "month":
            boundary = boundary.replace(day=1)
        elif self.period == "year":
            boundary = boundary.replace(month=1, day=1)
        return boundary

    @property
    def native_value(self):
        bucket = self.runtime.ledger.totals(self.period, dt_util.now().date().isoformat())
        if not bucket:
            return None
        if self.apartment:
            values = bucket["apartments"].get(self.apartment["id"])
            result = apartment_metric(values, self.metric) if values else None
        else:
            values = bucket["site"]
            result = (
                percentage(values["pv"] - values["export"], values["pv"])
                if self.metric == "self_consumption"
                else values[self.metric]
            )
        return (
            round(result, 3 if self.metric in ("autarky", "self_consumption") else 6)
            if result is not None
            else None
        )

    @property
    def available(self):
        return (
            self.runtime.ledger.available
            and not (self.apartment or {}).get("paused")
            and self.native_value is not None
        )


class SiteStatus(SiteEntity):
    _attr_icon = "mdi:list-status"

    def __init__(self, entry):
        super().__init__(entry, "site_status", "Datenqualität")

    @property
    def native_value(self):
        return self.runtime.ledger.reason


class SourceReading(SiteEntity):
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:counter"

    def __init__(self, entry, key):
        self.key = key
        apartment = next(
            (a for a in entry.runtime_data.apartments if key == f"apt:{a['id']}"), None
        )
        label = "Zählerstand" if apartment else f"Zählerstand {SITE_METRICS[key][0]}"
        super().__init__(entry, f"source_{key}", label, apartment)

    @property
    def native_value(self):
        return self.runtime.readings.get(self.key)

    @property
    def available(self):
        return (
            self.runtime.ledger.reason not in ("stale_source", "storage_error", "stopped")
            and self.native_value is not None
        )


class LegacyArchive(SiteEntity):
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:archive"

    def __init__(self, entry):
        super().__init__(entry, "observed_energy", "Verbrauch vor Anlagenumstellung (Archiv)")

    @property
    def native_value(self):
        return Decimal(self.runtime.legacy_total)


class AveragePower(SiteEntity):
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:flash"

    def __init__(self, entry, apartment):
        super().__init__(
            entry, f"{apartment['id']}_average_power", "Leistung Intervallmittel", apartment
        )

    @property
    def available(self):
        return self.runtime.ledger.available and not self.apartment.get("paused")

    @property
    def native_value(self):
        interval = self.runtime.ledger.interval
        if not interval or self.apartment["id"] not in interval["apartments"]:
            return None
        return round(
            interval["apartments"][self.apartment["id"]]["consumption"]
            * 3600000
            / interval["seconds"],
            1,
        )
