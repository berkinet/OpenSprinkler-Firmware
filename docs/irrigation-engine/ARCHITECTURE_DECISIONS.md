# Architecture discussion and decisions — 20 September 2026

This is a substantive summary of the owner's discussion in the Irrigation Engine Replacement task, not a verbatim transcript. It supplements DISCUSSION_HANDOFF.md and the historical DEVELOPMENT_NOTES.md. Decisions here supersede earlier architectural assumptions; historical observations remain historical evidence.

## Current installation

- OpenSprinkler (OS) schedules LinkTap (LT) valves through the existing OpenSprinkler-LinkTap-Bridge. The owner reports this integration works well.
- RainMachine (RM) independently schedules its wired valves.
- Indigo remains supervisory. The Irrigation Monitor project already supports reading current RainMachine zones.

## Alternatives considered

1. Replace the scheduling policy inside RainMachine while retaining two independent schedulers. Readable controller source has been inspected, but integration, persistence, deployment and recovery remain unproven. This would leave us responsible for an old platform and would not improve LinkTap irrigation.
2. Extend OpenSprinkler as master scheduler and use RainMachine as a valve executor. One algorithm can improve both LinkTap and RainMachine zones. Public firmware and UI source provide a more accessible development base and a possible upstream adoption path.
3. A separate API-based scheduling service would reduce coupling to OS internals but require its own configuration/status interface. The owner prefers an integrated OS codebase for operational simplicity.

## Agreed direction

- Develop an optional depletion-based scheduling mode and watering-window capacity planner within an OpenSprinkler fork. Preserve existing scheduling as an option.
- Keep soil-water accounting and planning modular to reduce conflicts when incorporating upstream changes. Updating from upstream is deliberate; every upstream commit does not require a local change.
- OS owns scheduling, planned runs and history. Indigo remains supervisory.
- Use the existing OS ETo service initially. Its exact inputs, output and suitability for a persistent depletion balance still require inspection; revisit its calculations later.
- Reuse the working LT bridge.
- Use RM timed-start and stop operations; stop-all may support explicit shutdown or restart recovery. RM local programs would be disabled at commissioning, not during research.
- Do not add an OS zone type. Use different configurations of the existing HTTP zone type for LT and RM. Verify request format, authentication and duration support; a bridge may translate if necessary.
- Do not introduce RM queue management or history retrieval into the proposed adapter. Validate execution semantics for overlapping/repeated commands even though OS owns scheduling.
- Prototype and replay offline before controlled live testing.
- Upstream adoption is desirable but unconfirmed. A merge plus maintainer acceptance of ongoing responsibility could allow retirement of the fork. No maintainers have been contacted.

## Public source findings, not live validation

### OpenSprinkler

The upstream Unified Firmware includes scheduling and runtime execution in C++, with GPL-3.0 licensing. Program matching and runtime queue submission are visible in main.cpp; program.h defines a two-bit schedule type field with four existing types. A new mode therefore requires deliberate storage/API/UI integration, not only a menu entry. The UI is a separate upstream repository. These observations are from upstream source, not the owner's installed version.

- Firmware: https://github.com/OpenSprinkler/OpenSprinkler-Firmware
- Scheduling: https://github.com/OpenSprinkler/OpenSprinkler-Firmware/blob/master/main.cpp
- Program structure: https://github.com/OpenSprinkler/OpenSprinkler-Firmware/blob/master/program.h
- UI: https://github.com/OpenSprinkler/OpenSprinkler-App

### RainMachine API

The Python library is regenmaschine. Its source and RainMachine's official Python client agree on timed zone starts and zone stops. Local LAN authentication is supported without a cloud dependency.

Endpoints relative to /api/4:

| Operation | Endpoint |
| --- | --- |
| Timed start in seconds | POST zone/{id}/start, JSON time (regenmaschine also sends zid) |
| Stop zone | POST zone/{id}/stop |
| Stop all and clear pending watering | POST watering/stopall |
| Read watering zones | GET watering/zone |

