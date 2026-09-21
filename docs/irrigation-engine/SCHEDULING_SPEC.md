# Depletion scheduling specification — draft 1

Status: design for offline evaluation, 20 September 2026. No scheduler or controller behavior is changed by this document. “Agreed” records the owner's decisions; “proposed” identifies implementation choices for evaluation, not additional owner decisions. Existing source findings are in [INTEGRATION_FINDINGS.md](INTEGRATION_FINDINGS.md).

## 1. Agreed behavior

- One zone is one independently controlled valve. No logical multi-valve zones.
- A zone selects a named profile. Initially there is one shared garden profile; more can be added later. Each zone maintains its own water balance.
- Prefer bounded refill events with frequency driven by depletion. Predict need through the next permitted watering opportunity.
- Watering windows and day restrictions are hard limits, including every cycle-and-soak pulse.
- Zones have independently configurable cycle duration and minimum soak interval. Other zones may use soak gaps when resource limits permit.
- Each zone belongs to a named, ordered priority group. There may be one common group or as many groups as zones. Within a group use projected depletion relative to the threshold.
- Under capacity shortage select zones by effective priority. Always report skipped/partial events. Allow a configurable choice between report-only and promotion for the next eligible window only; configured group membership is unchanged.
- Full refill is the default. A capacity-limited partial refill should be calculated to keep the zone at or below its depletion threshold until its next permitted opportunity, rather than applying an arbitrary leftover quantity. Report unmet need and predicted stress if this cannot be accomplished.
- OS owns scheduling and its ledger. Use the OS ETo service initially. Preserve the existing HTTP zone type.
- Extend the existing Indigo bridge for RM authentication and timed-start/stop translation, sharing suitable OS callback/runtime handling with LT. Both command paths depend on Indigo; Indigo does not decide the irrigation schedule.

## 2. Model and records

Proposed units: water depth in millimetres over the zone's represented wetted area; runtime in integer seconds; calendar rules in the site's named time zone; resolved events in UTC. Application rate and soil storage must refer to the same area basis, particularly for drip irrigation. Do not assume sprinkler precipitation rates apply to drip lines.

| Record | Required information |
| --- | --- |
| Profile (versioned) | Name, available water capacity in mm/m, effective root depth in m, allowed-depletion fraction, crop coefficient, effective-rain factor |
| Zone | Stable ID, OS station mapping, profile ID, priority group ID, gross application rate in mm/hour, application efficiency, maximum cycle seconds, minimum soak seconds, minimum useful pulse seconds, enabled state |
| Priority group | Stable ID, name and ordered rank (rank 0 highest) |
| Site/calendar | Time zone, permitted weekdays/windows, date-specific exclusions, resource capacity, station/master delays, execution timing margin |
| Water state | Zone ID, depletion, profile version, last reconciled weather period, event/checkpoint identity, uncertainty flag |
| Event | Stable run and pulse IDs, zone, planned intervals/depth, delivered-runtime estimate, evidence quality, cancellation/fault reason |
| Carryover | Zone, capacity shortfall, report and optional next-window promotion token |

One selectable profile is not a claim that all garden plants have identical requirements. Its initial numbers need site calibration. No production soil, crop or application-rate defaults have been selected. Synthetic fixtures below are not recommendations for the garden.

Validate all numeric inputs: finite values, positive capacity/root depth/application rate, 0 < depletion fraction <= 1, 0 < efficiency <= 1, crop coefficient >= 0, rain factor in [0,1], positive minimum pulse <= maximum cycle, soak >= 0. Capacity resources initially default to one active valve across the planned zones for simulation, pending a site-specific hydraulic model. Priority groups are not OS hydraulic/sequential groups.

Changing profile assignments must not erase watering history or silently reset the zone to wet. Proposed migration preserves absolute stored water within the new capacity, flags the change and recomputes demand. Root-depth/capacity changes may require a fresh depletion estimate because new soil water is unknown. Calibration edits and initialisation are explicit events, not inferred watering.

## 3. Water accounting

Use a simplified root-zone bucket for the first offline model:

