# OS integration inspection — 20 September 2026

## Scope

Read-only source review of firmware fork commit 41956f12fa4beae98b0fb8643cf8191823844091 (upstream baseline 6ac3b11), OpenSprinkler-Weather commit 07b3689d80dfc03d3147f146bf1cc51e6c2f69fe, and the owner’s existing private OpenSprinkler-LinkTap-Bridge repository at 8c39cf2eef4913e16b3e59c9629289fd73412a0a. Bridge findings here are a summary, not a publication of private plugin source or configuration.

Read-only GET requests to the documented OSPi address confirmed selected firmware and weather fields. No SSH access, active-run test, configuration change, application execution, installation or valve operation occurred. No controller files were copied.

## Installation evidence

- Live /jo: fwv=221, fwm=2, hwv=64, uwt=3, wl=91. This confirms firmware 2.2.1 (2), with ETo mode selected.
- Live /jc: wterr=0. Selected wtdata fields were eto=0.147, p=0, wp=Apple. These are a point-in-time observation, not a historical series or validation of weather accuracy.
- Bridge documentation records app 2.4.99; the app version and installed bridge binary were not independently checked this turn.
- The firmware fork identifies itself as 2.2.1 (5), not the installed revision 2. Source conclusions below apply to the reviewed commit, not automatically to the installed binary. Preserve a deliberate version baseline before development/deployment.

## HTTP station execution

In OpenSprinkler.cpp, switch_special_station receives duration but its HTTP/HTTPS branch calls switch_httpstation without that duration. switch_httpstation parses the configured server, port, on and off command strings and emits a static GET request. It does not provide arbitrary JSON POST bodies, dynamic duration substitution or RainMachine login/session handling.

Consequently changing HTTP-zone configuration alone cannot directly express the reviewed RainMachine authenticated timed-start POST contract. A translating bridge is the compatible path while retaining the existing HTTP zone type. This does not require a new OS zone type.

Source: https://github.com/berkinet/OpenSprinkler-Firmware/blob/41956f12fa4beae98b0fb8643cf8191823844091/OpenSprinkler.cpp#L1560

## Existing LinkTap Indigo plugin

The owner reports the bridge works; repository documentation records confirmed end-to-end OS→Indigo→LT start/stop. Source inspection shows:

- Static HTTP on/off callbacks identify the configured bridge and OS station.
- Listener validates routing and authorization; work is handled separately from the HTTP response path.
- The bridge reads OS /jc and uses active station bits plus remaining runtime and run identity.
- It subtracts request-processing delay before issuing a timed LT start.
- Duplicate start attempts are tracked, run deadlines are retained, and active work is reconciled against OS status. Uncertain starts lead to stop handling rather than blind repeated starts.
- Gateway acceptance is distinguished from reported valve activity.

Keep this integration intact. Reuse its contract concepts for RM translation, without expanding into RM queue/history management or duplicating Irrigation Monitor.

Architectural clarification: OS owns scheduling, but the existing LT execution path depends on the Indigo plugin. “Indigo is supervisory” must not be interpreted as “LT watering continues without Indigo.” Moving that execution dependency elsewhere would be separate scope, not an implicit change to this project.

## ETo input path

Firmware weather.cpp requests the configured weather service using weather method, location and options. Its callback consumes scale for the conventional watering percentage and retains rawData as wt_rawData, exposed as wtdata by the API. The live revision-2 response already includes separate ETo and precipitation.

The reviewed weather service calculates reference ETo in inches/day, then subtracts precipitation and divides by baseline ETo to produce watering percentages. Percentages are rounded/clipped (and additional scales represent rolling averages). rawData.eto retains the first day’s ETo before precipitation subtraction; rawData.p is separate precipitation.

For a depletion ledger, use ETo and rainfall separately, convert units explicitly, apply the zone crop coefficient and effective-rain policy once, and avoid applying the ordinary weather percentage again to the planned refill runtime. The percentage is not a lossless substitute for the underlying balance inputs.

The current source also includes /weatherSensorData with historical h.at, h.eto and h.p fields and separate forecast data. This is a candidate for a dated input contract, not proof that the configured hosted service exposes that revision. The legacy rawData payload alone does not establish the source weather day. Dates, freshness, duplicate-day handling and missed-day recovery must be specified before persistent accounting. Request-success timestamps alone do not identify a weather period.

Sources:
- https://github.com/berkinet/OpenSprinkler-Firmware/blob/41956f12fa4beae98b0fb8643cf8191823844091/weather.cpp
- https://github.com/OpenSprinkler/OpenSprinkler-Weather/blob/07b3689d80dfc03d3147f146bf1cc51e6c2f69fe/src/routes/adjustmentMethods/EToAdjustmentMethod.ts
- https://github.com/OpenSprinkler/OpenSprinkler-Weather/blob/07b3689d80dfc03d3147f146bf1cc51e6c2f69fe/src/routes/weather.ts

## Proposed implementation boundaries, not implemented

1. Weather-input adapter: dated ETo/rain observations, explicit units and freshness, persisted last-applied period, and a defined gap policy. Start with the OS service.
2. Per-zone state/model: depletion, root-zone capacity, crop coefficient, application rate/efficiency and actual-runtime adjustments.
3. Window planner: select and bound events against allowed windows and resource capacity, report infeasibility, retain deferred deficit.
4. OS integration: feed selected runs into the existing execution machinery; preserve legacy scheduling and prevent duplicate weather scaling. Audit runtime persistence and completion/cancellation events before choosing ledger hooks.
5. HTTP translation: preserve LT; implement the minimal RM start/stop translation separately after deciding its host. Do not assume RM can be configured directly as an OS HTTP destination.

## Remaining work

Confirm the intended firmware development baseline, audit the weather service’s dated input contract and recovery coverage, and design the offline model/replay interface. Select where RM translation runs. Later controlled tests should cover repeated callbacks, early stops, pauses, restart and loss of connection. No deployment or active testing is authorized by this inspection.
