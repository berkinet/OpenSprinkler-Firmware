# Offline irrigation reference model

First implementation, 21 September 2026. Python standard library only, tested with Python 3.13.9. Run from the firmware repository root using zsh:

```zsh
python3 -m unittest discover -s tools/irrigation_replay/tests -v
python3 -m tools.irrigation_replay tools/irrigation_replay/fixtures/capacity-and-soak.json
python3 -m tools.irrigation_replay tools/irrigation_replay/fixtures/partial-refill.json
```

The CLI reads an explicit local fixture and writes a JSON report to stdout. It contains no network/GPIO/device integration, credentials, valve commands or imports of controller/bridge code. No package installation is needed. `calendar.py` uses the host's standard time-zone database through `zoneinfo`.

## Browser configuration integration

The engine now also consumes the actual exported v1 soil-water form draft,
with explicit runtime state. See the [configuration-to-engine integration
notes](../../docs/irrigation-engine/ENGINE_INTEGRATION.md) for field mappings,
missing runtime inputs, synthetic results and the remaining firmware boundary.

```zsh
python3 -m tools.irrigation_replay --draft tools/irrigation_replay/fixtures/editor-draft.json
python3 -m tools.irrigation_replay \
  --draft tools/irrigation_replay/fixtures/editor-draft.json \
  --runtime tools/irrigation_replay/fixtures/editor-runtime.json
```

`draft.py` validates and converts UI units; `engine.py` resolves calendar rules
and calls the existing planner. A shared fixture is tested through both the
real browser forms and the Python engine. The adapter requires explicit
reconciled depletion, dated ETo, resource settings and legal future service
assumptions. It does not solve future service capacity or persist/deliver plans.

## Implemented

- Validated shared profiles, separate valve ledgers, ordered named priority groups.
- Chronological point observations: ETo, rain, explicit delivered seconds, unknown delivery and missing-weather markers.
- Idempotent event revisions and replay from the initial state; checkpoint roundtrip without crediting planned runs.
- Piecewise-constant projected ET, calculated full/minimum-partial depth and runtime, continuous pulse-delivery projection with threshold-exceedance diagnostics.
- Greedy interval packing with one shared valve resource, cycle limits, minimum useful pulses, soak gaps, transition delays and a closing margin.
- Priority-first allocation and an optional one-rank promotion for the next explicitly identified eligible window. This remains a proposed policy for evaluation.
- Local-time calendar helper with weekday restrictions, excluded dates, overnight intervals, normalisation and conservative DST resolution.
- Machine-readable plan reports with pulse IDs, allocation reasons, modeled stress duration, ledger and promotion state.

## Demonstrated results

| Fixture | Result |
| --- | --- |
| `capacity-and-soak.json` | A receives five 60-second pulses over 540 seconds. B receives four 60-second pulses in A's soak gaps, reaching its modeled threshold at the next supplied service time. B receives a next-window promotion token. |
| `partial-refill.json` | A 480-second window cannot fit the 1,800-second full refill. The calculated sufficient partial is 450 seconds (3 mm net), leaving modeled depletion at 15 mm at the supplied next service. |

Fixtures are synthetic, not calibrated garden settings. Neither plan is recorded as water actually delivered. Fixture delivery observations must be supplied independently. The full/partial labels describe planned allocations; physical delivery is not asserted.

## Model contracts and limits

This is the first reference-model milestone, not the completed production scheduler or complete replay matrix.

