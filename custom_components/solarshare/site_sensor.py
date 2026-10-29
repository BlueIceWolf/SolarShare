"""Site and apartment devices with automatically created energy/ratio points."""

import time
from decimal import Decimal

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .site_accounting import apartment_metric, percentage

PERIODS = {"lifetime": "Gesamt", "day": "Heute", "week": "Diese Woche", "last_week": "Letzte Woche", "month": "Dieser Monat", "last_month": "Letzter Monat", "year": "Jahr"}
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
    result = [SiteStatus(entry), LiveAutarkyPoint(entry)]
    for period in PERIODS:
        for metric in SITE_METRICS:
            if metric in ("charge", "discharge") and not runtime.ledger.battery:
                continue
            result.append(EnergyPoint(entry, metric, period))
        for apartment in runtime.units:
            result.append(ObservedEnergyPoint(entry, period, apartment))
            result.append(EnergyCostPoint(entry, period, apartment))
            for metric in APARTMENT_METRICS:
                result.append(EnergyPoint(entry, metric, period, apartment))
    for key in runtime.meters:
        result.append(SourceReading(entry, key))
    if "pv" not in runtime.meters:
        result.append(SourceReading(entry, "pv"))
    for apartment in runtime.units:
        result.append(AveragePower(entry, apartment))
        result.append(LiveUnitAutarkyPoint(entry, apartment))
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
            model=("Wallbox" if apartment.get("kind") == "wallbox" else "Wohnung") if apartment else "Energieanlage",
            **({"via_device_id": self.runtime.site_device_id} if apartment else {}),
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
            "pv_measurement": self.runtime.config.get("pv_measurement", "ac"),
            "source_sampling": "fresh_reports"
            if self.runtime.config.get("require_fresh_reports", False)
            else "available_counter_snapshots",
        }



class LiveAutarkyPoint(SiteEntity):
    """Current grid independence, never used in the cost calculation."""

    _attr_icon = "mdi:home-percent-outline"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry):
        super().__init__(entry, "site_live_autarky", "Autarkie Live")

    @property
    def native_value(self):
        metrics = self.runtime.live_metrics()
        return metrics["autarky"] if metrics else None

    @property
    def available(self):
        return self.runtime.live_metrics() is not None

    @property
    def extra_state_attributes(self):
        metrics = self.runtime.live_metrics()
        if metrics is None:
            return {
                "status": "power_sources_missing_or_stale",
                "configured": bool(self.runtime.live_power_sources),
                "explanation": "Live grid independence needs fresh power sensors.",
            }
        return {
            **metrics,
            "status": "live",
            "accounting_scope": "display_only_not_billable",
            "battery_origin": "not_tracked_in_live_percentage",
        }


class LiveUnitAutarkyPoint(SiteEntity):
    """Proportional share of current shared building power, display-only."""

    _attr_icon = "mdi:home-percent-outline"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry, unit):
        self.unit = unit
        super().__init__(
            entry, f"{unit['id']}_live_autarky",
            "Autarkie Live (anteilig)", unit,
        )

    @property
    def native_value(self):
        values = self.runtime.live_unit_metrics(self.unit)
        return values["autarky"] if values else None

    @property
    def available(self):
        return self.runtime.live_unit_metrics(self.unit) is not None

    @property
    def extra_state_attributes(self):
        values = self.runtime.live_unit_metrics(self.unit)
        if values:
            return {**values, "status": "live"}
        return {
            "status": "power_meter_missing_or_stale",
            "configured": bool(self.unit.get("power")),
            "accounting_scope": "display_only_not_billable",
        }


