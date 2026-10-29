"""One installation runtime collects all building and apartment source points."""

import asyncio
import logging
import time
from datetime import timedelta

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .accounting import energy_kwh
from .const import DOMAIN
from .observed_consumption import ObservedConsumption
from .tariff_accounting import TariffLedger
from .pv_night import PVNight
from .pv_sources import overlapping_growatt_totals, source_meters, total_pv
from .site_accounting import SiteLedger

_LOGGER = logging.getLogger(__name__)


class SiteRuntime:
    def __init__(self, hass, entry):
        self.hass, self.entry = hass, entry
        self.config = {**entry.data, **entry.options}
        self.options = dict(entry.options)
        self.signal = f"{DOMAIN}_{entry.entry_id}"
        self.meters = source_meters(self.config["sources"])
        self.pv_keys = tuple(key for key in self.meters if key == "pv" or key.startswith("pv:"))
        self.night = PVNight(self.pv_keys, enabled=self.config.get("pv_night_sleep", True))
        self.apartments = self.config["apartments"]
        self.wallboxes = self.config.get("wallboxes", [])
        self.units = [*self.apartments, *self.wallboxes]
        active = [item for item in self.units if not item.get("paused")]
        self.meters.update({f"apt:{item['id']}": item["meter"] for item in active})
        self.accounting_keys = set(self.meters)
        self.meters.update(
            {f"pv_detail:{entity_id}": entity_id for entity_id in self.config.get("pv_details", [])}
        )
        self.observed = ObservedConsumption(self.config.get("max_power_kw", 100))
        self.tariff_ledger = TariffLedger()
        self.ledger = SiteLedger(
            [item["id"] for item in active],
            battery=bool(self.meters.get("charge")),
            capacity=self.config.get("battery_capacity", 10),
            max_power=self.config.get("max_power_kw", 100),
            skew=self.config.get("alignment_seconds", 60),
            pv_keys=self.pv_keys,
            require_fresh_reports=self.config.get("require_fresh_reports", False),
            aggregation_seconds=0 if self.config.get("require_fresh_reports", False) else 300,
            balance_tolerance_kwh=self.config.get("balance_tolerance_kwh", "0.15"),
            allow_mixed_directions=True,
        )
        self.store = Store(hass, 1, f"{DOMAIN}.site.{entry.entry_id}", atomic_writes=True)
        self.identities = {}
        self.lock = asyncio.Lock()
        self.unsubs = []
        self.task = None
        self.active = False
        self.storage_failed = False
        self.legacy_total = None
        self.readings = {}
        self.reading_times = {}
        self.source_states = {}

    async def async_load(self):
        try:
            data = await self.store.async_load()
            if not data and self.entry.data.get("site_ledger_initialized"):
                raise ValueError("Previously initialized site ledger is missing")
            if data:
                self.ledger.restore(data["ledger"])
                self.observed.restore(data.get("observed_consumption"))
                self.tariff_ledger.restore(data.get("tariff_ledger"))
                self.identities = data["identities"]
                self.legacy_total = data.get("legacy_total")
                self.night.restore(data.get("last_pv_readings"))
                if data["revision"] != self.config["revision"]:
                    self.identities = {}
                    self.night.last_good = {}
                if data.get("review_token") != self.config.get("review_token"):
                    self.ledger.review = False
            elif self.entry.data.get("ledger_initialized"):
                legacy = await Store(self.hass, 1, f"{DOMAIN}.{self.entry.entry_id}").async_load()
                if not legacy:
                    raise ValueError("Legacy apartment ledger is missing")
                self.legacy_total = legacy["ledger"]["total"]
                if legacy["ledger"]["review_required"] and not self.config.get("review_token"):
                    self.ledger.review = True
            await self._save()
        except Exception as err:
            raise ConfigEntryError("SolarShare site ledger could not be loaded") from err

    async def _save(self):
        await self.store.async_save(
            {
                "ledger": self.ledger.snapshot(),
                "observed_consumption": self.observed.snapshot(),
                "tariff_ledger": self.tariff_ledger.snapshot(),
                "revision": self.config["revision"],
                "identities": self.identities,
                "legacy_total": self.legacy_total,
                "review_token": self.config.get("review_token"),
                "last_pv_readings": self.night.snapshot(),
            }
        )
        if not self.entry.data.get("site_ledger_initialized"):
            self.hass.config_entries.async_update_entry(
                self.entry, data={**self.entry.data, "site_ledger_initialized": True}
            )

    @callback
    def async_start(self):
        self.active = True
        self.unsubs = [
            async_track_state_change_event(
                self.hass, [*self.meters.values(), "sun.sun"], self._changed
            ),
            async_track_time_interval(self.hass, self._tick, timedelta(seconds=60)),
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._shutdown),
        ]
        self._queue()

    @callback
    def _changed(self, event):
        if not self.active or self.storage_failed:
            return
        state = event.data.get("new_state")
        if event.data["entity_id"] == "sun.sun":
            old = event.data.get("old_state")
            if old is None or state is None or old.state != state.state:
                self._queue()
            return
        # Evaluate invalid states immediately. Valid states are sampled together
        # on the common timer, rather than assigning an event from one apartment.
        if (
            state is None
            or energy_kwh(state.state, state.attributes.get("unit_of_measurement")) is None
        ):
            affects_accounting = False
            for key, entity_id in self.meters.items():
                if entity_id == event.data["entity_id"]:
                    self.readings[key] = None
                    self.source_states[key] = state.state if state is not None else "missing"
                    if key.startswith("apt:"):
                        # Do not bridge even a brief unavailable meter state
                        # when it recovers before the next 60-second sample.
                        self.observed.invalidate(key[4:])
                    night_pv = (
                        key in self.pv_keys
                        and self.night.enabled
                        and self._sun_state() == "below_horizon"
                        and (
                            state is None
                            or state.state in ("unknown", "unavailable")
                            or state.attributes.get("restored")
                        )
                    )
                    affects_accounting |= key in self.accounting_keys and not night_pv
                    if key in self.pv_keys:
                        self.readings["pv"] = None
            if affects_accounting:
                self.ledger.interrupt("source_unavailable")
            async_dispatcher_send(self.hass, self.signal)

    @callback
    def _tick(self, now):
        self._queue()

    def _sun_state(self):
        sun = self.hass.states.get("sun.sun")
        return sun.state if sun is not None and not sun.attributes.get("restored") else None

    @callback
    def _queue(self):
        if self.active and (self.task is None or self.task.done()):
            self.task = self.hass.async_create_task(self._sample())

    async def _sample(self):
        async with self.lock:
            if self.storage_failed:
                return
            now = time.time()
            readings, timestamps, eligible_night_pv = {}, {}, set()
            for key, entity_id in self.meters.items():
                source = er.async_get(self.hass).async_get(entity_id)
                identity = (
                    [source.platform, source.unique_id, source.config_entry_id]
                    if source
                    else [entity_id]
                )
                if (
                    key in self.accounting_keys
                    and key in self.identities
                    and self.identities[key] != identity
                ):
                    self.ledger.review = True
                    if key.startswith("apt:"):
                        self.observed.invalidate(key[4:])
                self.identities[key] = identity
                state = self.hass.states.get(entity_id)
                self.source_states[key] = state.state if state is not None else "missing"
                readings[key] = None
                if key in self.pv_keys and (
                    state is None
                    or state.state in ("unknown", "unavailable")
                    or state.attributes.get("restored")
                ):
                    eligible_night_pv.add(key)
                if (
                    state
                    and not state.attributes.get("restored")
                    and state.attributes.get("device_class") == "energy"
                    and state.attributes.get("state_class") in ("total", "total_increasing")
                ):
                    readings[key] = energy_kwh(
                        state.state, state.attributes.get("unit_of_measurement")
                    )
                    timestamps[key] = state.last_reported.timestamp()
            readings["pv"] = total_pv(readings, self.pv_keys)
            if all(key in timestamps for key in self.pv_keys):
                timestamps["pv"] = min(timestamps[key] for key in self.pv_keys)
            else:
                timestamps.pop("pv", None)
            self.readings = readings
            self.reading_times = timestamps
            # Metered consumer usage remains available when the site PV/grid
            # balance cannot be resolved. Unobserved gaps are never filled in.
            today = dt_util.now().date().isoformat()
            for unit in self.units:
                if not unit.get("paused"):
                    self.observed.observe(
                        unit["id"], readings.get(f"apt:{unit['id']}"), now, today
                    )
            effective, effective_times, transition = self.night.apply(
                readings, timestamps, now, self._sun_state(), eligible_night_pv
            )
            if transition:
                self.ledger.interrupt("pv_night_transition")
            if overlapping_growatt_totals(self.config["sources"].get("pv")):
                self.ledger.interrupt("overlapping_pv_sources")
            elif self.config.get("pv_measurement", "ac") == "ac":
                allocated = self.ledger.observe(
                    effective, effective_times, now, today
                )
                if allocated:
                    self.tariff_ledger.record(
                        self.ledger.interval["apartments"], today,
                        self.config.get("tariffs", {}),
                    )
                if self.ledger.reason == "observing" and self.night.sleeping:
                    self.ledger.reason = "observing_pv_night"
            else:
                self.ledger.interrupt("pv_measurement_boundary_unclear")
            try:
                await self._save()
            except Exception:
                self.storage_failed = True
                self.ledger.interrupt("storage_error")
                _LOGGER.exception("SolarShare site storage failed; allocation stopped")
            async_dispatcher_send(self.hass, self.signal)

    async def _shutdown(self, event):
        await self.async_stop()

    async def async_stop(self):
        self.active = False
        for unsub in self.unsubs:
            unsub()
        self.unsubs = []
        if self.task is not None:
            await self.task
        self.ledger.interrupt("stopped")
