#!/bin/sh
# Linux/Pi only. Build an isolated DEMO executable; no package or service changes.
set -eu
cd "$(dirname "$0")/.."
exec make -f tools/soil-demo.mk -j "${SOIL_BUILD_JOBS:-2}"
