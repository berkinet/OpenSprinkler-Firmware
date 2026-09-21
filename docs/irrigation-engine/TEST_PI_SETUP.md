# Dedicated test Pi — 21 September 2026

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

The next stage is an isolated runtime configuration and local simulated HTTP
valve receiver, followed by startup/API and timed-valve tests. DEMO avoids OSPi
GPIO output but still supports real outbound HTTP requests: only simulated
destinations should be configured for this stage. A successful build alone
does not validate runtime behavior or physical valve operation.
