"""Explicit night-only zero-generation model, separate from real meter readings."""

from decimal import Decimal


class PVNight:
    def __init__(self, keys, enabled=True):
        self.keys = tuple(keys)
        self.enabled = enabled
        self.sleeping = frozenset()
        self.initialized = False
        self.last_good = {}

    def restore(self, values):
        """Retain real historical counters for diagnostics, never for catch-up."""
        for key, raw in (values or {}).items():
            if key not in self.keys:
                continue
            value = Decimal(raw)
            if not value.is_finite() or value < 0:
                raise ValueError("Invalid stored PV counter")
            self.last_good[key] = value

    def snapshot(self):
        return {key: str(value) for key, value in self.last_good.items()}

    def apply(self, readings, timestamps, now, sun_state, eligible):
        """Only missing PV counters can receive a virtual, constant night baseline.

        A virtual zero counter is not a physical meter reading. The caller must
        break accounting continuity when switching between actual and virtual
        counter epochs. Above-horizon/unknown sun never permits this inference.
        """
        for key in self.keys:
            value = readings.get(key)
            if value is not None:
                self.last_good[key] = value
        sleeping = frozenset(
            key
            for key in self.keys
            if self.enabled
            and sun_state == "below_horizon"
            and readings.get(key) is None
            and key in eligible
        )
        changed = self.initialized and sleeping != self.sleeping
        self.sleeping, self.initialized = sleeping, True
        effective, times = dict(readings), dict(timestamps)
        for key in sleeping:
            effective[key] = Decimal(0)
            times[key] = now
        return effective, times, changed
