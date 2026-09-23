# Pi firmware scheduling integration

The `SOIL_SCHEDULER` build makes the OpenSprinkler process own the new schedule,
configuration, execution journal and ordinary station queue. It uses real UTC
time, with controller-local time conversion only at the queue boundary. The
earlier accelerated Python simulation service is not the dispatcher in this mode.

This first integration is deliberately compiled only with `DEMO` and
`DEMO_VALVE_SIM_ONLY`. Each eligible HTTP station must have its exact numbered
loopback simulator route. It cannot be built as a real-valve controller without
further development. Standard builds retain no-op hooks and their existing
scheduler. No new station type has been introduced.

## Components and persistence

- `soil_scheduler.cpp`: firmware-loop adapter, asynchronous planner invocation,
  controller/sensor gating, station queue dispatch and fake-receiver verification.
- `soil_runtime.hpp`: atomic, fsynced configuration and execution checkpoints,
  intent before ON, per-event identity, cycle/soak readiness and completed delivery.
- `tools/firmware_scheduler/worker.py`: one-shot planning component launched by
  firmware, using the existing tested reference planner. It fetches OS weather
  and returns a plan; it has no valve/control API. This Pi implementation requires
  `/usr/bin/python3` and the source tree beside the firmware executable. Porting
  to embedded ESP targets remains future work; this is not a native C++ rewrite
  of the allocation algorithm.

`soil-state.json` resides in the controller's `-d` data directory. The private
worker request includes the existing weather service/options/location; these
are not returned in the scheduler status API. Its result is accepted only if
the state revision still matches. Configuration revision checks protect against
stale editor writes. A corrupted checkpoint blocks scheduling.

The UI keeps browser drafts as an editing/staging area. **Programs → Firmware
watering** loads or saves controller configuration explicitly. Saving pauses
the new engine; Resume activates it. Loading controller programs backs up the
previous browser drafts. Site input changes require an explicit new soil
baseline; changing program settings alone preserves the existing baseline.

The firmware invokes the planner when idle, at most once per minute, and retains
an event's remaining cycles while it runs. It does not launch a worker within
25 seconds of a known pending start, so weather latency/replanning cannot erase
an imminent fixed reservation. It uses one active valve resource.
Current fixed-event reservations retain the reference planner's priority and
restriction rules. Native Stop All, queue pause, disabled-controller state and
sensor restrictions cannot bypass the new dispatcher's stop handling. An
interrupted soil event gets no assumed full refill and requires reconciliation
before that valve can receive another soil allocation. Fixed misting never
implies a refill.

The fake receiver's small `/state` response confirms ON/OFF and its session
identity; active state is checked every five seconds. Receiver restart or
unexpected output pauses the engine. These are simulator acknowledgements,
not evidence of actual field water delivery.

Its HTTP response is collected across TCP fragments and checked against the
declared length. The initial live test exposed the old single-read assumption;
that pulse stopped immediately and received no refill credit. The corrected
live test completed three two-second soil pulses followed by a separate
three-second fixed mist, with exactly one assumed refill in the journal.

## Real OS weather, with explicit estimation

The adapter calls the controller-configured OS service's
`/weatherSensorData?scope=h` endpoint. The vendor's
[API documentation](https://github.com/OpenSprinkler/OpenSprinkler-Weather/blob/master/docs/api.md)
defines version 1, `u:us`, historical timestamp `h.at`, daily `h.eto` and `h.p`.
Inches are converted to mm exactly once, multiplying by 25.4. The accepted daily
period must start at local midnight in the named site timezone; DST changes
therefore produce 23- or 25-hour periods correctly.

Successful observations are stored by period start. Reconciliation replays
dated weather and completed watering from the explicit initial soil baseline,
so repeated responses or revised daily values cannot add the same rain/ETo
twice. Missing completed days, missing fields, unexpected units or stale data
block soil allocation. They do not invent zero ETo/rain.

Today's ETo and future planning ETo repeat the latest observed daily rate and
are labeled **estimates**. Today's rain is not credited until the completed-day
observation arrives. Daily amounts are distributed uniformly within their
period, an explicit modeling assumption rather than a measured rain timeline.
Fixed-time programs remain independent of missing soil/weather inputs, while
physical delivery uncertainty still applies to that valve.

On the dedicated Pi, inspection found `provider:AW` with no key, producing OS
weather error 35. A read-only probe using the default provider successfully
returned dated Apple ETo and rainfall. Removing that invalid provider selection
uses the existing hosted OS weather service; it does not require a new account.

## Remaining limits

- Soil capacity/root depth and initial depletion are field inputs. Blanks remain
  unknown. An explicit test-only provisional option can fill blank soil fields
  and initialize at the depletion threshold; it must not be described as garden
  measurements. Imported minutes remain provisional event durations.
- Future service opportunities are legal-window assumptions, not reservations
  verified against future competition. Capacity-verified multi-window planning
  remains unfinished.
- Automatic promotion of skipped soil zones is not connected; selecting it
  yields a visible error. Report-only shortage handling is supported.
- Master outputs are blocked in this initial integration. Real HTTP bridge
  acknowledgements, field commissioning and embedded portability remain separate.
- The historical endpoint supplies a recent day, not an arbitrary backfill.
  Extended outages with missing complete days require explicit reconciliation.
- Delivery journals are bounded at 10,000 records; long-term checkpoint
  compaction/retention is still needed before sustained production use.
- Native queue pause cancels remaining new-model cycles instead of moving them
  outside their approved windows. Resume the firmware scheduler explicitly.
- Existing Pi services are transient systemd units. The controller data survives
  restart, but the units still need recreation after a full Pi reboot; automatic
  boot-service installation is a separate environment task.

## Build and checks

On the Pi, use POSIX `sh tools/build_soil_demo.sh`. This only compiles the
candidate `OpenSprinkler-soil.new`; it installs no packages and changes no
services. Keep the pinned external dependencies initialized. The production
upstream build script is not used to reconfigure the Pi.
The Makefile caches dependency-tracked objects and uses two compiler jobs by
default; `SOIL_BUILD_JOBS=1 sh tools/build_soil_demo.sh` reduces memory demand.

Local zsh commands from the repository root:

```zsh
c++ -std=c++14 tools/firmware_scheduler/test_runtime.cpp -o /tmp/test-soil-runtime
/tmp/test-soil-runtime
python3 -m unittest tools.firmware_scheduler.test_worker
python3 -m unittest discover -s tools/irrigation_replay/tests
```

The C++ tests exercise durable completion, no credit for incomplete cycles,
restart and interruption behavior, stale planner rejection, occurrence identity,
depth credit and fixed misting. Weather tests cover units, missing/stale fields,
DST period lengths, revisions, no forecast rain credit and fixed/soil separation.
