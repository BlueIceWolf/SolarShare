"""Normalize old single-PV assignments and new disjoint multi-meter sources."""


def pv_entities(value):
    if isinstance(value, str):
        return [value] if value else []
    return list(value or [])


def source_entities(sources):
    return [
        *pv_entities(sources.get("pv")),
        *(value for key, value in sources.items() if key != "pv" and value),
    ]


def source_meters(sources):
    result = {key: value for key, value in sources.items() if key != "pv" and value}
    pv = pv_entities(sources.get("pv"))
    if len(pv) == 1:
        result["pv"] = pv[0]
    else:
        result.update({f"pv:{entity_id}": entity_id for entity_id in pv})
    return result


def total_pv(readings, keys):
    values = [readings.get(key) for key in keys]
    return sum(values) if values and all(value is not None for value in values) else None