```
TAW = available_water_capacity_mm_per_m * root_depth_m
RAW = allowed_depletion_fraction * TAW
ETc = crop_coefficient * ETo_mm
I_net = gross_application_rate_mm_per_hour * efficiency * delivered_seconds / 3600
P_effective = rain_mm * effective_rain_factor
D_next = clamp(D_previous + ETc - P_effective - I_net, 0, TAW)
```

Here D is depletion (zero is field capacity). The equation is a simplified balance, not a full FAO-56 implementation: capillary rise is omitted, rain effectiveness is approximated, and excess above capacity is drainage. Apply gains/losses chronologically so a morning rainfall overflow cannot cancel unrelated future ET. Daily totals need an explicit time-distribution assumption in the replay; such interpolation is an estimate, not observed hourly weather.

Above RAW, flag predicted stress and its duration/exceedance; do not claim unstressed ET remains physiologically exact. The initial model retains potential crop demand as a conservative scheduling estimate rather than implementing a calibrated stress-reduction function. Track unmet demand separately if D saturates at TAW; clipping must not conceal an extended drought.

Maintain one ledger per valve, independent of program membership. Credit executed pulses, not scheduled depth. Repeated reports must be idempotent. A manual watering event enters the same ledger if its runtime is known; unobserved watering is unknown, never invented. Do not retrieve RM history to implement this design.

OS's station timer and a successful HTTP response do not prove water flowed. For the first integration, distinguish `planned`, `OS-runtime-estimated`, `bridge-acknowledged`, and `device-reported` evidence. Only verified failures justify a zero-delivery correction; an unknown outcome needs an uncertainty range or unresolved status, not automatic rewatering. Physical feedback integration is a later contract to agree with the existing monitor/bridge; it is not implemented here. The replay supplies explicit delivery events to test accounting independently.

## 4. Weather inputs and projection

Retain separate dated ETo and rainfall. Convert inches to mm with 25.4; never derive depletion from rounded/clipped OS watering percentages or apply those percentages again to model-generated runtimes.

Every input records source, period start/end, units, observation/forecast/estimate classification, retrieval time and revision. A repeated daily payload applies once. A correction replaces the previous contribution by replaying from a checkpoint; it is not additional rain/ET. Forecasts affect plans only and are replaced by observations without double-counting.

Proposed first replay policy: forecast rain is not credited as guaranteed water; observed rain is credited. Use explicitly supplied future ET estimates and mark the planning horizon uncertain. A missing historical day is not zero ET or zero rain. Enter a declared degraded state, retain existing ledger state and report the gap. The initial offline implementation should decline confident automated allocation across unresolved gaps; an operational fallback remains a future decision. The configured hosted service's dated coverage/backfill is not yet verified.

## 5. Trigger, refill and partial refill

For each zone, simulate depletion without a new event through its next legal, feasible service opportunity. The opportunity must include the expected service delay within that future window, not assume every zone starts at window opening. If that delay cannot yet be bounded, show an uncertain horizon. Iterate provisional reservations and projections; bounded search must report unresolved or infeasible horizons, not loop indefinitely or invent an opportunity beyond the configured calendar.

A zone is due when projected depletion reaches RAW before service can next begin. Crossing RAW before the present planned pulse is also reported; future refill does not erase earlier stress.

Proposed normal event depth: refill the depletion at the planned event start toward field capacity, subject to configured runtime and infiltration limits. Under stable demand and service timing this produces similar event amounts and varying intervals. Early watering for restrictions, rainfall and partial-event recovery can change the amount: do not force a nominal dose that exceeds the storage deficit. “Constant amounts” is a design preference, not a promise of mathematically identical doses.

For a capacity-limited partial event, calculate the smallest net depth that keeps projected depletion at or below RAW at every point through the next feasible opportunity. In the simplest dry-period case, ignoring ET during a short event:

```
minimum_net_refill = max(0, D_at_event_start + projected_ETc_until_next_service - RAW)
full_net_refill = D_at_event_start
required_seconds = ceil(3600 * minimum_net_refill / (application_rate * efficiency))
```

