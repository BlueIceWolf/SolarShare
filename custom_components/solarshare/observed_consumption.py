"""Independent, gap-safe cumulative energy monitoring for metered consumers."""

from decimal import Decimal, InvalidOperation

from .periods import WRITTEN_PERIODS, period_key


class ObservedConsumption:
    """Count only consecutive valid, same-day meter observations, independently of PV."""

    def __init__(self, max_power_kw=100):
        self.max_power = Decimal(str(max_power_kw))
        self.totals = {}
        self.baselines = {}
        self.gaps = {}

    def restore(self, data):
        for period, units in (data or {}).get("totals", {}).items():
            if not isinstance(units, dict):
                raise ValueError("Invalid observed consumption storage")
            self.totals[period] = {}
            for unit, raw in units.items():
                value = Decimal(str(raw))
                if not value.is_finite() or value < 0:
                    raise ValueError("Invalid stored consumption")
                self.totals[period][unit] = value
        self.gaps = {
            unit: int(count) for unit, count in (data or {}).get("gaps", {}).items()
        }
        if any(count < 0 for count in self.gaps.values()):
            raise ValueError("Invalid observation gap count")

    def snapshot(self):
        return {
            "totals": {
                period: {unit: str(value) for unit, value in units.items()}
                for period, units in self.totals.items()
            },
            "gaps": self.gaps.copy(),
        }

    def value(self, unit, period="lifetime", day=None):
        key = period_key(period, day) if day else period
        return self.totals.get(key, {}).get(unit)

    def invalidate(self, unit):
        if unit in self.baselines:
            self.gaps[unit] = self.gaps.get(unit, 0) + 1
        self.baselines.pop(unit, None)

    def observe(self, unit, reading, now, day):
        try:
            value = Decimal(str(reading)) if reading is not None else None
        except (ValueError, InvalidOperation):
            value = None
        if value is None or not value.is_finite() or value < 0:
            self.invalidate(unit)
            return False
        previous = self.baselines.get(unit)
        self.baselines[unit] = (value, float(now), day)
        if previous is None:
            return False
        before, stamp, previous_day = previous
        elapsed = float(now) - stamp
        delta = value - before
        if previous_day != day or elapsed <= 0 or elapsed > 300 or delta < 0:
            self.gaps[unit] = self.gaps.get(unit, 0) + 1
            return False
        if delta > self.max_power * Decimal(str(elapsed)) / 3600 + Decimal("0.05"):
            self.gaps[unit] = self.gaps.get(unit, 0) + 1
            return False
        for period in WRITTEN_PERIODS:
            key = period_key(period, day)
            bucket = self.totals.setdefault(key, {})
            bucket[unit] = bucket.get(unit, Decimal(0)) + delta
        return True
