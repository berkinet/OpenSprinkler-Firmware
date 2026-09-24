# Reserved periods for external control

Under Programs → Add, select **Reserve time for external control**. Enter a
name, weekdays, start time(s), and reserved duration. Save the draft, then apply
it through Firmware watering as with other new-mode programs. No valve, soil
profile, water amount, priority or cycle/soak settings apply to this option.

The owner selected this approach for Indigo-managed pool refill. Indigo keeps
deciding whether to fill and directly operates its RainMachine valve within the
agreed period. OS reserves the shared water resource without sending any valve
commands or crediting soil water. Indigo is responsible for closing its valve
before the period ends; OS has no direct evidence of that external valve's state.
No actual pool-refill hours have been chosen or enabled by this implementation.

## Scheduling behavior

- Reservations are mandatory and take precedence over every watering priority.
  They are independent of watering restrictions, excluded irrigation dates,
  soil inputs and weather. A disabled reservation has no effect.
- The station transition delay is added before and after the reserved period
  (at least one second in the firmware planner). Irrigation pulses must fit
  entirely outside the resulting blocked interval.
- Flexible soil events may be split around the interval while retaining their
  required ON duration and soak separation. An event that cannot fit follows
  existing shortage rules. A conflicting fixed-time event is skipped and
  reported as `external_reservation`, with no late catch-up.
- Overlapping reservations combine their blocked intervals; neither is skipped.
- Weekdays refer to the start day. Durations are elapsed time, up to 24 hours;
  overnight continuation remains reserved on the following day. Replanning and
  restarting inside a period retain the block from the preceding day.
- At an ambiguous daylight-saving start, both occurrences are covered, which
  lengthens the reservation. A nonexistent start advances to the next valid
  minute. Indigo's timing must use a compatible policy.

## Firmware enforcement and scope

Draft schema 5 adds `scheduleMode: reservation` programs with `reserved:` IDs,
`name`, `enabled`, `days`, `times` and `duration` (minutes). Previous schemas and
programs remain supported. The shared planner returns dated reservations as
report data, never as executable valve events. The firmware panel displays the
next 24 hours of reservations and their transition margins.

In Soil water balance mode the firmware checks the entire native station queue,
including manual and run-once requests. A conflicting request is cancelled and
logged as blocked; it is not moved to another time. The legacy manual endpoint
may acknowledge queue submission before this check, so that response alone
does not promise watering. This is not the deferred-request API discussed as
an alternative design. STOP operations remain available.

After changing reservation configuration, absent/expired calendar coverage
blocks watering until a valid plan is available. Pausing the scheduler does
not bypass saved reservations. The Standard scheduling mode does not use these
new-mode programs. The current integration remains Pi DEMO-only with simulated
outputs; real bridge commissioning is separate.

Tests cover blocked soil/fixed pulses, transition gaps, overlap, overnight
restart, DST, strict valve-free schema, disabled reservations, independence from
soil/weather inputs, firmware interval guards and editor persistence. No Indigo
automation is edited by this feature.
