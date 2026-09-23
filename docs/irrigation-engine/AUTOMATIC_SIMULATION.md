# Automatic virtual watering — 23 September 2026

This is an automatic **laboratory simulation**, using the current Python
reference planner and the existing loopback fake-valve receiver. It is an
interim integration harness in this repository, not production firmware
scheduling or a decision to move the production scheduler outside OpenSprinkler.
It sends no OpenSprinkler valve commands and has no LinkTap/RainMachine adapter.
Consequently the ordinary controller dashboard can remain System Idle while
virtual valves are running; use the simulation view for their status.

## Use from the dedicated test Pi app

Open Programs → **Virtual watering simulation** (also the new-mode Preview
page). The view shows virtual time, speed, active virtual valve, plan decisions,
per-valve soil depletion and recent planned/ON/OFF/completed/skipped events.

- **Apply saved drafts to simulation** copies this browser's saved configuration
  to the test Pi and starts it. Unsaved form edits are not included. Applying
  unchanged content is idempotent. Later browser edits do not silently change
  the running copy; apply them explicitly. Changes interrupt any current event,
  without full-refill credit, and replan using retained balances.
- **Pause simulation** stops active fake valves and freezes the virtual clock.
  An interrupted runtime event is not credited as a full refill.
- **Resume simulation** continues the saved simulation. It reconciles fake valves
  first; it does not replay an interrupted event or catch up downtime.

The simulation does not need the browser open. The UI server hosts its worker.
The first deployment uses a **60x virtual clock**: approximately one simulated
minute per real second, slowing if necessary to process events individually.
Whole days take approximately 24 real minutes. Fixed starts follow that virtual
local clock, not the real wall-clock time displayed on the main OS dashboard.

## Explicit test inputs

- Synthetic ETo: 4 mm/day, distributed uniformly; no rain. **No live weather feed**.
- Blank profile fields use an effective test copy: capacity 100 mm/m, roots
  0.3 m, depletion 50%, crop coefficient 1, effective rainfall 80% (unused with
  no rain). Nonblank profile fields are preserved. The UI identifies assumed
  fields. Browser drafts and field calibration are not overwritten.
- New soil balances start at the depletion threshold, not an assertion about
  actual garden moisture. Subsequent balances follow elapsed simulated ETo.
- Initial timezone Europe/Paris. Private test-Pi location supports night hours;
  it is not part of the public sample configuration.
- One active fake valve, five seconds of virtual transition time. Priority,
  hard restrictions, cycle/soak and fixed-time conflicts use the reference engine.
- A future service time is the next allowed opportunity at least 24 hours later,
  searched up to eight days ahead. It is **not a capacity-verified reservation**.
  No opportunity blocks simulation rather than inventing a watering window.
- This first automatic harness accepts report-only shortage handling. It rejects
  promotion mode visibly until persistent promotion semantics are implemented.

A completed full runtime event resets that valve's simulated depletion once.
Individual pulses and interrupted events never imply full refill. Fixed misting
never resets the soil balance. Calibrated depth events credit completed pulse
seconds at the configured net application rate. This harness uses end-of-pulse
credits, not an assertion of measured physical delivery.

## Persistence and failure behavior

The separate simulation directory contains `state.json` and append-only
`history.jsonl`, outside the served asset directory. Configuration, decisions,
active intent, OFF/completion transitions and refill credit are saved atomically.
Idle clock/balance checkpoints occur at most every ten real seconds to limit SD
writes. After an abrupt restart the virtual clock resumes its latest checkpoint;
it can roll back that uncheckpointed interval. It does not advance through
service downtime. A pending ON intent is treated as interrupted, stopped, and
not replayed. Completed refill state is restored without reapplying the credit.

A changed receiver session or unexpected fake-valve state pauses simulation with
an error. Service shutdown stops the runner and fake valves and saves a paused
state. Resume explicitly after a graceful service restart. History is durable;
the UI shows the latest 30 records, and the in-memory status retains 500.
No real valve recovery guarantees are implied by these fake-receiver tests.

## Deployment

Extend the existing UI asset server invocation with:

```
--simulation-directory /home/codex/opensprinkler-simulation
--controller-origin http://192.168.5.244
--simulation-speed 60
--simulation-timezone Europe/Paris
--simulation-location /home/codex/opensprinkler-simulation-location.json
```

The optional location JSON contains `latitude` and `longitude`. The UI remains
on port 8081. Read-only status is `/simulation/status`; JSON POST endpoints
`/simulation/config` and `/simulation/control` accept only the configured browser
Origin. This is a LAN development service, not production authentication.

The output adapter has a literal `127.0.0.1:18080` target, disables proxies and
redirects, validates fake-receiver identity and addresses only numbered fake
zones. It cannot configure a remote URL or route to the real valve bridge.
The separate DEMO firmware's loopback guard remains unchanged.

Tests: `python3 -m unittest discover -s tools/valve_sim/tests -v`, plus the
existing irrigation-replay and browser suites. API tests bind an ephemeral
loopback HTTP port. Existing offline tests remain free of controller I/O.
