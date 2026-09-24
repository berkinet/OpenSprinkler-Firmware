# RainMachine zones on the test Pi — 24 September 2026

The owner requested adding RainMachine-managed zones to the development system.
The Indigo Irrigation Monitor repository contains connection logic, not a saved
zone export. Its local Indigo preferences and RainMachine device supplied the
existing connection settings. Read-only `zone` and `zone/properties` API queries
confirmed sixteen active, non-master zones, with UID equal to valve ID.
No RainMachine programs, settings or outputs were changed.

The test Pi now exposes 32 stations (`ext=3`). Existing stations 1–16 retain
their names, settings and numbers, including disabled kitchen/spare slots.
RainMachine UID N maps to OS station 16+N, with an `RM ` name prefix:

| RM valve | OS station | Name |
| --- | --- | --- |
| 1 | 17 | Front of House |
| 2 | 18 | Drip loop 2 (Street) |
| 3 | 19 | Laundry Gate |
| 4 | 20 | Top Restanque |
| 5 | 21 | Kitchen Restanque |
| 6 | 22 | Below Pool |
| 7 | 23 | Drip Loop 1 (Inside) |
| 8 | 24 | Pool Lawn |
| 9 | 25 | Bergerie Lawn |
| 10 | 26 | Parking Area |
| 11 | 27 | Pool Refill |
| 12 | 28 | Restanque 1 (entry) |
| 13 | 29 | Restanque 2 (center) |
| 14 | 30 | Restanque 1 & 2 |
| 15 | 31 | Restanque 1b |
| 16 | 32 | Restanque 2 (wall) |

All new stations are enabled HTTP stations, sequential group A, no masters,
with ordinary rain/sensor handling. Station N points only to
`127.0.0.1,18080,sim/zoneN/on,sim/zoneN/off`. The fake receiver service's runtime
override now uses `--zones 32`. These are simulated stand-ins, not a commissioned
RainMachine bridge. All 32 routes and types were verified by API readback.

No RainMachine programs or soil calibration were imported. The existing nine
programs, site baseline, configuration revision 4 and eight refill records were
preserved. Automatic scheduling was paused while idle and resumed afterward.
Pool Refill needs an appropriate fixed/manual policy rather than a soil-refill
assumption when programs are added. Other new program durations remain to be set.

Private backup on the Pi:
`/home/codex/irrigation-build-records/before-rm-zones-20260924T103021Z`.
The credentials-free mapping is also stored privately as
`/home/codex/irrigation-build-records/rainmachine-zone-mapping.json`.
The backup includes the previous receiver override and controller data.

Import detail: station special flags must be enabled in the same request as,
or before, writing HTTP station types; otherwise `attribs_save()` resets the
type to standard. Readback caught this and the new station types were rewritten
after setting the flags, before resuming the scheduler.
