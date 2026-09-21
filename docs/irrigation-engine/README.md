# Irrigation Engine Replacement

Research and design an optional soil-depletion scheduling mode and watering-window capacity planner integrated into OpenSprinkler. The proposed architecture makes OS the scheduling authority for LinkTap and RainMachine valves, with Indigo supervisory.

## Scheduling design

- [Scheduling specification, draft 1](SCHEDULING_SPEC.md) — agreed policies, proposed defaults and integration boundaries
- [Offline replay plan](REPLAY_PLAN.md) — acceptance scenarios and numerical examples
- [Dedicated test Pi setup](TEST_PI_SETUP.md) — environment and reproducible DEMO build
- [UI development and scheduling mode](UI_DEVELOPMENT.md) — integrated UI source and test deployment
- [Configuration-to-engine integration](ENGINE_INTEGRATION.md) — executable draft-to-plan path, field mappings and runtime gaps
- [Application-rate presets](APPLICATION_PRESETS.md) — direct entry, equipment types and university/manufacturer sources

The [offline reference model](../../tools/irrigation_replay/README.md) now accepts
the actual browser draft format and explicit runtime snapshots. Multi-window
service-horizon planning and firmware integration remain to be built. Both
scheduling modes are selectable on the test Pi; Soil water balance opens the
editor preview and keeps automatic watering paused.

## Background and decisions

- [OS, LinkTap bridge and ETo integration findings](INTEGRATION_FINDINGS.md)
- [Current architecture and discussion decisions](ARCHITECTURE_DECISIONS.md)
- [Original RainMachine research handoff](DISCUSSION_HANDOFF.md)
- [Historical development notes and source inspection](DEVELOPMENT_NOTES.md)
- [Project working instructions](AGENTS.md)

The historical notes originally required autonomous scheduling inside RainMachine. The later discussion supersedes that design constraint with the proposed OS master scheduler. Controller access restrictions remain unchanged.

## Repositories

- Project and firmware fork: https://github.com/berkinet/OpenSprinkler-Firmware
- Firmware upstream: https://github.com/OpenSprinkler/OpenSprinkler-Firmware
- Existing LinkTap bridge: https://github.com/berkinet/OpenSprinkler-LinkTap-Bridge
- Existing Irrigation Monitor: https://github.com/berkinet/Indigo-Irrigation-Monitor-Plugin
- UI source imported into this repository: [ui/](../../ui/README.md), based on https://github.com/OpenSprinkler/OpenSprinkler-App

Current phase: offline prototype and dedicated test Pi setup. Use different configurations of OS's existing HTTP zone type; do not introduce a new zone type. Begin with the OS ETo service and offline validation. Installation and builds on the new test Pi are authorized; production controller changes and file copying remain unauthorized.

This project is public to support review and collaboration with OpenSprinkler developers. Local infrastructure identifiers in the historical handoff have been replaced with placeholders. It contains authored research, not exported controller source.