- **Future opportunities are supplied, not solved.** Every zone requires explicit contiguous ET coverage and an explicit next-service timestamp at or after the current window end. That timestamp must already include an assumed service delay. Multi-window capacity-aware horizon computation remains unimplemented. Reports are conditional on these fixture assumptions.
- **Forecast rainfall is not credited.** The dry projection is piecewise linear; a partial event is accepted only if the whole projected path stays within the threshold. An already-stressed zone may receive a full refill, but its earlier stress remains reported.
- **Refill target is the window-start deficit.** The first model deliberately caps full allocation at that snapshot and rounds down to whole seconds to avoid overfilling. It does not yet increase the full target for ET accumulated before a delayed start. This conservative approximation differs from the specification's eventual event-start target. Minimum partial runtime rounds up, and must still fit within the full target. With too little current storage to cover the projected gap, this version skips and reports `storage_horizon_infeasible`; emergency insufficient watering is not implemented.
- **History uses point contributions.** ETo history events are applied at their supplied timestamp, unlike the continuous future projection. Authors must explicitly split historical periods around rain/delivery when order matters. Unmarked historical gaps are not inferred from missing events. Daily weather ingestion, period coverage validation, provider corrections and dated backfill remain separate work. Revisions in a fixture are treated retrospectively using the latest revision, not as an online arrival-time simulation.
- **Profiles stay fixed for a replay.** Soil/profile migrations and numerical calibration changes are not implemented. A ledger checkpoint only contains events and must be restored against the same initial state and configuration; it is not a production crash-safe file format.
- **One shared resource.** No simultaneous valves. Named priority groups do not define hydraulic groups. Reservations identify external valves; a reservation on a managed valve is rejected as ambiguous ownership. The caller supplies `ready_at` for soak carryover from a previous window. Valve/master latency beyond the explicit transition and closing-margin parameters is not modeled.
- **Greedy packing.** It may report `planner_no_fit` even when a different ordering or split could work. `insufficient_on_time` is a lower-bound result when even raw free ON seconds are inadequate. This is not a global optimality claim.
- **Calendar resolution depends on entry point.** The original replay fixtures contain resolved integer intervals. The new `--draft` runner invokes the tested local-time resolver using the form rules and an explicitly supplied named timezone. No real watering restriction is inferred from a location. DST rules are proposed and need review.
- **Window finalisation.** Promotion tokens expire only when the caller closes the relevant eligible window. Cancelled/ineligible windows must be omitted from that lifecycle. The runner finalises each fixture window once; restart recovery is an in-memory JSON roundtrip, not an active hardware recovery test. Duplicate closure is ignored. A partial planned allocation can earn a token; device failures do not masquerade as capacity skips.
- **No delivery confirmation integration.** Unknown-delivery markers block confident planning until corrected. The existing bridge/monitor interfaces and firmware queue remain unchanged. A full plan does not establish physical water flow.

The model uses potential crop demand above the threshold and exposes it as a planning diagnostic, not a calibrated stress physiology model. A peak beyond total capacity represents unsatisfied potential demand, not a physically negative reservoir. No uncertainty reserve has been added; equality with the threshold has zero modeled margin.

## Code map

| File | Responsibility |
| --- | --- |
| `model.py` | Configuration, point observations and zone ledger |
| `planner.py` | Demand calculation, pulse packing, projection, priority and promotion |
| `calendar.py` | Explicit calendar rule resolution |
| `replay.py` | Fixture orchestration and reports |
| `draft.py`, `engine.py` | Actual UI draft validation, unit conversion and calendar-to-planner orchestration |
| `tests/` | Numeric, accounting, temporal and lifecycle checks |

## Validation and remaining acceptance coverage

56 unittest methods pass, including 24 configuration/engine integration checks
and an independent exhaustive feasibility oracle for 1,920 small single-zone
packing combinations. The oracle establishes only the empty-window single-zone
cases it enumerates, not optimal packing for many valves.

Covered wholly or in their stated narrow reference-model form: interrupted/duplicate delivery accounting, unknown evidence, rain-overflow ordering, separate zone balances, full/partial numeric examples, cycle/soak interleaving, priority order, temporary promotion/expiry, minimum pulse rounding, transition/closing margins, and calendar/DST resolution.

Not complete: multi-day autonomous frequency replay (B01/B02), historical missing-day detection (B05), profile migration (B07), future feasible-service allocation (W07/W08), integrated cancellation/soak carryover, actual bridge faults and production persistence/dispatch (E04–E08). Consult the full [replay plan](../../docs/irrigation-engine/REPLAY_PLAN.md); the existence of a test module is not a claim that every matrix row is implemented.

Next: solve and replay future service opportunities across competing windows, then evaluate the proposed policies on multi-day cases. A focused XHigh review is useful before those results are translated into firmware. Keep High for the next implementation pass.
