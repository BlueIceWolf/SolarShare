"""Aligned, conservative building accounting and proportional apartment allocation."""

from copy import deepcopy
from decimal import Decimal

ZERO = Decimal(0)
ENERGY_KEYS = ("consumption", "solar", "direct_solar", "grid", "battery", "unknown")
SITE_KEYS = ("pv", "import", "export", "charge", "discharge", "consumption", "residual")


def empty(keys=ENERGY_KEYS):
    return dict.fromkeys(keys, ZERO)


def decimal_tree(value):
    if isinstance(value, dict):
        return {key: decimal_tree(item) for key, item in value.items()}
    result = Decimal(value)
    if not result.is_finite() or result < 0:
        raise ValueError("Invalid stored accounting value")
    return result


def strings(value):
    if isinstance(value, dict):
        return {key: strings(item) for key, item in value.items()}
    return str(value)


class SiteLedger:
    """Only complete source frames can affect apartments; missing data is not zero."""

    def __init__(
        self,
        apartment_ids,
        *,
        battery=False,
        capacity=10,
        max_power=100,
        skew=60,
        pv_keys=("pv",),
        require_fresh_reports=True,
        aggregation_seconds=0,
        balance_tolerance_kwh="0.02",
        allow_mixed_directions=False,
    ):
        self.apartment_ids = tuple(apartment_ids)
        self.pv_keys = tuple(pv_keys)
        self.battery = battery
        self.capacity = Decimal(str(capacity))
        self.max_power = Decimal(str(max_power))
        self.skew = float(skew)
        self.require_fresh_reports = require_fresh_reports
        self.aggregation_seconds = max(0, int(aggregation_seconds))
        self.balance_tolerance = Decimal(str(balance_tolerance_kwh))
        if not self.balance_tolerance.is_finite() or not ZERO <= self.balance_tolerance <= 2:
            raise ValueError("Invalid energy balance tolerance")
        self.allow_mixed_directions = bool(allow_mixed_directions)
        self.last_observation = None
        self.last_readings = None
        self.pending_seconds = 0
        self.pending_balance = None
        self.baseline = None
        self.baseline_times = None
        self.baseline_day = None
        self.frame_time = None
        self.available = False
        self.reason = "waiting_for_sources"
        self.gaps = 0
        self.review = False
        self.pools = {"solar": ZERO, "grid": ZERO, "unknown": self.capacity if battery else ZERO}
        self.periods = {}
        self.interval = None

    @property
    def required(self):
        return (
            *self.pv_keys,
            "import",
            "export",
            *(("charge", "discharge") if self.battery else ()),
            *(f"apt:{key}" for key in self.apartment_ids),
        )

    def interrupt(self, reason):
        if self.baseline is not None:
            self.gaps += 1
        self.baseline = self.baseline_times = self.frame_time = self.baseline_day = None
        self.last_observation = self.last_readings = None
        self.pending_seconds = 0
        self.pending_balance = None
        self.available = False
        self.interval = None
        self.reason = reason
        # Unobserved storage exchanges destroy origin certainty.
        self.pools = {
            "solar": ZERO,
            "grid": ZERO,
            "unknown": self.capacity if self.battery else ZERO,
        }

    def restore(self, data):
        if not data:
            return
        if type(data["review"]) is not bool or type(data["gaps"]) is not int:
            raise ValueError("Invalid accounting storage")
        self.review = data["review"]
        self.gaps = data["gaps"] + 1
        self.periods = decimal_tree(data["periods"])
        if self.gaps < 1:
            raise ValueError("Invalid stored gap count")
        for bucket in self.periods.values():
            if set(bucket) != {"site", "apartments"} or set(bucket["site"]) != set(SITE_KEYS):
                raise ValueError("Invalid stored site bucket")
            if any(set(values) != set(ENERGY_KEYS) for values in bucket["apartments"].values()):
                raise ValueError("Invalid stored apartment bucket")
        # Keep totals but deliberately invalidate the battery origin and all baselines.

    def snapshot(self):
        return {"review": self.review, "gaps": self.gaps, "periods": strings(self.periods)}

    def totals(self, period="lifetime", day=None):
        key = self.period_key(period, day) if day else period
        return self.periods.get(key)

    @staticmethod
    def period_key(period, day):
        return {
            "lifetime": "lifetime",
            "day": f"day:{day}",
            "month": f"month:{day[:7]}",
            "year": f"year:{day[:4]}",
        }[period]

    def observe(self, readings, timestamps, now, day):
        """Process a shared sampling boundary, using receipt freshness and skew limits."""
        if self.review:
            self.interrupt("review_required")
            return False
        if any(readings.get(key) is None or key not in timestamps for key in self.required):
            self.interrupt("source_unavailable")
            return False
        if any(not readings[key].is_finite() or readings[key] < 0 for key in self.required):
            self.interrupt("invalid_reading")
            return False
        times = {key: timestamps[key] for key in self.required}
        if self.require_fresh_reports:
            if any(now - stamp > 300 or stamp > now + 1 for stamp in times.values()):
                self.interrupt("stale_source")
                return False
            if max(times.values()) - min(times.values()) > self.skew:
                self.interrupt("sources_not_aligned")
                return False
        else:
            # HA integrations may publish cumulative counters only on change.
            # Sample available numeric states together; no missing source is
            # replaced. These are snapshots, not synchronized source reports.
            times = dict.fromkeys(self.required, now)
        current = {key: readings[key] for key in self.required}
        if self.baseline is not None:
            since_sample = now - self.last_observation
            if since_sample <= 0:
                self.interrupt("out_of_order")
                return False
            if since_sample > 300 or day != self.baseline_day:
                self.interrupt("observation_or_day_boundary")
            elif any(current[key] < self.last_readings[key] for key in self.required):
                self.review = True
                self.interrupt("meter_reset_or_implausible_jump")
                return False
            elif any(times[key] <= self.baseline_times[key] for key in self.required):
                # Wait for a report from every source. Never mix an old meter value
                # with fresh values from the other apartments.
                self.reason = "waiting_for_aligned_reports"
                return False
        self.last_observation, self.last_readings = now, current
        if self.baseline is None:
            self.baseline, self.baseline_times = current, times
            self.frame_time, self.baseline_day = now, day
            self.available = False
            self.reason = "baseline_ready"
            return False
        deltas = {key: current[key] - self.baseline[key] for key in self.required}
        limit = self.max_power * Decimal(str(now - self.frame_time)) / 3600 + Decimal("0.05")
        if any(value < 0 or value > limit for value in deltas.values()):
            self.review = True
            self.interrupt("meter_reset_or_implausible_jump")
            return False
        # Validate each inverter/string first. Summing raw counters before this
        # point could hide one source's reset behind another source's increase.
        deltas["pv"] = sum((deltas[key] for key in self.pv_keys), ZERO)
        if deltas["pv"] > limit:
            self.review = True
            self.interrupt("implausible_total_pv_jump")
            return False
        self.pending_seconds = now - self.frame_time
        self.pending_balance = {
            "supply_kwh": str(
                deltas["pv"]
                + deltas["import"]
                + deltas.get("discharge", ZERO)
                - deltas["export"]
                - deltas.get("charge", ZERO)
            ),
            "apartments_kwh": str(sum((deltas[f"apt:{key}"] for key in self.apartment_ids), ZERO)),
            "tolerance_kwh": str(self.balance_tolerance),
        }
        # Coarse cumulative registers must share an observation window with the
        # fine apartment counters. Waiting keeps the original baseline; it does
        # not publish invented supply or discard consumption at every poll.
        if self.pending_seconds < self.aggregation_seconds:
            self.interval = None
            self.reason = "waiting_for_meter_window"
            return False
        try:
            allocation, site, pools = self.allocate(deltas)
        except ValueError as err:
            if (
                self.aggregation_seconds
                and str(err) in ("inconsistent_energy_balance", "unresolved_export_origin")
                and self.pending_seconds < 3600
            ):
                self.interval = None
                self.reason = "waiting_for_meter_window"
                return False
            self.interrupt(str(err))
            return False
        self.pending_seconds = 0
        self.pending_balance = None
        self.pools = pools
        for period in ("lifetime", "day", "month", "year"):
            key = self.period_key(period, day)
            bucket = self.periods.setdefault(key, {"site": empty(SITE_KEYS), "apartments": {}})
            for metric, value in site.items():
                bucket["site"][metric] += value
            for apartment, values in allocation.items():
                target = bucket["apartments"].setdefault(apartment, empty())
                for metric, value in values.items():
                    target[metric] += value
        # Only current day/month/year counters are needed; lifetime is retained.
        keep = {self.period_key(period, day) for period in ("lifetime", "day", "month", "year")}
        self.periods = {key: value for key, value in self.periods.items() if key in keep}
        self.interval = {
            "apartments": allocation,
            "site": site,
            "seconds": Decimal(str(now - self.frame_time)),
            "ambiguous": ((deltas["import"] > 0 and deltas["export"] > 0)
                          or (deltas.get("charge", ZERO) > 0 and deltas.get("discharge", ZERO) > 0)),
        }
        self.baseline, self.baseline_times = current, times
        self.frame_time, self.baseline_day = now, day
        self.available, self.reason = True, (
            "observing_ambiguous_interval" if self.interval.get("ambiguous") else "observing"
        )
        return True

    def allocate(self, delta):
        """PV-first policy, AC counters, no simultaneous bidirectional exchanges.

        This is a declared interval allocation, not a physical per-apartment meter
        for energy origin. Battery origin follows proportional virtual inventory.
        """
        pv, imported, exported = (delta[key] for key in ("pv", "import", "export"))
        charge, discharge = (delta.get(key, ZERO) for key in ("charge", "discharge"))
        mixed = (imported > 0 and exported > 0) or (charge > 0 and discharge > 0)
        if mixed and not self.allow_mixed_directions:
            raise ValueError("mixed_direction_interval")
        if exported > pv and not (mixed and self.allow_mixed_directions):
            raise ValueError("unresolved_export_origin")
        load = pv + imported + discharge - exported - charge
        apartment_load = sum((delta[f"apt:{key}"] for key in self.apartment_ids), ZERO)
        if (
            load < 0
            or (load == 0 and apartment_load > 0)
            or apartment_load > load + self.balance_tolerance
        ):
            raise ValueError("inconsistent_energy_balance")
        denominator = max(load, apartment_load)
        unknown_balance = denominator - load
        if mixed:
            # Net cumulative counts show total energy, but not which direction
            # occurred while a particular apartment was drawing power. Preserve
            # the consumption without inventing a solar/grid billing split.
            allocations = {
                key: dict(consumption=delta[f"apt:{key}"], solar=ZERO,
                          direct_solar=ZERO, grid=ZERO, battery=ZERO,
                          unknown=delta[f"apt:{key}"])
                for key in self.apartment_ids
            }
            site = {
                "pv": pv, "import": imported, "export": exported,
                "charge": charge, "discharge": discharge,
                "consumption": load, "residual": max(load - apartment_load, ZERO),
            }
            pools = {"solar": ZERO, "grid": ZERO,
                     "unknown": self.capacity if self.battery else ZERO}
            return allocations, site, pools
        direct = min(pv - exported, max(load - discharge, ZERO))
        grid_direct = load - direct - discharge
        if grid_direct < 0:
            raise ValueError("inconsistent_energy_balance")
        pools = deepcopy(self.pools)
        battery_origins = empty(("solar", "grid", "unknown"))
        if discharge:
            stored = sum(pools.values(), ZERO)
            withdrawal = min(stored, discharge / Decimal("0.95"))
            for origin in pools:
                removed = withdrawal * pools[origin] / stored if stored else ZERO
                pools[origin] -= removed
                battery_origins[origin] = removed * Decimal("0.95")
            battery_origins["unknown"] += max(discharge - sum(battery_origins.values()), ZERO)
        if charge:
            solar_charge = min(charge, max(pv - exported - direct, ZERO))
            pools["solar"] += solar_charge * Decimal("0.95")
            pools["grid"] += (charge - solar_charge) * Decimal("0.95")
            excess = max(sum(pools.values(), ZERO) - self.capacity, ZERO)
            # Initial unknown inventory is an upper-bound opening estimate. Charging
            # may displace this uncertainty, never known stored origin.
            pools["unknown"] -= min(excess, pools["unknown"])
            if sum(pools.values(), ZERO) > self.capacity + Decimal("0.02"):
                raise ValueError("battery_capacity_exceeded")
        allocations = {}
        for key in self.apartment_ids:
            consumed = delta[f"apt:{key}"]
            fraction = consumed / denominator if denominator else ZERO
            allocations[key] = {
                "consumption": consumed,
                "solar": (direct + battery_origins["solar"]) * fraction,
                "direct_solar": direct * fraction,
                "grid": (grid_direct + battery_origins["grid"]) * fraction,
                "battery": discharge * fraction,
                "unknown": (unknown_balance + battery_origins["unknown"]) * fraction,
            }
        site = dict(
            pv=pv,
            import_=imported,
            export=exported,
            charge=charge,
            discharge=discharge,
            consumption=load,
            residual=max(load - apartment_load, ZERO),
        )
        site["import"] = site.pop("import_")
        return allocations, site, pools


def percentage(numerator, denominator):
    """Zero consumption has no meaningful ratio."""
    return min(Decimal(100), max(ZERO, numerator * 100 / denominator)) if denominator else None


def apartment_metric(values, metric):
    if metric == "autarky":
        # Unknown battery origin must never masquerade as solar self-sufficiency.
        return percentage(values["solar"], values["consumption"]) if not values["unknown"] else None
    return values[metric]
