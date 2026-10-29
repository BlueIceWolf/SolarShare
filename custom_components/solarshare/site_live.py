"""Instantaneous, explicitly measured site grid independence.

Power is not energy: these values are display-only and must never affect
cumulative kWh accounting, saved totals or tenant bills.
"""


def live_autarky(power, battery=False):
    """Return current grid independence using nonnegative W readings.

    Supported strategies:
      - Building load power and grid import power (preferred).
      - Sum of measured PV/import/export and, if applicable, battery powers.

    Battery origin is *not* inferred; live grid independence is not a claim
    that all energy came directly from the PV installation.
    """
    imported = power.get("import")
    if imported is None or imported < 0:
        return None
    load = power.get("load")
    if load is None:
        if any(power.get(key) is None or power[key] < 0 for key in ("pv", "export")):
            return None
        if battery and any(power.get(key) is None or power[key] < 0
                           for key in ("charge", "discharge")):
            return None
        load = (power["pv"] + imported - power["export"]
                + (power["discharge"] - power["charge"] if battery else 0))
    if load is None or load <= 0 or imported > load + max(50, load * 0.05):
        return None
    if load < 0:
        return None
    return {
        "autarky": round(max(0, min(100, (load - imported) / load * 100)), 1),
        "load_w": round(load, 1),
        "import_w": round(imported, 1),
        "measured": "direct_load" if power.get("load") is not None else "power_balance",
    }