class ObservedEnergyPoint(SiteEntity):
    """Metered usage independent of site PV/grid balance."""

    _attr_icon = "mdi:counter"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, entry, period, unit):
        self.period = period
        self.unit = unit
        super().__init__(
            entry, f"{unit['id']}_observed_{period}",
            f"Gemessener Verbrauch {PERIODS[period]}", unit,
        )
        self._attr_state_class = (
            SensorStateClass.TOTAL_INCREASING
            if period == "lifetime" else SensorStateClass.TOTAL
        )

    @property
    def native_value(self):
        value = self.runtime.observed.value(
            self.unit["id"], self.period, dt_util.now().date().isoformat()
        )
        return round(value, 6) if value is not None else None

    @property
    def available(self):
        # Published historical values do not disappear during a meter outage.
        return self.native_value is not None

    @property
    def extra_state_attributes(self):
        return {
            "accounting_scope": "complete_observed_meter_intervals_only",
            "allocation_status": self.runtime.ledger.reason,
            "meter": self.unit["meter"],
            "meter_currently_available": self.runtime.readings.get(
                f"apt:{self.unit['id']}"
            ) is not None,
            "gap_count": self.runtime.observed.gaps.get(self.unit["id"], 0),
        }


class EnergyCostPoint(SiteEntity):
    """Accrued priced solar/grid energy, excluding unresolved-origin kWh."""

    _attr_icon = "mdi:currency-eur"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"

    def __init__(self, entry, period, unit):
        self.period = period
        self.unit = unit
        super().__init__(
            entry, f"{unit['id']}_priced_energy_cost_{period}",
            f"Kosten zugeordnete Energie {PERIODS[period]}", unit,
        )
        self._attr_state_class = (
            SensorStateClass.TOTAL_INCREASING
            if period == "lifetime" else SensorStateClass.TOTAL
        )

    def _costs(self):
        return self.runtime.tariff_ledger.value(
            self.unit["id"], self.period, dt_util.now().date().isoformat()
        )

    @property
    def native_value(self):
        amounts = self._costs()
        return round(amounts["solar_eur"] + amounts["grid_eur"], 4) if amounts else None

    @property
    def available(self):
        return self._costs() is not None

    @property
    def extra_state_attributes(self):
        amounts = self._costs()
        if not amounts:
            return {"status": "no_priced_intervals_yet"}
        day = dt_util.now().date().isoformat()
        observed = self.runtime.observed.value(self.unit["id"], self.period, day)
        bucket = self.runtime.ledger.totals(self.period, day)
        allocated = (
            bucket.get("apartments", {}).get(self.unit["id"], {}).get("consumption")
            if bucket else None
        )
        uncovered = max((observed or Decimal(0)) - (allocated or Decimal(0)), Decimal(0))
        not_priced = max((allocated or Decimal(0)) - amounts["covered_kwh"], Decimal(0))
        return {
            "solar_cost_eur": str(amounts["solar_eur"]),
            "grid_cost_eur": str(amounts["grid_eur"]),
            "unpriced_kwh": str(amounts["unpriced_kwh"]),
            "observed_not_allocated_kwh": str(uncovered),
            "allocated_before_tariff_kwh": str(not_priced),
            "partial_amount": bool(amounts["unpriced_kwh"] or uncovered or not_priced),
            "accounting_scope": "priced_verified_intervals_only",
            "price_history": "rates_at_time_of_allocation",
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
        if self.period in ("last_week", "last_month"):
            return None
        if self.period == "week":
            from datetime import timedelta
            boundary -= timedelta(days=boundary.weekday())
        elif self.period == "month":
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
        # Persisted, successfully allocated totals remain valid while the next
        # source interval is still gathering after restart or a brief outage.
        # Do not mistake the absence of a new allocation for lost history.
        return not (self.apartment or {}).get("paused") and self.native_value is not None


class SiteStatus(SiteEntity):
    _attr_icon = "mdi:list-status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_translation_key = "data_quality"
    _attr_options = [
        "waiting_for_sources",
        "review_required",
        "source_unavailable",
        "invalid_reading",
        "stale_source",
        "sources_not_aligned",
        "out_of_order",
        "observation_or_day_boundary",
        "waiting_for_aligned_reports",
        "baseline_ready",
        "meter_reset_or_implausible_jump",
        "implausible_total_pv_jump",
        "mixed_direction_interval",
        "unresolved_export_origin",
        "inconsistent_energy_balance",
        "battery_capacity_exceeded",
        "observing",
        "storage_error",
        "stopped",
        "pv_measurement_boundary_unclear",
        "overlapping_pv_sources",
        "observing_pv_night",
        "pv_night_transition",
        "waiting_for_meter_window",
        "observing_ambiguous_interval",
    ]

    def __init__(self, entry):
        super().__init__(entry, "site_status", "Datenqualität")

    @property
    def native_value(self):
        return self.runtime.ledger.reason

    @property
    def extra_state_attributes(self):
        result = super().extra_state_attributes
        now = time.time()
        diagnostics = {}
        for role, entity_id in self.runtime.meters.items():
            stamp = self.runtime.reading_times.get(role)
            diagnostics[entity_id] = {
                "role": role,
                "source_state": self.runtime.source_states.get(role, "not_sampled"),
                "valid_numeric_state": self.runtime.readings.get(role) is not None,
                "last_report_age_seconds": round(max(now - stamp, 0))
                if stamp is not None
                else None,
                "required_for_allocation": role in self.runtime.accounting_keys,
                "night_assumed_zero_generation": role in self.runtime.night.sleeping,
            }
        result["source_diagnostics"] = diagnostics
        result["unavailable_sources"] = [
            entity_id
            for entity_id, details in diagnostics.items()
            if not details["valid_numeric_state"]
            and details["required_for_allocation"]
            and not details["night_assumed_zero_generation"]
        ]
        result["sources_without_recent_report"] = [
            entity_id
            for entity_id, details in diagnostics.items()
            if details["last_report_age_seconds"] is not None
            and details["last_report_age_seconds"] > 300
            and details["required_for_allocation"]
        ]
        result["require_fresh_reports"] = self.runtime.config.get("require_fresh_reports", False)
        result["aggregation_seconds"] = self.runtime.ledger.aggregation_seconds
        result["balance_tolerance_kwh"] = str(self.runtime.ledger.balance_tolerance)
        result["pending_seconds"] = self.runtime.ledger.pending_seconds
        result["pending_balance"] = self.runtime.ledger.pending_balance
        if result["pending_balance"]:
            balance = result["pending_balance"]
            result["pending_difference_kwh"] = str(
                Decimal(balance["supply_kwh"]) - Decimal(balance["apartments_kwh"])
            )
        result["unmetered_consumption_note"] = (
            "Positive residual includes unmetered loads such as cellar and measurement differences; "
            "these cannot be separated without a dedicated meter."
        )
        result["pv_night_sleep"] = self.runtime.night.enabled
        result["sun_state"] = self.runtime._sun_state()
        result["pv_night_assumed_zero"] = [
            self.runtime.meters[key] for key in self.runtime.night.sleeping
        ]
        result["last_known_pv_counters_kwh"] = {
            self.runtime.meters[key]: str(value)
            for key, value in self.runtime.night.last_good.items()
        }
        from .pv_sources import overlapping_growatt_totals

        result["overlapping_pv_sources"] = overlapping_growatt_totals(
            self.runtime.config["sources"].get("pv")
        )
        return result


class SourceReading(SiteEntity):
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:counter"

    def __init__(self, entry, key):
        self.key = key
        apartment = next(
            (a for a in entry.runtime_data.units if key == f"apt:{a['id']}"), None
        )
        label = (
            "Zählerstand"
            if apartment
            else (
                f"PV-Quellzähler {entry.runtime_data.meters[key]}"
                if key.startswith(("pv:", "pv_detail:"))
                else (
                    "PV-Gesamtzählerstand" if key == "pv" else f"Zählerstand {SITE_METRICS[key][0]}"
                )
            )
        )
        super().__init__(entry, f"source_{key}", label, apartment)

    @property
    def native_value(self):
        return self.runtime.readings.get(self.key)

    @property
    def available(self):
        stamp = self.runtime.reading_times.get(self.key)
        return (
            self.runtime.ledger.reason not in ("stale_source", "storage_error", "stopped")
            and self.native_value is not None
            and (
                not self.runtime.config.get("require_fresh_reports", False)
                or (stamp is not None and -1 <= time.time() - stamp <= 300)
            )
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
