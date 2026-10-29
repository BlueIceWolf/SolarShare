"""Immutable incremental tariff totals; no historical repricing or invented energy."""

from decimal import Decimal


def period_key(period, day):
    return {"lifetime": "lifetime", "day": f"day:{day}",
            "month": f"month:{day[:7]}", "year": f"year:{day[:4]}"}[period]


class TariffLedger:
    """Price only confidently attributed solar/grid kWh from accepted windows."""

    def __init__(self):
        self.periods = {}

    def restore(self, data):
        for period, units in (data or {}).items():
            if not isinstance(units, dict):
                raise ValueError("Invalid tariff storage")
            self.periods[period] = {}
            for unit, parts in units.items():
                if (not {"solar_eur", "grid_eur", "unpriced_kwh"} <= set(parts)
                        or set(parts) - {"solar_eur", "grid_eur", "unpriced_kwh", "covered_kwh"}):
                    raise ValueError("Invalid tariff bucket")
                values = {key: Decimal(str(value)) for key, value in parts.items()}
                values.setdefault("covered_kwh", Decimal(0))
                if any(not value.is_finite() or value < 0 for value in values.values()):
                    raise ValueError("Invalid monetary total")
                self.periods[period][unit] = values

    def snapshot(self):
        return {
            period: {unit: {key: str(value) for key, value in values.items()}
                     for unit, values in units.items()}
            for period, units in self.periods.items()
        }

    def record(self, allocations, day, tariffs):
        if "solar" not in tariffs or "grid" not in tariffs:
            return False
        rates = {key: Decimal(str(tariffs[key])) for key in ("solar", "grid")}
        if any(not value.is_finite() or value < 0 for value in rates.values()):
            raise ValueError("Invalid tariffs")
        for period in ("lifetime", "day", "month", "year"):
            bucket = self.periods.setdefault(period_key(period, day), {})
            for unit, values in allocations.items():
                amounts = bucket.setdefault(unit, {
                    "solar_eur": Decimal(0), "grid_eur": Decimal(0),
                    "unpriced_kwh": Decimal(0), "covered_kwh": Decimal(0),
                })
                amounts["solar_eur"] += values["solar"] * rates["solar"]
                amounts["grid_eur"] += values["grid"] * rates["grid"]
                amounts["unpriced_kwh"] += values["unknown"]
                amounts["covered_kwh"] += values["consumption"]
        return True

    def value(self, unit, period, day):
        return self.periods.get(period_key(period, day), {}).get(unit)
