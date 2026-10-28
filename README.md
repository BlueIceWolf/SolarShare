<p align="center"><img src="custom_components/solarshare/brand/logo.png" alt="SolarShare" width="500"></p>

# SolarShare

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=BlueIceWolf&repository=SolarShare&category=integration)

Home Assistant custom integration for monitoring energy consumption per apartment,
with a foundation for solar energy sharing and future tenant electricity accounting.

**Initial development / v0.1.x:** apartment meter assignment and conservative observed
consumption are implemented. PV shares, prices, invoices, battery origin tracking and
live wallbox adapters are not implemented yet. The sensor reports only energy from
continuously observed intervals, not a complete or billing-certified consumption total.

## Install with HACS

Requires Home Assistant **2026.10 or newer** and an installed/configured HACS.

1. Open the **Open in HACS** button above, or open HACS → three-dot menu →
   **Custom repositories / Benutzerdefinierte Repositories**.
2. Add `https://github.com/BlueIceWolf/SolarShare` with category **Integration**.
3. Search for **SolarShare**, open it and select **Download / Herunterladen**.
   Without a published release, HACS installs the current default branch (`main`).
4. **Restart Home Assistant** after installation or updating the integration.
5. Open **Settings → Devices & services → Add integration → SolarShare**, then
   configure the apartments as described below.

This is a HACS custom repository, not a listing in the default HACS catalog.
HACS downloads the complete `custom_components/solarshare/` folder, including the
bundled icons. No extra icon installation or external brands-repository entry is needed.

### Icons and themes

The integration includes transparent PNG icons at 256/512 px and logos at 800/1600 px,
with light/dark variants in `custom_components/solarshare/brand/`. Home Assistant
serves these local brand images automatically. The energy entity also has a
`mdi:home-lightning-bolt` icon. An editable SVG source is included.

Some older HACS dashboard versions still use the legacy external icon CDN and may
show a placeholder even though the icon works in Home Assistant. This is a
[known HACS frontend issue](https://github.com/hacs/integration/issues/5171),
not a missing asset in this repository. Restart HA after installing the assets.

## Manual installation and apartment setup

Requires Home Assistant **2026.10 or newer**. The real-HA test target is 2026.10.4.

1. Copy `custom_components/solarshare` into your Home Assistant
   `config/custom_components/solarshare` directory and restart Home Assistant.
   Alternatively add this repository as a HACS **custom repository / Integration**
   and install it. This project is not in the default HACS catalog.
2. Open **Settings → Devices & services → Add integration → SolarShare**.
3. Enter an apartment name and select its cumulative energy sensor. Sources must
   have device class `energy`, state class `total` or `total_increasing`, and units
   `Wh`, `kWh` or `MWh`. Power (`W`/`kW`) and daily-reset meters are unsuitable.
4. Set the maximum plausible load for that apartment in kW (default 25 kW).
   This bounds acceptable increments; allow headroom for the real installation.
5. Repeat **Add integration** for each additional apartment. One active assignment
   per source meter is allowed. Setup also accepts temporarily unavailable sources;
   observation starts when valid data arrives.

English and German setup/options texts are included.

## Edit, replace or reassign meters

Open **Configure** on the apartment's integration entry. Change the name, source or
maximum load. The apartment's stable sensor identity and previously observed total
remain. Every reload starts a new baseline; no difference across the edit is added.

To move a meter from apartment A to B, first **pause A**, then select that meter in
B's configuration. A retains its historical total and releases the meter. Assign
a different meter to A before resuming it. There is no retroactive ownership change.
Pausing is also useful during maintenance or tenant changes.

A meter reset, implausible jump or entity-registry source identity replacement
holds the sensor unavailable with `review_required: true`. Check the source,
correct the maximum load if necessary, then use **I checked the source** in Configure.
This retains the total, clears the hold and starts a new baseline. It does not add
the skipped energy. A transient zero followed by an old high value cannot silently
release this hold.

## What the sensor means

Each apartment exposes **SolarShare <name> observed energy** in kWh. The first valid
reading establishes a baseline; it is not consumption. Consecutive valid increments
are accumulated with decimal arithmetic and saved before a state update is published.
The sensor uses `total_increasing` for Home Assistant statistics, but gaps make it an
incomplete observed total. Do not use it as an invoice amount.

- `unknown`, `unavailable`, missing entities, invalid numbers, restored startup states
  and incompatible metadata make the output unavailable; they never become zero.
- After a gap or restart, the next valid reading establishes a new baseline.
  Energy during the missing interval is deliberately omitted, even if the physical
  meter has a cumulative reading. Its time and ownership were not observed.
- No source change event for five minutes breaks continuity. A timer detects silent
  sources within a further 30 seconds. The next event after a long gap also rebaselines.
  Even a live but infrequently updating meter may therefore omit intervals. Choose
  a source reporting more frequently than five minutes. Unchanged values are not
  treated as proof of freshness by this initial implementation.
- Decreasing readings and jumps larger than maximum load × elapsed time plus a
  0.05 kWh quantization allowance require review. Small erroneous source values
  within this tolerance cannot be distinguished from real consumption.
- `gap_count`, `status`, `review_required`, `source_entity` and
  `last_observed_total_kwh` explain the state. Gap count is a continuity-break count,
  including restarts, not an audit log or a measured amount of missing energy.

Totals and review holds live in `.storage/solarshare.<entry_id>`. Baselines are never
restored across restarts. A missing previously initialized ledger or read error
blocks setup instead of creating a fresh zero. A write failure stops observation
and marks the output unavailable; reload after fixing storage. An abrupt shutdown
can lose the latest uncommitted update, but it will not be replayed or double counted.
Keep regular Home Assistant backups of both config entries and integration storage.
Removing an entry does not delete its ledger file; archive it before manual cleanup.
Re-adding a deleted apartment creates a new identity and a new total.

## Roadmap and design

See [accounting architecture](docs/ACCOUNTING.md) for interval alignment, PV/grid/
battery conservation and data quality requirements. See [wallbox design](docs/WALLBOX.md)
for RFID/card mapping, session ownership, meter boundaries and recovery behavior.

The MVP intentionally has no automatic tariff calculation, backfilling, source
origin claims or charger control. These need an auditable interval/session ledger.

## Development and tests

Offline ledger regression suite, Python 3.12+ and no third-party dependencies:

```sh
python -m unittest discover -s tests -p test_accounting.py -v
```

Real Home Assistant boundary tests, Linux and Python >=3.14.2:

```sh
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests/ha -v
```

The boundary tests use real Home Assistant objects and mock only disk IO and selected
config-entry operations. They cover setup/options results, duplicate assignment,
source metadata, persistence, gap recovery, write failures, pausing/reassignment and
unload draining. They do not replace a manual test in a running HA frontend.
GitHub Actions offers both suites and Ruff/HACS checks for manual runs only;
pushes and pull requests do not trigger them automatically. Changes should add regression cases
for accounting behavior, especially missing data and ownership boundaries.

API references used for the integration:
[config flows](https://contributors.home-assistant.io/core/integrations/config-flow/),
[options flows](https://contributors.home-assistant.io/core/integrations/options-flow/),
[sensor entities](https://contributors.home-assistant.io/core/entities/sensor/).
