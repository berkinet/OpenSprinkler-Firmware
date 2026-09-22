# Local DEMO valve receiver and exercise

These Python standard-library tools are for the dedicated test Pi. The receiver
has no valve hardware, vendor credentials, forwarding or vendor API support.
It models two boolean valve states and records commands; its `lt` and `rm`
labels distinguish test zones, not working LinkTap or RainMachine adapters.

## Receiver

```sh
python3 tools/valve_sim/receiver.py --log /home/codex/opensprinkler-demo/simulated-valves.jsonl
```

It binds only `127.0.0.1:18080`. HTTP GET endpoints:

- `/sim/lt/on`, `/sim/lt/off`
- `/sim/rm/on`, `/sim/rm/off`
- `/status`: states, session ID and the most recent 10,000 events.

Events append to the JSON-lines log with wall-clock and monotonic timestamps.
Repeated commands are recorded, with `changed=false` for duplicate states.
Restarting the receiver begins a new session with both simulated valves OFF;
this is not production recovery behavior. Requests are acknowledged promptly
without calling back into OpenSprinkler.

## Required DEMO configuration

The test controller listens on loopback port 80 (also accessible over the Pi's
LAN address). Configure station 1 as `SIM LinkTap` and station 2 as
`SIM RainMachine`, both using the existing HTTP station type:

| Station | Server | Port | ON command | OFF command |
| --- | --- | --- | --- | --- |
| SIM LinkTap | 127.0.0.1 | 18080 | sim/lt/on | sim/lt/off |
| SIM RainMachine | 127.0.0.1 | 18080 | sim/rm/on | sim/rm/off |

Disable stations 3–8. Leave master stations disabled and no scheduled programs.
The exercise validates this configuration before issuing station commands,
requires DEMO hardware identity 255, uses no HTTP proxies or redirects, and
has no configurable remote controller address. Run it while the test controller
is idle and avoid manually operating zones during the exercise.

```sh
python3 -m tools.valve_sim.exercise
```

It checks a four-second automatic run and an early explicit stop for each zone,
then reads zone A's five-pulse plan from the offline `capacity-and-soak` fixture.
The cycle test shortens each 60-second pulse and soak to three seconds (20×).
The driver waits from each **observed OFF callback** before submitting the next
pulse, so polling and dispatch overhead can extend the elapsed time. It checks
each timed pulse within 1.5 seconds and each soak is at least three seconds.
It finishes with both simulated valves off and the controller queue empty.

This is a transport and sequencing smoke test. It is not firmware integration
of the new planner, a test of strict watering-window execution, a real-time
five-minute irrigation test, or evidence of physical water delivery. The
offline model itself remains free of controller I/O. Actual LinkTap/RainMachine
bridge adapters, restart recovery and failure injection remain separate work.

## Production-shaped shadow setup

For a larger station list, start the receiver with `--zones N`. This adds
`/sim/zone1/on`, `/sim/zone1/off`, … through zone N alongside the original lt/rm
aliases. All receiver state starts OFF; no vendor APIs or forwarding exist.

The dedicated development firmware is now built with both `-DDEMO` and
`-DDEMO_VALVE_SIM_ONLY`. The latter blocks every special-station output except
plain HTTP to the literal `127.0.0.1` on port `18080`. It rejects hostnames,
HTTPS, remote controllers, RF and GPIO special stations. Normal builds are
unchanged. Run the small C++ guard test before deploying this build:

```
g++ -std=c++14 tools/valve_sim/test_guard.cpp -o /tmp/os-demo-guard-test
/tmp/os-demo-guard-test
```

`python3 -m tools.valve_sim.import_shadow /private/path/configuration.json`
imports an allowlisted, separately prepared configuration into loopback port 80.
It requires DEMO identity, soil mode, idle outputs, no existing standard programs,
and enough simulated receiver zones. Back up the test data first. It expands the
station count, temporarily disables all stations, sets and verifies loopback
routes, restores names/enable masks and adds the source standard programs.
It never copies production special-station addresses or credentials. Partial
failure requires inspection/restoration from backup, not blind rerunning.

This tool is not a general backup-file importer. The private input contains
schema=1, names, disabled masks, station groups, ignore_rain masks, standard
program arrays, source_local_epoch, timezone_offset, station_delay and location.
Interval phases are adjusted from the source snapshot's local calendar date.
The tool leaves soil mode selected and automatic scheduling paused; imported
programs remain Standard-mode reference schedules. New-engine conversion still
needs calibration and resolution of duplicate programs assigned to one valve.
The original two-valve exercise intentionally refuses this larger configuration.
