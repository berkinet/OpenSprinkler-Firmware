# Current resume point — 23 September 2026

Automatic virtual watering is now implemented and installed. See
[AUTOMATIC_SIMULATION.md](AUTOMATIC_SIMULATION.md) for operation, explicit test
assumptions and failure behavior. The UI server on the dedicated test Pi hosts
an unattended reference-planner worker; Programs → Virtual watering simulation
applies browser drafts, pauses/resumes, and shows plans, virtual ON/OFF/completion,
soil balances and history. The initial run uses the nine starter drafts, 60x
virtual time, synthetic 4 mm/day ETo, no rain and an effective assumed soil
profile for blank fields. Actual browser calibration remains blank/unchanged.

Important: the worker addresses the non-forwarding fake receiver directly,
not the firmware's station queue. The ordinary controller dashboard therefore
still says System Idle. Real-time firmware integration and live OS ETo ingestion
remain unfinished. This is an interim integrated-repository simulation harness,
not a production architecture change to an external scheduler.

State/history live at `/home/codex/opensprinkler-simulation`, outside web assets.
The existing transient UI unit now has the simulation arguments documented in
AUTOMATIC_SIMULATION.md. A graceful UI-service restart pauses simulation; resume
from the app after restart. No production valves or configuration were changed.

Latest implementation commits: `da225121` (automatic simulation), `c524c216`
(browser cache-busting status requests). Tests: 13 simulator/API tests, 88
reference-engine tests, 418 browser tests; simulator/API tests also passed on
Pi Python. Live verification first observed Salad completion with one assumed
refill and Artichokes active. Subsequent live results are in DEVELOPMENT_NOTES.md.

Next: evaluate the visible automatic run, then replace synthetic weather with
the OS ETo adapter and develop capacity-verified future service planning.
Persistent production configuration and C++ dispatch remain separate milestones.
Keep the test profile/weather assumptions explicit. Do not confuse restarting
this development UI worker with commissioning real valves.

---

# Historical handoff — 22 September 2026

The owner asked to save our place and continue tomorrow. Do not start an
unattended experiment merely because this handoff exists.

## Completed and installed

Implementation commit: `1c2f0324` on `berkinet/OpenSprinkler-Firmware` master,
published and pulled onto the dedicated test Pi. The served UI module was
compared with that checkout and matched. Last checks: 416 browser tests,
88 Python tests, ESLint and diff checks passed. These checks cover editor and
offline planning behavior, not a working autonomous scheduler.

Test app: http://192.168.5.244/ (OSPI-Dev, dedicated DEMO installation).
The Programs page was visibly verified with nine drafts:

| Valve | Soil-water event, provisional minutes |
| --- | --- |
| 1 Salad | 1 |
| 2 Artichokes | 15 |
| 3 Cucumber/Zucchini | 120 |
| 4 Tomato boxes | 45 |
| 5 Strawberries | 120 |
| 6 Asparagus | 120 |
| 7 Front entry | 6 |
| 8 Pool End | 6 |

A separate Salad misting program runs conceptually every day at 12:15 for
3 minutes. It is a fixed-time draft, not an active scheduled run. No kitchen
programs were created. All starters use Normal priority, inherited default
hours, one cycle covering the event, zero soak, and a one-second minimum pulse.
Durations and cycle settings need field review; the shared soil profile is blank.

Each program chooses mutually exclusively between **Soil water balance** and
**Fixed days, times and watering duration**. Both retain priority groups,
allowed hours and cycle/soak. One soil program per valve is still enforced;
separate fixed programs may share that valve. Misting does not imply a full
soil refill. Fixed-time reservations precede flexible soil work in the current
offline prototype; priority resolves fixed-slot conflicts. This ordering remains
an implementation policy for review. Skipped fixed events are not shifted,
caught up, or automatically promoted into an extra run.

## Why automatic operation is still absent

The owner correctly pointed out that simulated watering uses no water. The
remaining obstacle is implementation, not a requirement to avoid simulated
valve commands. “Paused” in the UI is misleading if interpreted as a ready
scheduler waiting for an enable switch:

- Browser drafts are not yet consumed by a continuous controller engine.
- The Python reference engine creates conditional plans on invocation. It does
  not execute them, reconcile simulated completions, or persist run identity.
- Soil scheduling needs initial depletion, profile inputs and dated weather.
  Clearly labeled synthetic test values can support initial simulation; do not
  present them as garden measurements or overwrite owner calibration silently.
- Future-service capacity is still supplied as an assumption rather than solved.

## Next development milestone

Build an unattended, isolated simulation on the test Pi: saved configuration
feeds a scheduling loop; due pulses operate simulated valves; simulated
completion updates persistent simulation state; plans, starts, finishes and
skips are visible. Start with a bounded deterministic scenario (including
Salad misting), then exercise multi-day soil frequency and real-clock operation.
This is proposed implementation sequencing, not work already performed.

Account for restart/retry event identity, no double refill, same-valve conflicts,
cycle/soak, priority and hard watering windows. Keep synthetic weather/profile/
initial-state assumptions visible. The eventual architecture remains integrated
OpenSprinkler scheduling; any temporary Python simulation harness is not a
replacement decision to build an external production scheduler. Start the real
weather integration with the OS ETo service as previously agreed.

Keep the test build's `DEMO` + `DEMO_VALVE_SIM_ONLY` isolation. Numbered HTTP
station routes point only to `127.0.0.1:18080/sim/zoneN/...`; no production bridge
credentials belong in test routes or published documentation. Production OS,
RainMachine and real valves remain outside the modification/operation scope.

## Deployment details to retain

- Pi source: `/home/codex/OpenSprinkler-Firmware`.
- Controller data: `/home/codex/opensprinkler-demo`.
- Served UI: `/home/codex/opensprinkler-ui/scheduling-v1` (port 8081).
- Private initial seed: `js/soil-starter-programs.json` under the served UI.
  Preserve this file when replacing packages. It seeds each browser once,
  preserves edited programs/settings, and backs up the preceding browser draft.
  Subsequent edits are still browser-local, not synchronized between browsers.
- Prior UI backup: `/home/codex/irrigation-build-records/before-fixed-programs`.
- DEMO and valve-simulator services use transient systemd units; stopping them
  removes their definitions. See TEST_PI_SETUP.md before changing services.
- Last observed UI: System Idle, global new mode selected, automatic runs absent.
  No new valve commands or service changes were performed when saving this note.
