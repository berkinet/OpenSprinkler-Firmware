# Offline replay and acceptance plan — draft 1

This describes the next implementation, not an existing simulator or passed test suite. It accompanies [SCHEDULING_SPEC.md](SCHEDULING_SPEC.md). Fixtures are synthetic and must never be sent to a controller.

## Harness boundary

Proposed first implementation: Python standard library, so the reference model can run locally without installing packages. It is an executable specification, not a Python dependency for OS firmware. Keep numerical water accounting, candidate selection, interval packing and event replay separate so the later C++ implementation can run equivalent fixtures.

The simulator must not import OS/controller applications, load credentials or bridge settings, make network requests, or access GPIO. All inputs are explicit fixture files. A virtual clock advances events without real sleeps. No adapter that operates a valve belongs in this harness.

Proposed components:

- `balance`: unit conversion, chronological water balance and event deduplication.
- `calendar`: local recurring rules/exclusions to UTC intervals with explicit DST resolution.
- `demand`: due status, normal refill and minimum sufficient partial refill.
- `planner`: deterministic priority order, resource reservations and cycle/soak placement.
- `replay`: synthetic weather, delivery, interruption, restart and configuration events.
- `report`: per-zone decisions, pulse timeline, ledger and uncertainty output.

## Input/output contract

Version each fixture schema. Use stable IDs, explicit units, named time zone, dated weather periods, profile/group references, initial depletion and confidence, rate/efficiency, cycle/soak/minimum pulse, permitted windows, shared resource reservations, and time-stamped events. Synthetic known delivery is independent of scheduled duration.

Outputs must include resolved legal intervals, pulses, zone/event IDs, group/effective rank, full/minimum requested depth, allocated depth/time, observed or estimated delivery, residual depletion, reason codes, projection assumptions and promotion-token transitions. Capture config/source versions and seed (if random scenarios are later added) for reproducibility.

Start with explicit future ET amounts; do not implement a weather downloader. Forecast validation and hosted service compatibility remain a separate integration task.

## Numerical oracle examples

[micro-fixtures.json](micro-fixtures.json) holds five hand-checkable examples. These are arithmetic/planning targets only; checking their arithmetic does not validate a scheduler.

1. Full refill: D=12 mm, threshold RAW=15 mm, projected ETc=6 mm before next service. Without watering, D would reach 18 mm. At gross rate 30 mm/h and efficiency 0.8, full refill needs 1,800 seconds; minimum sufficient partial needs 450 seconds. A 480-second capacity limit can accommodate the 450-second sufficient partial, with 30 seconds left unused rather than overstating the required amount. The end-of-horizon D is 15 mm under the stated dry, short-event assumptions.
2. Insufficient remainder: same zone and forecast, but only 420 seconds available. The threshold-preserving minimum cannot fit. Proposed policy skips and reports; an arbitrary 420-second application would leave projected D=15.2 mm and cannot be called sufficient.
3. Cycle/soak: a zone needs 300 ON seconds, max cycle 60, min soak 60. Five isolated pulses span 540 seconds. A second valve may use a soak gap without extending the first event when shared capacity is one valve and transition overhead is zero.
4. Delivery accounting: D=12 mm, only 600 actual/known seconds delivered at the same rate and efficiency. Credit 4 mm, leaving D=8 mm before later weather. Do not credit a planned 1,800-second refill.
5. Storage infeasibility: D=12 mm, RAW=15 mm and projected ETc=20 mm. The simple required partial is 17 mm, greater than the present 12 mm deficit. Even full refill leaves projected D=20 mm. Flag the interval as infeasible; never apply 17 mm to a 12 mm deficit and claim the excess will remain available.

Equality with RAW in these examples is the boundary, not a robustness margin. Production uncertainty reserve remains to be selected. Rates, profiles and zero transition delays are illustrative only.

## Scenario matrix

