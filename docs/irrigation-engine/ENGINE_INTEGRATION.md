# Configuration-to-engine integration — 21 September 2026

The owner requested starting engine work to check the match between form
properties and execution variables. This increment connects the actual v1 UI
draft to the existing offline planner. It is executable planning code, not a
firmware dispatcher. Automatic watering remains paused in Soil water balance
mode on the test Pi.

## Implemented path

Saved browser draft → strict configuration validation and unit conversion →
local calendar resolution → explicit reconciled state and dated ETo projection
→ priority allocation and pulse packing → a JSON plan with reasons.

The Programs preview page now offers **Export saved draft**. It exports only
the separate soil-water draft, including uncalibrated blanks. The standard OS
popup offers a file download and selectable JSON for browsers that do not
support downloads (the in-app browser did not confirm a download in review).
It does not
export controller credentials or station connection settings. Unsaved edits
are not included. The browser test suite creates the shared synthetic fixture
through the real forms and checks that the exported document matches exactly;
the Python tests consume that same fixture.

`draft.py` rejects unmapped configuration properties so an added UI field
cannot silently look supported by this version of the engine. Missing enabled
program calibration produces errors with form paths, such as
`programs[0].rate` or `profile.roots`. Disabled drafts need no calibration or
water state and never enter the allocation. They still need valid identity and
group/profile references. Empty watering-window configuration produces no plan.

## Form properties and engine variables

| Saved form property | Engine representation / use |
| --- | --- |
| `programs[].sid` | Zero-based OS station ID; internal zone identity `sid:N`. The older reference `Zone.station` is one-based, converted exactly once. Output pulse `sid` is zero-based again. |
| `name` | Report label; changing the name does not change valve identity. |
| `enabled` | Admission to planning. The runtime eligibility snapshot separately excludes disabled stations, masters and bundles. |
| `profile` | Reference to the shared `garden` profile. |
| `group`, ordered `groups` | Configured priority; list position determines rank. No additional group properties. |
| `rate` | Gross application rate, mm/hour, converted to net mm/second using efficiency. |
| `efficiency` | UI percentage divided by 100 once. |
| `cycle`, `soak`, `minimum` | Draft minutes converted to whole seconds. Blank remains unconfigured; zero soak is valid. Fractional-minute representations of one-second picker values are accepted without treating them as subsecond runtimes. |
| `profile.capacity × roots` | Total available root-zone water, mm. |
| `profile.depletion` | Percentage divided by 100, multiplied by total capacity to obtain the depletion threshold. |
| `profile.crop` | Applied once to reference ETo to obtain crop demand. Zero is valid. |
| `profile.rain` | Effective-rain percentage for historical accounting; validated and converted, but no forecast rain is credited by this planning pass. Zero is valid. |
| `windows[].days/start/end`, `excluded` | Existing conservative calendar resolver, normalised UTC intervals; exclusions override windows. Weekdays are Monday=0. |
| `shortage` | Report-only or proposed one-rank promotion. The dry run accepts an explicit active-promotion snapshot and reports candidates; it does not issue or expire persistent tokens. |
| Timing example in editor | An illustration only, deliberately absent from saved configuration and execution inputs. The engine calculates dose. |

The form previously rejected zero crop and effective-rain factors, although the
model accepts them. That validation mismatch is corrected. Capacity, root
depth and allowed depletion still must be positive.

## Inputs that are not ordinary program fields