Queue and history endpoints also exist but are outside the proposed minimal adapter scope. Timed start expresses controller-side runtime intent; network-loss behavior, repeated starts, restrictions and exact installed-firmware behavior have not been live-tested. A successful HTTP response must not automatically be equated with physical water delivery.

- Library: https://github.com/bachya/regenmaschine
- Zone implementation: https://github.com/bachya/regenmaschine/blob/dev/regenmaschine/endpoints/zone.py
- Local authentication: https://github.com/bachya/regenmaschine/blob/dev/regenmaschine/controller.py
- Vendor zone client: https://github.com/sprinkler/rainmachine-developer-resources/blob/master/api-python/API4Client/rmAPIClientZones.py
- Vendor watering client: https://github.com/sprinkler/rainmachine-developer-resources/blob/master/api-python/API4Client/rmAPIClientWatering.py

regenmaschine is a reference or possible offline test client. An integrated C++ adapter need not introduce a Python dependency. The existing HTTP-zone constraint takes priority when selecting the integration mechanism.

## Next work and boundaries

Inspect the existing OS installation/version and LT bridge before implementation. Check HTTP zone capabilities and the OS ETo interface. Define water balance, window planning and offline replay scenarios. Validate RM behavior only within explicitly authorized access boundaries.

The owner authorized creation of the project repository, documentation of this discussion and an OpenSprinkler fork. This does not authorize controller writes, copying controller files, installing software or operating valves. No implementation or deployment occurred during this discussion.

## Repository consolidation

The owner subsequently requested one repository for code and background documentation. These documents now live under docs/irrigation-engine in the OpenSprinkler firmware fork. The upstream README is preserved. The original documentation repository was archived after migration verification and subsequently deleted at the owner’s request. The OpenSprinkler UI remains a separate upstream project; its integration has not yet been implemented.

## Subsequent scheduling decisions

The owner agreed to one valve per zone, profile selection with one shared initial garden profile, separate zone depletion, hard watering restrictions, per-zone cycle-and-soak, and named ordered priority groups. Capacity skips are reported, with configurable temporary promotion for the next eligible window. Full refill remains the default; capacity-limited partial refill is calculated to keep projected depletion within threshold through the next opportunity, with unmet need/stress reported. Exact promotion size and several implementation defaults remain proposals.

The owner also selected extending the existing Indigo LinkTap bridge with an RM adapter. Both command paths therefore depend on Indigo; OS owns scheduling. The bridge project's decision note is at https://github.com/berkinet/OpenSprinkler-LinkTap-Bridge/blob/main/docs/RAINMACHINE-ADAPTER-DECISION.md . This supersedes the earlier suggestion to choose a separate RM bridge host.

See [SCHEDULING_SPEC.md](SCHEDULING_SPEC.md) and [REPLAY_PLAN.md](REPLAY_PLAN.md) for the consolidated design and explicit distinctions between agreements and proposed behavior.

## 21 September 2026 — program editor and selectable preview

Owner decision: initially, one soil-water program = one zone = one individual
valve. Select the program editor through the global scheduling mode. Both
modes must be selectable even before the new engine exists. Only the selected
engine generates automatic runs; retain the other mode’s configuration.

Implemented first draft: selectable persisted `smode=1`, Standard timed-match
gating, busy-mode-change rejection, a dedicated program editor and shared
settings draft. New forms save only browser-local drafts; mode 1 currently
generates no automatic irrigation. This storage choice is an interim prototype
implementation, not a decision to make the finished controller browser-dependent.

## Shared controls across scheduling modes

The owner requested reuse of Standard program-editor code wherever behavior
is shared, including timing controls. Name, enable and duration controls now
share implementation. Mode-specific scheduling semantics and persistence stay
separate; Standard repeat intervals are not reinterpreted as OFF-time soak.

## Priority-group management page

Owner decision: a dedicated page under Scheduling for the new algorithm. For
now groups have a name and an editable order only; additional properties can
be introduced later. Implemented with Move up / Move down and a highest-first
list, conditional on the saved Soil water balance selection. Renaming retains
program assignments; the initial implementation retains browser-draft storage.

## Equipment presets alongside direct calibration

