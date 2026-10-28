# Accounting architecture and roadmap

## Version 0.2 implementation

The integration is now a central installation hub: one building source map, an
editable apartment list, automatic apartment devices, period counters, proportional
PV/grid allocation, self-sufficiency and a virtual battery-origin model. The current
rules, uncertainty treatment and supported measurement topology are documented in
the [README](../README.md). The following phases describe the original roadmap;
the immutable interval journal, SOC reconciliation and financial reporting remain
future work. Current source alignment is a bounded common sampling frame, not an
interpolated or billing-certified synchronized meter reading.

## Delivered in 0.1

One config entry and monotonic observed-energy ledger per apartment. Assignment
edits preserve apartment identity and total. Sources are cumulative energy sensors;
the integration does not derive energy by integrating instantaneous power.
Current storage contains the total, continuity-break count, review latch, source
identity and assignment revision. There is no financial or interval audit journal yet.

The runtime serializes observations and writes. A fresh baseline is required after
startup, unavailable data, assignment edits or an observation gap. Decreases and
implausible increases latch for review. Data from those intervals is excluded rather
than estimated. A storage failure blocks publication of further valid states.

## Phase 1: auditable interval ledger

- Persist immutable observations with meter identity, unit, source time, receipt
  time, sequence, assignment revision and quality. Keep late events separate.
- Effective-dated apartment assignments: close the old epoch at an explicitly
  recorded meter boundary, then open the new one. Never rewrite ownership history.
- Create aligned intervals only when all required meters cover the same boundaries.
  Define and configure allowed timestamp skew per source; never multiply a daily
  PV percentage by apartment consumption and label the result measured solar energy.
- Gaps remain unresolved. Any later manual reconciliation is a separate adjustment
  with evidence, actor, reason and original interval references. No silent backfill.
- Add recorder/statistics export, repair issues, complete gap timestamps, schema
  migrations, retention and durable journal recovery. Simulate power loss while
  saving and compare replayed totals against committed journal entries.

## Phase 2: grid and PV (without battery)

Configure distinct cumulative meters for AC PV production, grid import, grid export,
each apartment and common-area consumption. Define the measurement topology first.
For an aligned complete interval without storage, use:

```text
building load = PV AC production + grid import - grid export
PV used on site = PV AC production - PV export
building load = sum(apartment loads) + common loads + measured/unallocated residual
```

The PV-export identity requires a topology where export has no other source. It
cannot be assumed once grid-charged storage or another generator is present.
Reject contradictory negative balances beyond a documented tolerance; never clamp
away unexplained energy. Preserve residuals and quality flags.

Choose and document the distribution policy before implementation: e.g. proportional
allocation of interval PV used on site to eligible loads. Include common loads and
standalone wallboxes in the denominator. Cap every allocation by its recipient's
load; sum of allocations must not exceed measured distributable PV. Stable rounding
must preserve totals in integer Wh (or smaller fixed units), with residual handling.
This is an allocation policy, not proof of the path of individual electrons.

## Phase 3: batteries

Add separate AC charge/discharge counters, usable state of charge and documented
conversion efficiencies/boundaries. Track virtual PV-origin, grid-origin and unknown
energy inventories. Define an explicit mixing/discharge policy (e.g. proportional).
Store losses separately. Opening inventory of unknown origin stays unknown.
Do not count PV energy once at battery charging and again as newly generated energy
when discharged. Missing battery measurements make affected origin allocations
incomplete; no assumption of 100% PV charging. AC/DC meters cannot be mixed without
conversion/loss treatment. Test conservation over charge/discharge cycles, midnight,
grid charging, battery resets and unavailable SOC/energy meters.

## Phase 4: tariffs and reporting

Only after interval and session quality is auditable: effective-dated tariffs,
timezone-aware billing periods, tax/rounding rules, explicit incomplete-period
status, reproducible exports and reviewable adjustments. Store arithmetic in fixed
precision, never binary floating point. Legal/metrology suitability and financial
approval are outside this initial integration. No invoice generator is shipped.

## Required invariants

1. Unknown data is never zero; incomplete energy never receives an invented origin.
2. No interval or charge transaction is applied twice on replay/restart.
3. Assignment edits cannot move already committed consumption between apartments.
4. All allocations conserve measured energy within declared meter tolerances.
5. A billing period with unresolved intervals cannot silently appear complete.
6. Ledger/schema migrations preserve identities, totals and adjustment references.