| Required input | Current offline source | Integration still needed |
| --- | --- | --- |
| Depletion and reconciliation timestamp for each valve | Explicit runtime snapshot exactly at `as_of` | Controller ledger, deliberate initialisation/calibration and dated weather reconciliation. Never assume a new zone starts wet. |
| Unresolved observations/delivery | Explicit list per valve | Bridge/runtime evidence and uncertainty handling. An unresolved valve gets no allocation. |
| Earliest legal start after prior watering/soak | Explicit `ready_at` timestamp | Last OFF time from execution state, including interruption and restart. |
| Dated ETo with units and classification | Synthetic forecast/estimate periods | OS ETo adapter with period identity, revisions, freshness and missing-day recovery. Existing rounded watering percentages cannot supply this information. |
| Named site timezone | Explicit IANA name in runtime file | Resolve how to store this alongside OS's current timezone/offset configuration; do not infer DST rules from a numeric offset. |
| Hydraulic capacity, transition and closing margins | Explicit runtime resource settings | Audit the existing station/master/bridge settings and map them. This version accepts one shared active valve only; priority groups are not hydraulic groups. |
| Next feasible service time per valve | Explicit future timestamp inside a later permitted window, with room for at least a minimum pulse | The next engine milestone: solve future reservations and service delay across competing valves/windows. These timestamps are assumptions, not capacity-verified reservations. |
| Configuration/profile versions and persistent event identity | Draft version plus in-memory immutable model objects | Atomic controller storage, migrations, replay checkpoints and execution identities. Current group names are references; durable group IDs remain a later storage migration. |

The runtime file is a test input, not a proposal to make the owner type these
variables into the program form. Most must come from controller state or the
engine itself. No new UI properties have been added by assumption.

The calendar helper currently applies the selected weekdays to both dates of
an overnight window, as the specification proposes. The form labels these as
“Opening days”; that wording needs clarification before operational use. This
increment retains the conservative resolver and does not silently introduce a
different overnight restriction policy.

## Run and evaluate

From the repository root on the Mac (zsh) or the test Pi:

```zsh
# Audit a saved export without inventing runtime state.
python3 -m tools.irrigation_replay --draft /path/to/soil-water-draft.json

# Reproduce the shared synthetic example; no device access.
python3 -m tools.irrigation_replay \
  --draft tools/irrigation_replay/fixtures/editor-draft.json \
  --runtime tools/irrigation_replay/fixtures/editor-runtime.json

python3 -m unittest discover -s tools/irrigation_replay/tests -v
```

Validation failures return JSON `status: blocked` with field-specific issues
and exit code 2. A valid configuration audit is not a claim of operational
readiness. The dry run uses `conditional_plan`, never `ready_to_dispatch`.
All timestamps in runtime inputs must include a UTC offset. Reports contain
UTC seconds and readable local pulse timestamps.

Synthetic example results (not garden calibration):

| Valve | Priority | Allocation | ON / elapsed | End depletion at supplied next service |
| --- | --- | --- | --- | --- |
| Synthetic LinkTap | High | Full, five 60-second pulses | 300 / 540 seconds | 13.8 mm |
| Synthetic RainMachine | Normal | Sufficient partial, four 60-second pulses in soak gaps | 240 / 420 seconds | 15 mm (threshold) |

Both start at 6 mm depletion. The reference example supplies 13.8 mm future ETo
and zero ETo during the short present window. The second valve's partial depth
is 4.8 mm. No final soak is charged. Reversing only group order reverses who
gets the full refill. Shortening the window to six minutes prevents either
sufficient event from fitting; both receive a reported `planner_no_fit`, not
an arbitrary insufficient dose. The greedy failure is not a proof of optimality.

These are **planned** amounts. Input depletion remains unchanged by a plan;
no watering, ledger credit, persistent promotion, or controller API call occurs.

## Validation and next milestone

56 Python tests pass, including 24 new configuration/engine tests. 401 browser
tests pass, including the shared form-to-engine fixture, zero-factor validation
and saved-draft export. Coverage includes unit conversion, zero-based valve
mapping, priority changes, interleaved soak, unavailable valves, incomplete
calibration, weather gaps, state freshness, excluded future service, explicit
resource limits/margins, prior soak and unknown delivery.

The reference planner's existing limitations still apply: full refill is based
on the present snapshot rather than depletion at a delayed first pulse; future
service capacity is supplied rather than solved; historical weather/ledger
ingestion and profile migration are separate. See the
[reference-model limits](../../tools/irrigation_replay/README.md).

