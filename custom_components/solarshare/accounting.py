"""Conservative observed-energy ledger, independent of Home Assistant.

Missing intervals are deliberately not recoverable from a cumulative reading:
their timing and ownership cannot be established by this initial implementation.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


def energy_kwh(value, unit: str | None) -> Decimal | None:
    """Accept only finite, nonnegative cumulative energy in supported units."""
    factors = {"Wh": Decimal("0.001"), "kWh": Decimal(1), "MWh": Decimal(1000)}
    if unit not in factors or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value)) * factors[unit]
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() and result >= 0 else None


@dataclass
class Ledger:
    """Persist totals; keep baselines strictly within a running observation epoch."""

    total: Decimal = Decimal(0)
    gaps: int = 0
    review_required: bool = False
    baseline: Decimal | None = None
    observed_at: float | None = None
    available: bool = False
    reason: str = "waiting_for_meter"
    max_gap: float = 300
    max_power_kw: Decimal = Decimal(25)

    @classmethod
    def restore(cls, data: dict | None, max_power_kw=25):
        """Never restore an active baseline, even after a clean shutdown."""
        ledger = cls(max_power_kw=Decimal(str(max_power_kw)))
        if data:
            total = energy_kwh(data["total"], "kWh")
            if (
                total is None
                or type(data["gaps"]) is not int
                or data["gaps"] < 0
                or type(data["review_required"]) is not bool
            ):
                raise ValueError("Invalid ledger storage")
            ledger.total = total
            ledger.gaps = data["gaps"] + 1
            ledger.review_required = bool(data["review_required"])
        return ledger

    def snapshot(self) -> dict:
        """Only durable accounting state, never a restart-spanning baseline."""
        return {
            "total": str(self.total),
            "gaps": self.gaps,
            "review_required": self.review_required,
        }

    def interrupt(self, reason: str):
        """Break continuity exactly once per unavailable period."""
        if self.baseline is not None:
            self.gaps += 1
        self.baseline = self.observed_at = None
        self.available = False
        self.reason = reason

    def observe(self, value: Decimal | None, now: float):
        """Commit only bounded, consecutive observations; latch anomalous resets."""
        if self.review_required:
            self.interrupt("review_required")
            return
        if value is None:
            self.interrupt("invalid_or_unavailable")
            return
        if self.observed_at is not None:
            elapsed = now - self.observed_at
            if elapsed <= 0:
                self.interrupt("out_of_order")
                return
            if elapsed > self.max_gap:
                self.interrupt("observation_gap")
        if self.baseline is not None:
            delta = value - self.baseline
            limit = self.max_power_kw * Decimal(str(now - self.observed_at)) / 3600
            # Small allowance for quantized meter updates (50 Wh).
            if delta < 0 or delta > limit + Decimal("0.05"):
                self.review_required = True
                self.interrupt("meter_reset_or_implausible_jump")
                return
            self.total += delta
        self.baseline, self.observed_at = value, now
        self.available = True
        self.reason = "observing"