Check the complete pulse trajectory for the real plan. Do not rely solely on endpoint depletion if rain is forecast between a stress peak and the endpoint. Add a configurable uncertainty reserve only as a separately identified proposed parameter; fixtures initially use zero reserve. If minimum_net_refill exceeds available soil storage/full refill, even a full event cannot bridge the interval: report a calendar/demand infeasibility.

The chosen runtime must fit window/resource/soak constraints and the minimum useful pulse. A final shorter pulse is allowed if useful; otherwise adjust the split without exceeding capacity or soil storage, or reject that candidate.

Proposed initial allocation rule: in priority order, try full refill; if it cannot fit, try the minimum sufficient partial refill. If neither fits, skip and report the quantified shortfall. Do not sprinkle a token amount and label it adequate. Whether to offer an explicit emergency insufficient-refill mode remains open; do not implement one by assumption.

This is a priority-first policy, not an optimizer that maximizes the count of stress-free zones. A higher-priority full event may consume time that could have supplied several lower-priority partial events. The replay must expose that tradeoff for review rather than conceal it.

## 6. Windows and cycle-and-soak

Resolve recurring local-time rules to legal half-open intervals [start,end), including date exclusions. Adjacent/overlapping intervals are normalised; exclusions always win. Overnight windows are split at local midnight and each date's rules applied. Proposed DST semantics: nonexistent local boundary moves to the next valid instant; for ambiguous boundaries choose the later opening and earlier closing, dropping empty intervals. Validate this conservative rule before production; do not silently gain an extra watering hour.

Every pulse must end by the legal deadline. Duration is ON time only; soak is elapsed OFF time and may cross a closed interval. The preferred full event fits in one window; if only a sufficient partial fits, the next window gets a fresh depletion decision, not a blindly resumed old plan. No final soak is required for packing an event, but a subsequent event on that valve must respect the minimum OFF interval.

Example: 300 seconds ON, cycle <=60 seconds, soak >=60 seconds. Isolated pulses at [0,60), [120,180), [240,300), [360,420), [480,540) require 540 elapsed seconds. Another valve can use [60,120) while the first soaks. Soak need not be exactly 60 seconds; it is a lower bound. Account separately for valve transition/master delays and bridge latency margin. An illustrative zero-delay fixture does not imply zero-delay hardware.

Do not resolve a conflict by moving a pulse past closing, shortening its mandated soak, or ignoring resource reservations. Revalidate before dispatch and after interruptions; cancel or replan stale pulses. Firmware queue shifting/preemption cannot silently invalidate the legal-window check.

## 7. Priority and temporary promotion

Order due zones by effective group rank, then greatest projected D/RAW, then oldest unmet demand, then stable zone ID. Tie-break rules after depletion are proposed for deterministic replay. Do not water a non-due zone merely because it has a high priority or an unused promotion token.

Proposed promotion rules for the configurable `promote_next` mode:

- A capacity-shortfall event (skipped or partial) creates a token for the next eligible window only.
- Move one group higher, bounded at the top; never edit configured membership and never stack tokens. The size of the promotion is a proposal, not an earlier explicit owner selection.
- The token is fixed for one window, persists through replanning/restarts, and expires at its close. A new capacity shortfall in that window may issue a fresh token for the following window, still based on the configured rank.
- A wholly prohibited/cancelled window is not eligible. Disabled zones and missing input/device faults are not capacity skips and do not earn promotion.
- If rain removes demand at the next eligible window, expire the token without watering. It must not remain indefinitely waiting for demand.

`report_only` keeps rank unchanged. Both modes retain the physical deficit, report affected zones, and flag repeated unmet demand. Proposed default is report-only until replay demonstrates the promotion policy. Promotion cannot guarantee fairness or adequate water when total demand exceeds capacity; strict priority may starve lower groups and must be visible.

## 8. Planning, execution and restart boundary

