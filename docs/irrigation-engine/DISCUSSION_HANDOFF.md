# Discussion handoff — 20 September 2026

This is a substantive summary of today's RainMachine discussion from the Chicken cage door management task, not a verbatim transcript. The original conversation remains in task [private task identifier omitted]. The owner explicitly requested moving this work to the newly created Irrigation Engine Replacement project and will continue here.

## Owner's request and boundaries

The owner asked to pull the latest RainMachine2 repository, read DEVELOPMENT_NOTES.md, connect by SSH, and inspect the OS, Python version, filesystem and application modules. Initially read-only: do not modify, delete, install, restart or replace anything on the controller. Copy nothing until findings have been reviewed. A later request authorized deeper in-place inspection and public research; it did NOT authorize downloading the controller application or changing it. No controller file has been copied. This handoff copies only our existing local development notes.

The main objective is a more Rachio-like irrigation algorithm running autonomously on RainMachine: use soil-water depletion to vary watering frequency rather than extending every scheduled runtime, and address collisions/overruns between watering programs. Indigo must remain supervisory; irrigation must not depend on Indigo or another external scheduler.

The owner then asked for deeper investigation of actual RainMachine internals, public modification projects, and documentation or actual code implementing Rachio scheduling. That investigation is complete at the initial source-tracing level; details and evidence are in DEVELOPMENT_NOTES.md. The owner responded positively and requested this project handoff. No replacement implementation or deployment has been authorized yet.

## Connection and inspected environment

- Controller: RainMachine Touch HD-16. Inspected through owner-authorized read-only access. Connection and authentication details are omitted from public documentation.

- Android 4.3 / API 18, Linux 3.2.0 ARMv7, Python 2.7.8.
- /rainmachine-app points to /system/rainmachine-app; /system, /data and /cache are ext4; /tmp is RAM-backed.
- Frameworks include ordinary readable .py source plus .pyc bytecode. Source inspection used python -B -S and standard-library parsing; never imported or ran application modules.
- RMSimulatorFramework: 3 source/bytecode pairs; RMProgramsFramework: 10; RMParserFramework: 22 including parsers; RMUtilsFramework: 16.

## Key conclusions discussed

1. RainMachine already computes ET/weather demand, reconciles forecast versus observed conditions and carries water surplus/deficit.
2. Adaptive Frequency suppresses small variable-duration runs and carries deficit to the next configured scheduling opportunity. It is not equivalent to a fixed refill event triggered by a physical per-zone depletion threshold.
3. The misleadingly named getFieldCapacity method already includes allowed depletion; the Adaptive Frequency condition then compares against half of that amount. See source references in notes.
4. Water carryover is keyed by program AND zone. A replacement needs careful accounting across multiple programs, manual irrigation and interrupted/partial runs.
5. Automatic work enters an ordered queue with default concurrency one. Delayed runs retain calculated runtime; restriction logic is not a global capacity/soil-urgency planner.
6. Separate the future design into a per-zone depletion decision and a watering-window capacity planner. Frequency changes alone cannot guarantee enough capacity on high-demand days. Preserve manual control, valve sequencing, safety restrictions and autonomous fallback.
7. Preferred next technical work is an offline model/replay before any controller change; access/copying for that must be agreed first.

## Public research discoveries

- Important correction to the original notes: https://github.com/aroberts/rainmachine-rpi contains a public Python 3 port of firmware 4.0.1144 with the simulator/scheduler and Raspberry Pi GPIO integration. The inspected Adaptive Frequency branch retains the same policy. Its documentation references another clone owner, and GitHub reports no root license; verify provenance and reuse terms before adopting/distributing it. It was NOT installed or run.
- https://github.com/sprinkler/rainmachine-developer-resources provides actual ET formula, parser SDK and API examples.
- https://github.com/dataoscar/rainmachine-fixes contains a NOAA parser fix, not a replacement scheduler.
- No production Rachio Flex Daily source was found. Public Rachio documentation and a historical support explanation disclose event-depth/runtime formulas and moisture-based scheduling behavior. Treat historical formulas as evidence, not a complete current specification.
- https://github.com/kthorp/pyfao56 is actual independent FAO-56 water-balance/automatic-irrigation source, not Rachio code. Useful as an offline reference; not a drop-in Python 2.7 controller library.
- Full URLs, line references, caveats and proposed architecture are in DEVELOPMENT_NOTES.md.

## Local project history and preferences

RainMachine2 was pulled from berkinet/RainMachine2 main to b78714a, then the research notes were committed/pushed as 40911ad. Its directory is /Users/OWNER/Documents/Codex/RainMachine2. Existing untracked .DS_Store files were untouched. The initial handoff used a byte-identical copy of DEVELOPMENT_NOTES.md. Public documentation may redact local identifiers; the original remains in RainMachine2 development history.

Owner uses zsh on this Mac unless another shell is required; this was added to /Users/OWNER/.codex/AGENTS.md today. The remote Android shell is a separate environment. Owner prefers doing local application installations/configuration personally. Standing commit/push/publication authorization does not override the explicit controller read-only/no-copy boundary. No new GitHub repository has been requested for this project.
