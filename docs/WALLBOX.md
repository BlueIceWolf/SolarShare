# Wallbox support design (not a live adapter in 0.1)

The current integration can monitor a cumulative wallbox energy meter as a separate
entry. It cannot yet attribute a shared charger to cards, create sessions or control
a charger. This document defines the next implementation boundary.

## Configuration and topology

Create a charger adapter with stable charger ID, connector ID, transaction/session
ID, charging state, authorization/card ID and cumulative connector meter in Wh/kWh.
Prefer transaction events carrying meter and source timestamps atomically. Entity
adapters (e.g. charging state sensor plus meter plus RFID sensor) must retain event
timestamps and flag timing ambiguity rather than assuming state arrival order.

Use an editable, effective-dated card-to-apartment mapping. Preserve the exact
provider card token and namespace it by adapter/issuer. Do not coerce numeric-looking
IDs to integers or strip leading zeroes. Provider-specific normalization must be
explicit. Show masked card labels in ordinary diagnostics; raw RFID IDs can identify
people and must not be included in logs or exports by default. A card ID identifies
the configured account assignment, not verified physical identity.

Declare whether the charger is downstream of an apartment meter or is separately
metered at building level. A downstream session is a breakdown of that apartment's
load; it must not be added to the building load again. A shared, separately metered
charger is its own load and participates in PV allocation on the same intervals.

## Session record

```text
session_key: (adapter_id, charger_id, connector_id, transaction_id)
assignment: mapping_revision + apartment_id resolved at authorization/start
card_reference: private token reference, not a public sensor attribute
start/end: source timestamps, cumulative meter values, source identity/epoch
observations: ordered meter boundaries with sequence IDs and quality
totals: measured_energy_wh, unresolved_intervals, origin allocations
state: pending_authorization | active | suspended | ended | needs_review
```

Snapshot apartment ownership at session start. Editing a card mapping affects later
sessions; it never moves an existing session's energy. Unknown cards and missing or
ambiguous authorization remain **unassigned** for review. Never charge them to the
previous card, the default apartment or the person currently editing configuration.

## State machine and failure cases

1. A start transaction opens a session only with an unambiguous transaction ID,
   connector, owner mapping and start meter boundary. If authorization arrives late,
   keep it pending; do not invent a start meter from a later reading.
2. Consecutive valid meter deltas are attached to that transaction and to aligned
   building intervals. RFID changes mid-session do not automatically transfer
   ownership. An explicit transaction boundary or review is required.
3. A stop transaction with a valid end meter closes the session. Meter resets,
   rollback, source replacement or a missing boundary require review. A validated
   start/end cumulative pair may establish total session energy even when intermediate
   samples are missing, but those gaps still prevent timed PV/tariff attribution.
4. Persist open sessions, last committed sequence and idempotency keys before
   acknowledging an observation. Duplicate start/stop/meter events are harmless.
   Reject out-of-order events into a review queue or reorder within a documented
   bounded window; never decrement a committed session total.
5. On restart query the adapter for the active transaction and counter. Resume only
   when charger, connector, transaction, owner snapshot and meter epoch agree.
   Record the restart gap. If identity cannot be proven, suspend for review.
6. Two connectors need separate counters or transaction meter values. A charger-wide
   counter while both connectors charge is insufficient for individual attribution.

## Acceptance tests before enabling RFID attribution

- Two cards mapped to different apartments, unknown/blank cards and leading zero IDs.
- Mapping changes during charging, late authorization and a card change mid-session.
- Parallel connectors, overlapping sessions, duplicate events and delayed stop events.
- HA restart while charging, charger restart with new transaction ID, offline gaps,
  counter rollover/reset and restoration of stale sensor values.
- Session sum versus connector/building meters; downstream sessions never counted twice.
- Complete total energy with incomplete timed origin allocation remains visibly partial.

Start with a vendor-neutral replayable session engine and adapter contract tests,
then add the first hardware adapter once representative event samples are available.