Proposed planner stages: reconcile inputs; resolve windows/resources; project need; rank candidates; tentatively pack full then sufficient-partial events; recompute affected next-service horizons; emit a plan with reasons and confidence. Reservation changes must be transactional: a rejected partial plan leaves no orphan pulses. A deterministic greedy plan is initially acceptable; report `planner_no_fit` separately from proven insufficient capacity. A heuristic's failure is not proof no feasible packing exists.

Keep future pulse plans outside the legacy runtime queue. The inspected firmware has a finite queue and a station-to-queue mapping; blindly queueing many pulses per station is not a verified integration. Candidate dispatch design keeps at most one outstanding pulse per station and feeds ready pulses into existing execution handling, with deadlines checked again immediately before start. This is an integration proposal requiring source-level tests.

Persist configuration versions, water ledger/checkpoints, promotion tokens and event identity atomically. On restart, do not credit unfinished planned water or automatically resume stale pulses. Reconcile uncertain delivery and replan within the remaining legal window. Stop-all is available as a bridge capability; invoking it at every startup is not an agreed policy.

A depletion-controlled valve must have one automatic owner. The owner subsequently selected a global scheduling-mode choice: only the selected engine generates automatic runs. Standard programs remain stored while soil-water mode is selected. Within soil-water mode, one program = one zone = one individual valve, with no duplicate program ownership. This supersedes the earlier proposal to run legacy scheduling alongside depletion scheduling on other valves. Manual changes can invalidate reservations and require replanning. New hard-window guarantees cover this engine's automatic dispatch; whether all existing manual/legacy paths should be constrained is a separate integration decision, not a promise made by this document.

Do not bypass existing safety restrictions. Do not silently apply legacy weather/monthly/sensor duration scaling to a model-computed dose; audit and distinguish stop/veto safeguards from runtime multipliers at integration.

## 9. Reporting and user interface

One zone page selects profile, priority group, application calibration and cycle/soak settings. Separate profile and priority-group editors allow later expansion without per-zone numeric priority management. The plan view shows local start/end, ON versus elapsed time, full/partial/skipped status, effective/configured priority, projected depletion, next-service horizon and confidence.

Reports distinguish capacity deferral, no legal window, disabled/faulted zone, missing weather, insufficient storage, and planner search failure. Show net depth/time requested and allocated, evidence-based delivery estimate and outstanding deficit. Repeated shortage should produce a persistent actionable condition, not a new indistinguishable warning at every poll. No notification channel is selected here.

## 10. Scientific basis and limits

FAO-56 chapter 8 describes root-zone depletion, readily available water and irrigation depths no greater than the root-zone deficit. Partial refill is compatible with that balance; its adequacy depends on time to next service. This design uses a simplified bucket and does not claim complete FAO-56 agronomic fidelity: https://www.fao.org/4/x0490e/x0490e0e.htm

FAO deficit-irrigation research shows crop and growth-stage dependence. Do not infer a universal safe stress allowance for a mixed garden: https://www.fao.org/4/Y3655E/y3655e03.htm

CSU Extension describes cycle-and-soak as a way to apply the required amount while reducing runoff. Pulse/soak parameters are site-specific: https://extension.colostate.edu/resource/operating-and-maintaining-a-home-irrigation-system/

## 11. Scope of the next deliverable

Implement a pure offline reference model and replay harness from [REPLAY_PLAN.md](REPLAY_PLAN.md), with no network, GPIO, bridge calls or controller imports. First prove water accounting and interval packing independently of firmware. The reviewed revision-5 source is a reference baseline, not authorization to upgrade the installed revision-2 controller. UI and firmware deployment decisions follow replay evaluation.

## 12. Visible editor increment — 21 September 2026

The owner confirmed one program = one zone = one valve and requested a visible
editor draft, with Soil water balance selectable before the engine exists. The
test Pi now persists that selection and suppresses Standard timed matching in
soil-water mode. The UI routes program creation/editing to the appropriate form.
Draft soil-water forms are browser-local pending a controller storage contract;
no new-engine watering or water accounting is implemented by this increment.
See [UI_DEVELOPMENT.md](UI_DEVELOPMENT.md) for the precise preview boundary.
