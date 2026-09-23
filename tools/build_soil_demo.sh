#!/bin/sh
# Linux/Pi only. Build an isolated DEMO executable; no package or service changes.
set -eu
cd "$(dirname "$0")/.."
g++ -o OpenSprinkler-soil.new -DDEMO -DDEMO_VALVE_SIM_ONLY -DSMTP_OPENSSL \
  -DSOIL_SCHEDULER -DOTF_MAX_BODY_SIZE=65536 -std=c++14 -include string.h -include cstdint \
  main.cpp OpenSprinkler.cpp program.cpp opensprinkler_server.cpp utils.cpp weather.cpp \
  soil_scheduler.cpp gpio.cpp mqtt.cpp notifier.cpp smtp.c RCSwitch.cpp ads1115.cpp sensors/*.cpp \
  -Iexternal/TinyWebsockets/tiny_websockets_lib/include external/TinyWebsockets/tiny_websockets_lib/src/*.cpp \
  -Iexternal/OpenThings-Framework-Firmware-Library external/OpenThings-Framework-Firmware-Library/*.cpp \
  -lpthread -lmosquitto -lssl -lcrypto