Next implement bounded future-service planning and multi-day frequency replay,
then review the numerical policy before translating the core into firmware
C++ and connecting persistent configuration and execution. Future pulse plans
must stay outside the finite legacy runtime queue until dispatch; never feed
this conditional dry-run report directly to valve commands.

## Fixed-event draft extension (version 2)

The compiler accepts existing v1 and new v2 exports. Additional program fields:

| Field | Meaning |
| --- | --- |
| `amountMode` | `runtime`, `depth`, or `legacy` (also the default for unconverted programs). |
| `runtime` | Fixed full-event ON minutes, resolving to whole seconds; required in runtime mode. |
| `depth` | Fixed net event mm; required in depth mode and bounded by the shared soil reservoir. |
| `equipment` | Optional text containing the copied catalogue entry/layout provenance. It is never used in place of the explicit numeric calibration. |

Runtime mode does not require `rate` or `efficiency`. It still requires a valid
profile and reconciled depletion/weather inputs. The planner retains the same
due test, legal windows, priority order and cycle/soak constraints. It allocates
the whole configured runtime or reports a skip. Its conditional projection
assumes zero depletion at the final pulse's end; it reports no physical delivered
mm (`allocated_mm` and `full_refill_mm` are null). Projection stress remains
visible if even an assumed refill cannot cover the next-service horizon.

Depth mode converts the fixed net event depth to whole ON seconds, without
weather-percentage scaling. It retains the existing capacity-shortfall partial
policy. Excess over the current modeled deficit is reported as drainage; the
full event is not shortened merely because today's deficit differs. Legacy v1
refills continue to use current depletion, preserving historical replay results.

The offline ledger accepts `completed_refill_seconds` only for runtime zones,
with an amount exactly equal to the configured complete event duration. This
observation is an explicit delivery assertion at event completion, not a start
acknowledgement or a per-pulse report. One stable observation ID represents the
whole event; a newer revision can replace uncertain/partial delivery with
verified completion, or withdraw an erroneous completion. Partial/manual
`delivered_seconds` in runtime mode cannot establish depth and therefore marks
the event unresolved without resetting depletion. Retry and checkpoint/restore
semantics remain idempotent. Future dispatch integration must reconcile every
pulse before emitting a completion assertion; no live adapter does so yet.

`fixtures/fixed-events-draft.json` is reproduced exactly by the browser form contract test
and consumed by Python tests. Run it with the existing editor-runtime fixture to
compare a full five-minute runtime event with a capacity-limited calibrated
water-depth event. These are synthetic offline examples, not garden calibration.


## 22 September 2026 — default and per-program permitted hours

Edit Options → Scheduling now includes a default daily permitted-hours control,
visible for Soil water balance. Use its **Save default hours draft** button;
this is browser-local draft storage, separate from controller option submission.
Each program can inherit that default, specify its own daily interval, or allow
any time within the site legal windows. Inheritance stays linked: changing the
default affects inheriting programs, while explicit overrides remain unchanged.

Times are controller-local; an earlier closing time crosses midnight. Equal
endpoints are rejected; the explicit Any time choice covers the full day.
Existing drafts inherit an unrestricted daily default, retaining their existing
legal windows. Site weekday windows and excluded dates are always hard limits;
a program override cannot widen them. Every pulse must fit inside the intersection.

The optional v2 root `defaultHours` and program `permittedHours` objects contain
`mode` (`all` or `custom`, plus `inherit` for programs). Custom objects require
`start` and `end` as HH:MM. Missing program settings inherit; missing default is
`all`. The offline compiler resolves inheritance and the planner limits pulse
packing, capacity calculations, and future-service validation to the resulting
intervals. Complete runtime events that cannot fit are skipped with no partial
allocation. Calendar resolution reuses the existing timezone/DST handling.

This remains an editor/offline implementation. Controller persistence and live
execution are not connected; automatic watering stays paused in the new mode.
