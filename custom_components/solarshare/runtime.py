"""Event-driven observation and serialized persistent ledger writes."""

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

from .accounting import Ledger, energy_kwh
from .const import CONF_MAX_POWER, CONF_METER, CONF_REVISION, DOMAIN, MAX_GAP_SECONDS

_LOGGER = logging.getLogger(__name__)


class SolarShareRuntime:
    """An apartment's total is independent of its currently assigned source."""

    def __init__(self, hass, entry):
        self.hass, self.entry = hass, entry
        self.config = {**entry.data, **entry.options}
        self.options = dict(entry.options)
        self.meter = self.config[CONF_METER]
        self.signal = f"{DOMAIN}_{entry.entry_id}"
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}", atomic_writes=True)
        self.ledger = Ledger()
        self.lock = asyncio.Lock()
        self.tasks = set()
        self.unsubs = []
        self.active = False
        self.identity = None
        self.storage_failed = False

    async def async_load(self):
        """Fail closed if storage is unreadable; never silently replace totals."""
        try:
            data = await self.store.async_load()
            if not data and self.entry.data.get("ledger_initialized"):
                raise ValueError("Previously initialized ledger is missing or corrupt")
            self.ledger = Ledger.restore(data and data["ledger"], self.config[CONF_MAX_POWER])
            if data:
                self.identity = data.get("identity")
                if data["revision"] != self.config[CONF_REVISION]:
                    self.ledger.review_required = False
                    self.identity = None
            # Persist initialization before exposing a fresh zero total. The entry
            # marker prevents Store's corrupt-file recovery from resetting totals.
            await self._save()
        except Exception as err:
            raise ConfigEntryError("SolarShare ledger could not be loaded") from err

    @callback
    def async_start(self):
        if self.config.get("paused"):
            self.ledger.interrupt("paused")
            async_dispatcher_send(self.hass, self.signal)
            return
        self.active = True
        self.unsubs = [
            async_track_state_change_event(self.hass, [self.meter], self._changed),
            async_track_time_interval(self.hass, self._expire, timedelta(seconds=30)),
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._shutdown),
        ]
        self._queue(self.hass.states.get(self.meter), time.time())

    @callback
    def _changed(self, event):
        self._queue(event.data.get("new_state"), time.time())

    @callback
    def _expire(self, now):
        if (
            self.ledger.observed_at is not None
            and time.time() - self.ledger.observed_at > MAX_GAP_SECONDS
        ):
            self._queue(None, time.time())

    @callback
    def _queue(self, state, now):
        if not self.active:
            return
        task = self.hass.async_create_task(self._process(state, now))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _process(self, state, now):
        async with self.lock:
            if self.storage_failed:
                return
            source = er.async_get(self.hass).async_get(self.meter)
            identity = (
                [source.platform, source.unique_id, source.config_entry_id]
                if source
                else [self.meter]
            )
            if self.identity is not None and self.identity != identity:
                self.ledger.review_required = True
            self.identity = identity
            value = None
            if state is not None and not state.attributes.get("restored"):
                age = (dt_util.utcnow() - state.last_updated).total_seconds()
                if (
                    0 <= age <= MAX_GAP_SECONDS
                    and state.attributes.get("device_class") == "energy"
                    and state.attributes.get("state_class") in ("total", "total_increasing")
                ):
                    value = energy_kwh(state.state, state.attributes.get("unit_of_measurement"))
            self.ledger.observe(value, now)
            try:
                await self._save()
            except Exception:
                self.storage_failed = True
                self.ledger.interrupt("storage_error")
                _LOGGER.exception("SolarShare storage write failed; observation stopped")
            async_dispatcher_send(self.hass, self.signal)

    async def _save(self):
        await self.store.async_save(
            {
                "ledger": self.ledger.snapshot(),
                "revision": self.config[CONF_REVISION],
                "identity": self.identity,
            }
        )
        if not self.entry.data.get("ledger_initialized"):
            self.hass.config_entries.async_update_entry(
                self.entry, data={**self.entry.data, "ledger_initialized": True}
            )

    async def _shutdown(self, event):
        await self.async_stop()

    async def async_stop(self):
        self.active = False
        for unsub in self.unsubs:
            unsub()
        self.unsubs = []
        if self.tasks:
            await asyncio.gather(*list(self.tasks))
        self.ledger.interrupt("stopped")
