# Dedicated test Pi — 21 September 2026

For the subsequently installed Scheduling section and locally hosted UI, see
[UI development and deployment](UI_DEVELOPMENT.md). The build baseline below
records the earlier unmodified DEMO build.

The owner authorized installing dependencies, cloning the fork and building on a
new, dedicated Raspberry Pi 3B+ named `OSPI-Dev` (`192.168.5.244`, user `codex`).
This development-machine authorization does not change the read-only boundary
for the production OpenSprinkler, RainMachine or LinkTap systems. No production
configuration or credentials are needed for this baseline build.

## Observed environment

- 64-bit ARM (`aarch64`); `/etc/os-release` reports Debian 13.7, Trixie.
- GCC/G++ 14.2.0; Python 3.13.5; GitHub CLI 2.46.0.
- GitHub CLI authentication is configured separately on the Pi. Git uses HTTPS
  with the CLI credential helper. Do not put tokens in this repository.
- Repository: `/home/codex/OpenSprinkler-Firmware`.
- Build baseline: `75ab770d6cd777adc50deca5f355701191e97e8a`, OpenSprinkler
  firmware 2.2.1 (5), with all submodules checked out at their pinned revisions.
- Build records: `/home/codex/irrigation-build-records/75ab770/`.

## Reproduce the build

Run these commands on the test Pi. They are compatible with Bash (the Pi shell)
and zsh. The compile command follows the DEMO branch of upstream `build.sh`,
with shell globs in place of its intermediate file lists.

```sh
sudo apt-get install -y build-essential libmosquitto-dev libssl-dev
git clone --recurse-submodules https://github.com/berkinet/OpenSprinkler-Firmware.git
cd OpenSprinkler-Firmware
git checkout 75ab770d6cd777adc50deca5f355701191e97e8a
git submodule update --init --recursive --checkout

python3 -m unittest discover -s tools/irrigation_replay/tests -v

g++ -o OpenSprinkler -DDEMO -DSMTP_OPENSSL -std=c++14 \
  -include string.h -include cstdint \
  main.cpp OpenSprinkler.cpp program.cpp opensprinkler_server.cpp \
  utils.cpp weather.cpp gpio.cpp mqtt.cpp notifier.cpp smtp.c \
  RCSwitch.cpp ads1115.cpp sensors/*.cpp \
  -Iexternal/TinyWebsockets/tiny_websockets_lib/include \
  external/TinyWebsockets/tiny_websockets_lib/src/*.cpp \
  -Iexternal/OpenThings-Framework-Firmware-Library/ \
  external/OpenThings-Framework-Firmware-Library/*.cpp \
  -lpthread -lmosquitto -lssl -lcrypto

file OpenSprinkler
ldd OpenSprinkler
```

Install packages using sudo, then compile as `codex`. The stock build script
also contains service installation and legacy service removal steps; invoking
the compile command directly keeps this task limited to building.

## Validation and next stage

All 32 offline scheduler tests passed on this Pi. The reference scheduler remains
a separate Python prototype; it has not yet been integrated into the firmware.

The DEMO build succeeded without compiler diagnostics. `file` identified the
binary as a 64-bit ARM executable, and `ldd` resolved all shared libraries.
The binary is `/home/codex/OpenSprinkler-Firmware/OpenSprinkler`, with SHA-256
`8b4b07ca45acc26035634f8dd41aa80c677428ddcd0cff5f0e19e5ebf769807a`.
The checkout was clean after compilation. No OpenSprinkler process or startup
service was launched by this build task.

## Subsequent authorized startup and simulated valve configuration

The owner subsequently requested startup and simulated valve testing. The DEMO
server now runs as `codex`, using `/home/codex/opensprinkler-demo` for its data.
Its transient systemd unit is `opensprinkler-demo.service`; it has only
`CAP_NET_BIND_SERVICE` to bind the DEMO build's fixed port 80. The page is
http://192.168.5.244/ and password checking is disabled at the owner's request.
The `/jo` response reports firmware 221, minor 5 and DEMO hardware 255.

The loopback-only [valve simulator](../../tools/valve_sim/README.md) runs as
`codex` in transient unit `opensprinkler-valve-sim.service`, listening on
`127.0.0.1:18080`. Stations 1 and 2 are `SIM LinkTap` and `SIM RainMachine`,
configured as ordinary HTTP zones pointing to this receiver. Stations 3–8 are
disabled; no scheduled programs or master stations are configured.

Both units survive SSH disconnects but are not enabled to start after reboot.
These commands recreate them after a reboot, from a shell on the test Pi:

```sh
sudo systemd-run --unit=opensprinkler-valve-sim --uid=codex \
  --property=NoNewPrivileges=yes \
  /usr/bin/python3 /home/codex/OpenSprinkler-Firmware/tools/valve_sim/receiver.py \
  --log /home/codex/opensprinkler-demo/simulated-valves.jsonl

sudo systemd-run --unit=opensprinkler-demo --uid=codex \
  --property=WorkingDirectory=/home/codex/opensprinkler-demo \
  --property=AmbientCapabilities=CAP_NET_BIND_SERVICE \
  --property=CapabilityBoundingSet=CAP_NET_BIND_SERVICE \
  --property=NoNewPrivileges=yes \
  /home/codex/OpenSprinkler-Firmware/OpenSprinkler \
  -d /home/codex/opensprinkler-demo
```

Inspect status using `systemctl status opensprinkler-demo opensprinkler-valve-sim`.
Request logs are in the simulator's journal; command events append to
`/home/codex/opensprinkler-demo/simulated-valves.jsonl`.

DEMO avoids OSPi GPIO output but still supports real outbound HTTP requests:
only simulated destinations should be configured for this stage. The standard
firmware scheduler runs the timed commands; the new depletion planner is still
an offline prototype, with test-driver sequencing for its cycle-and-soak plan.

### Observed simulated-valve results

The guarded exercise passed on 21 September 2026:

- Both zones' four-second runs produced ON and OFF callbacks about 4.001 seconds
  apart, with automatic queue completion.
- Explicit stop ended each requested 20-second run after approximately 1.04 and
  1.07 seconds respectively.
- Zone A's five one-minute planner pulses were exercised at 20× speed on
  `SIM LinkTap`: each requested three-second pulse measured 2.996–3.004 seconds.
  All four soak intervals measured approximately four seconds, exceeding the
  scaled three-second minimum. Dispatch overhead explains the longer gaps.
- Both simulator states were OFF, station bits were clear and the queue was
  empty at completion.

The machine-readable report is
`/home/codex/irrigation-build-records/75ab770/simulated-valve-test.json`.
These results validate local HTTP command delivery and timed sequencing, not
the real vendor bridges or exact watering-window execution. The original
five-minute-ON/nine-minute-elapsed case remains an offline numerical test.

### Soil-water editor preview

The 21 September editor increment keeps the same test URL. Select Soil water
balance under Edit Options → Scheduling and save, then open Edit Programs. The
choice persists on the controller; the new program and shared-settings drafts
are stored only in the browser. Standard timed programs are suspended in this
mode. The actual soil-water scheduler remains unimplemented. See
[UI_DEVELOPMENT.md](UI_DEVELOPMENT.md) for the complete boundary and controls.
