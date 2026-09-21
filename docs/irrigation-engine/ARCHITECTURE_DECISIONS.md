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
