# Irrigation Engine Replacement

Research and design an optional soil-depletion scheduling mode and watering-window capacity planner integrated into OpenSprinkler. The proposed architecture makes OS the scheduling authority for LinkTap and RainMachine valves, with Indigo supervisory.

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
- Separate upstream UI (not yet forked): https://github.com/OpenSprinkler/OpenSprinkler-App

Current phase: research and design. Use different configurations of OS's existing HTTP zone type; do not introduce a new zone type. Begin with the OS ETo service and offline validation. No controller deployment or file copying is authorized.

This project is public to support review and collaboration with OpenSprinkler developers. Local infrastructure identifiers in the historical handoff have been replaced with placeholders. It contains authored research, not exported controller source.