Owner direction: offer direct application-rate (mm/hour) and efficiency (%)
entry, plus common equipment types to simplify setup. The current garden uses
drip emitters, spot mini-sprinklers, perforated lines and drip/soaker hose.
Manufacturer ratings and university guidance can support explicit estimates;
measurement is a refinement, not an inherent requirement of the equations.
See [APPLICATION_PRESETS.md](APPLICATION_PRESETS.md) for inspected sources,
proposed categories and the distinction between product flow, installed layout,
efficiency estimates and measured calibration. Preset values and UI details
remain proposals; this note does not change any zone's settings.

## Fixed event amounts and catalogue maintenance

Owner agreement: weather changes frequency; the chosen full-event watering
amount stays constant. Offer minutes per watering with an explicit assumed
refill after verified completion, or a fixed net depth converted through gross
application rate and efficiency. Runtime mode requires the common soil profile
for ETo/depletion tracking but no equipment flow calibration. Sensors may later
reconcile depletion; this increment does not add sensor ingestion.

Implemented in the editor and offline engine: v2 programs select `runtime` or
`depth`. Existing v1 and unconverted programs retain explicitly labelled legacy
behavior rather than silently acquiring new calibration. Runtime mode requires
a complete event to fit; capacity-limited partial depth events remain available
where their calculated delivery satisfies the existing horizon rules.

The owner also requested catalogue maintenance. The browser-local catalogue
supports add/edit/delete and JSON backup/import. Application copies product
ratings and layout provenance into a program; later catalogue changes cannot
silently alter saved program values. Seed entries are source-labelled examples,
not identified installed hardware or measured efficiency. Controller storage
and automatic dispatch remain future integration work.

## 22 September 2026 — fixed-time exceptions within the new scheduling mode

Owner clarification: Salad has a midday misting use distinct from irrigation.
Each program chooses mutually exclusively between Soil water balance and
**Fixed days, times and watering duration**. Both have a priority group. Keep
one soil-water program per physical valve, but permit separate fixed-time
programs on that same valve. Do not activate the Standard engine alongside the
new engine. The physical zone and water balance still belong to one valve.

Implemented prototype policy: fixed programs specify weekdays and exact local
start times, runtime, cycle/soak, priority and allowed hours. They do not require
soil calibration or infer refill from misting. Legal restrictions still apply;
blocked or conflicting events are skipped/reported, never delayed or caught up.
The offline planner reserves exact slots before flexible soil work, using group
order to resolve fixed-slot conflicts (chronological start then program ID for
ties). Fixed skips are not automatically promoted into extra/moved misting.
This ordering is an implementation policy for review, not a field-validated
agronomic rule. DST missing times are skipped, repeated times occur once at the
first occurrence. All prototype output remains conditional and non-dispatching.

## 23 September 2026 — first firmware integration and real weather

Owner authorized the next two steps: integrate autonomous execution into OS
firmware and connect real inputs, while retaining fake-valve output. The initial
Linux/Pi implementation reuses the Python reference planner as a one-shot
firmware-invoked component. C++ firmware owns durable configuration, journal,
station dispatch and completion. There is no independent scheduling daemon in
this mode. This implementation choice retains a Python/source-tree dependency;
it is not yet an ESP-portable allocation engine.

Use dated OS weather-service ETo/rainfall, converted once to mm. Today/future
ETo uses an explicitly labeled persistence estimate; completed-day weather is
reconciled by replay. Site profile/initial state remain owner-supplied inputs,
with a separate opt-in provisional test option. See FIRMWARE_SCHEDULER.md for
current capacity, promotion and commissioning limits.

## 24 September 2026 — external-control reservations

The owner clarified that Indigo independently manages Pool Refill and can
constrain its direct RainMachine commands to an agreed period. Selected a
third, mutually exclusive program option: Reserve time for external control.
It has days, start time(s) and duration, no valve or soil ledger, and mandatory
precedence over irrigation priorities. The scheduler leaves transition gaps
and fits irrigation outside the period; Indigo must stop by its end.
See EXTERNAL_RESERVATIONS.md. An OS API for deferred external watering requests
remains an alternative, not part of this implementation.
