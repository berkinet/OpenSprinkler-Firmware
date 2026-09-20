# Project instructions

Read README.md, ARCHITECTURE_DECISIONS.md, DISCUSSION_HANDOFF.md and DEVELOPMENT_NOTES.md before continuing. Preserve the distinction between inspected source behavior, vendor documentation, hypotheses and proposed changes.

The current direction is an integrated OpenSprinkler scheduling-engine fork serving LinkTap and RainMachine valves. This supersedes the original requirement that RainMachine itself remain the autonomous scheduler. Indigo remains supervisory. Use different configurations of the existing OS HTTP zone type; do not add a new zone type. Start with the OS ETo service and offline validation.

Controller work is read-only until the owner explicitly changes that boundary: do not modify, delete, install, restart or replace anything, and do not copy controller files until the owner approves that next step. Do not execute/import controller application modules merely to inspect them. Local research notes and code experiments must not operate valves or alter controller state. Disabling RainMachine programs is a future commissioning action, not current authorization.

Use zsh on the owner's Mac unless another shell is required. The owner performs local application installation, upgrades and configuration unless explicitly delegated. Global publication authorization does not override controller restrictions. The owner has authorized creation of the project repository, background documentation and an OpenSprinkler fork.