| ID | Scenario | Required result |
| --- | --- | --- |
| B01 | Steady dry demand with sufficient daily windows | Repeatable bounded refill amounts; frequency responds to ET; water conserved within declared drainage/uncertainty |
| B02 | Increased ET with unchanged profile | Earlier due dates; no second multiplication by OS watering percentage |
| B03 | Observed rain before a planned event | Reconcile rain once, cancel/reduce unnecessary event; no negative depletion |
| B04 | Same daily payload repeated, then corrected | Duplicate adds nothing; corrected weather replays its period without duplicate irrigation |
| B05 | Missing day or absent timestamp | Declared degraded state; no silent zero-weather day or confident forecast across gap |
| B06 | Shared profile, different valve runtime histories | Distinct depletion/decisions despite same profile |
| B07 | Profile edit, reassignment and restart | Preserve history; version/explicitly initialise changed capacity; no silent reset to field capacity |
| W01 | 300-second event, 60/60 cycle/soak | 540-second isolated span, five pulses, no final soak charged |
| W02 | Another valve during soak gaps | No simultaneous resource violation; all minimum OFF times preserved |
| W03 | 539-second isolated window for W01 | Full event cannot fit; choose only an adequate partial candidate or report omission |
| W04 | Transition/master delay and dispatch margin | Delays reserve capacity; final valve-off deadline still inside legal interval |
| W05 | Overlapping windows, midnight exclusion | Normalise duplicates; never cross an excluded date segment |
| W06 | Spring/fall DST transition | Apply specified ambiguity rule, no accidental duplicate hour/event |
| W07 | Next opportunity exists but service is late in its window | Projection includes bounded service delay; no assumption every valve starts at opening |
| W08 | No future eligible window within horizon | Explicit horizon/calendar infeasibility, no fabricated timestamp |
| P01 | High and low groups both due, one event fits | Priority order determines service; low zone deficit persists and skip reported |
| P02 | Same group, different D/RAW | Greater relative depletion first; deterministic ties |
| P03 | Report-only after skip | Configured/effective group unchanged on next window |
| P04 | Promotion enabled after partial/skip | One-rank temporary promotion, no stacking; expires once; restart/replan do not consume early |
| P05 | Rain removes promoted zone demand | No unnecessary watering; token expires at eligible window close |
| P06 | Top-rank zone skipped; lower group repeatedly skipped | No rank overflow; no starvation guarantee; persistent shortage visible |
| P07 | Full high-priority vs several lower-priority minimum partials | Expose priority-first result and service tradeoff; do not silently switch objectives |
| R01 | Full refill cannot fit, sufficient partial fits | Allocate computed adequate partial, preserve residual depletion, report partial |
| R02 | Even minimum adequate partial does not fit | Skip and report predicted stress/shortfall under proposed default |
| R03 | Full refill cannot bridge legal-window gap | Report storage/calendar infeasibility; no overfill |
| R04 | Minimum pulse or last-pulse remainder affects packing | Valid useful split or candidate rejection; never exceed cycle/window/storage limits |
| E01 | Early stop after known delivered seconds | Credit delivered amount once; residual deficit remains |
| E02 | Duplicate callbacks/completion messages | No extra start, credit or promotion |
| E03 | Lost acknowledgement/unknown physical delivery | Uncertain ledger outcome; no automatic full replay or false zero/full credit |
| E04 | Restart during pulse/soak | Restore event/token state, do not resume stale pulses or claim planned delivery |
| E05 | Manual/legacy event consumes time or water | Reserve resource and reconcile known delivery; replan future work |
| E06 | Same valve in legacy and depletion automatic modes | Reject ownership conflict; no double scheduling |
| E07 | Rain veto/pause or closing time reached during plan | Stop/replan within legal bounds; no blind queue shift beyond closing |
| E08 | Many cycles/valves exceed legacy queue size | Planner keeps future work outside queue; later integration tests bounded dispatch |

## Invariants and success criteria

Every result must satisfy:

1. Each pulse has positive duration, valid zone mapping and a unique stable identity.
2. ON intervals obey legal windows, resource capacity and per-valve non-overlap; consecutive pulses obey minimum OFF duration.
3. Depth/runtimes use consistent units, and only declared delivery events affect irrigation credit.
4. Water/weather/event replay is idempotent and deterministic across checkpoint/restart.
5. Profile sharing does not share depletion; configured groups never mutate through promotion.
6. Reported sufficient partials satisfy the modeled threshold over the entire declared horizon, not just at its endpoint.
7. Skips and failures leave no phantom reservations or watering credit.
8. Unknown delivery/weather remains visible; no successful-looking report built from missing evidence.
9. A planner search failure is distinguished from a mathematical lower-bound capacity failure.

Report full/partial/skipped zones, predicted threshold exceedance in time and depth, window/resource utilisation, delivered-depth error, and repeat-deferral counts. Compare full-event-only against the proposed sufficient-partial policy on identical synthetic inputs. Compare report-only against promotion. Use small exhaustive schedule cases as an oracle for the greedy packer before claiming it finds all feasible plans.

## Delivery sequence

1. Implement and test pure balance, demand and cycle/soak packing using the numeric fixtures.
2. Add ordered-group allocation and both carryover policies; expose P07 tradeoffs.
3. Add calendar/DST, event replay and fault scenarios.
4. Review outputs and tune explicitly proposed policies before C++/UI integration.
5. Audit existing runtime hooks and HTTP delivery evidence; only then design production persistence and dispatch changes.

Astra High is recommended for model/planner implementation. Use a focused Astra XHigh review after the initial implementation and scenario results exist, especially for partial-refill horizons, promotion lifetime and restart accounting. Effort settings are a workflow preference, not correctness evidence.
