# Integrated UI source and scheduling-mode setting

## Source and maintenance

The owner requested a Scheduling section under Edit Options and a dedicated
soil-water program editor. The initial disabled alternative has now been
superseded: both modes can be selected for evaluation on the dedicated test Pi.
Soil water balance is an editor preview; its automatic engine is not integrated.

`ui/` is a squashed git subtree of
https://github.com/OpenSprinkler/OpenSprinkler-App at
`f79f9b9817ae498f8df1bf15497e1f3cd5a4e76e`. Firmware and UI changes now live in
this single repository. The UI retains its upstream AGPL-3.0 license and
attributions in `ui/LICENSE`; the firmware retains its own license. The UI's
About page links to the modified UI source in this repository.

Future upstream UI updates can be imported deliberately with:

```sh
git subtree pull --prefix=ui https://github.com/OpenSprinkler/OpenSprinkler-App.git master --squash
```

Review and test the resulting changes before deployment.

## Controller contract

- `/jo` (and the options portion of `/ja`) exposes `smode`.
- `smode=0` means Standard. Its byte is appended to the integer-option array,
  preserving previous file offsets. Older files receive the default 0.
- `/co?smode=0` and `/co?smode=1` persist Standard and Soil water balance.
- Other values, including malformed or empty input, are rejected before other
  options in the request change. Unsupported stored values normalize to 0.
- A mode change with a nonempty runtime queue is rejected before any options
  change. Stop or finish watering before changing modes.
- `ProgramStruct::check_match` returns no match in mode 1. Existing Standard
  programs, including repeated run-once entries, remain stored but cannot start
  by time. Standard resumes its normal matching when mode 0 is restored.
- Manual commands and physical program-switch commands retain their existing
  behavior. This preview is not a global valve-disable or legal-window guard.
- The UI section only appears on controllers exposing `smode`. Edit Programs,
  Add Program and Preview route according to the saved controller mode. The
  dashboard identifies mode 1 as automatic watering paused.

## Visible editor draft (21 September 2026)

One soil-water program owns one individual zone/valve; duplicate assignments,
masters, disabled stations and bundle leaders/members are excluded. Standard
program storage is separate and unchanged. The saved mode is global: the two
automatic engines do not operate alongside each other.

Edit Options → Scheduling selects the mode. Save options, then use Edit
Programs → Add (upper right). The initial Programs page uses Standard mode’s
empty-list prompt and toolbar; Add opens the soil-water editor. The form includes
a name, one valve, enabled state, the sole Garden profile, a named priority group, application rate and
efficiency, maximum cycle, minimum soak and minimum useful pulse. A five-minute
example with one-minute cycle and soak displays five pulses and nine elapsed
minutes. This timing illustration does not prescribe a fixed scheduled dose.

Shared settings are linked from Edit Options → Scheduling:
multiple weekly windows, overnight windows, excluded dates, configurable
shortage reporting/promotion and the Garden soil profile. Priority groups have
their own page in Scheduling, available when Soil water balance is saved as
the active mode.
These describe draft inputs, not operational restriction enforcement. Promotion
size remains undecided. No calibration defaults are presented as garden advice.

**Storage boundary:** Save draft writes versioned, controller-scoped browser
storage only. Drafts do not call `/cp`, survive reloads in that browser, and are
not shared across browsers or included in controller backups. Clearing browser
storage removes them. Switching to Standard preserves these drafts. Controller
persistence, migrations, water ledger and actual soil-water dispatch are future
work. Blank calibration fields are allowed for review, not operational readiness.

## UI packaging and tests

Use a current Node.js version. Upstream's npm lockfile is retained. Standard
web-only build commands from `ui/` are:

```sh
npm ci --ignore-scripts
npx eslint www/js/modules/options.js www/js/modules/about.js
npx grunt prepareFW
npx karma start test/karma.conf.js --browsers ChromeHeadless
```

Chrome must be installed (`CHROME_BIN` can specify its executable). Lifecycle
scripts are unnecessary for this browser build; they include mobile packaging
patches and Git-hook setup. Initial validation used the bundled modern Node
runtime and pnpm: `pnpm import`, then
`pnpm install --frozen-lockfile --ignore-scripts`. The generated pnpm lockfile
was not retained as a second dependency source. Karma explicitly loads its
three plugins to work with either package-manager layout.

`ui/build/firmware/UI.zip` includes the generated `modules.json` required by the
firmware's `home.js` bootstrap. `tools/serve_test_ui.py` serves the extracted
assets with cross-origin access and no caching for development.

## Installation on ospi-dev

Installed on 21 September 2026. The entry point remains http://192.168.5.244/.

- UI assets: `/home/codex/opensprinkler-ui/scheduling-v1`.
- UI service: transient `opensprinkler-ui.service`, running as `codex` on port 8081.
- Controller UI source: `http://192.168.5.244:8081/js`.
- Backups, build log, candidate binary and API results:
  `/home/codex/irrigation-build-records/scheduling-ui/`.
- Before replacement, the idle controller's data was archived as
  `data-before-install.tar.gz` and its binary saved as `OpenSprinkler.before`.

Upstream DEMO ignores `/cu` UI-source updates. For this isolated installation,
the URL was written into the test `sopts.dat` JavaScript URL slot after checking
the pinned layout (slot 2, 320 bytes per slot, 13 slots total). Other bytes were
preserved and the file atomically replaced. This is a test-installation
procedure, not a production migration API.

To recreate the UI service after reboot:

```sh
sudo systemd-run --unit=opensprinkler-ui --uid=codex \
  --property=NoNewPrivileges=yes \
  /usr/bin/python3 /home/codex/OpenSprinkler-Firmware/tools/serve_test_ui.py \
  /home/codex/opensprinkler-ui/scheduling-v1 --bind 0.0.0.0 --port 8081
```

Also recreate the controller and simulator services as described in
[the test Pi setup](TEST_PI_SETUP.md). They remain transient test services,
not enabled for automatic startup.

## Validation

- DEMO compiled without diagnostics. Changed UI modules passed ESLint and UI
  packaging succeeded.
- All 370 browser tests passed, including three new cases covering section
  placement, disabled mode, stock-firmware compatibility and controller saving.
- Existing options, stations and programs matched the pre-upgrade snapshot.
- Standard saved successfully; seven unsupported/malformed values were rejected
  without applying an accompanying watering-percentage change.
- After restart, Standard, the local UI URL, password bypass and simulated zones
  remained intact, with an empty queue and both simulated valves OFF.
- Browser inspection confirmed the installed section and disabled alternative;
  the settings layout was visually checked.

No production controllers or real valves were involved. Integration of the new
soil-water engine remains future work; only the DEMO firmware was compiled here.

## Optional Maps and upstream integration

GitHub secret-scanning alert 1 identified a Google Maps key inherited verbatim
from the UI subtree's upstream revision. The same value occurred in `map.js`
and `options.js`. GitHub reported validity as unknown. No attempt was made to
use the key to test its validity or inspect the provider account.

The current source and packaged UI contain no bundled Google API key. On this
test deployment, clicking Location opens the existing GPS-coordinate editor;
reverse geocoding returns the coordinates or supplied fallback without making
a Google request. Existing controller location and weather settings are retained.

Map selection remains optional: `ui/www/js/maps-config.js` ships an empty
`window.OSMapsConfig.apiKey`. A deployment can replace that file in its **built
assets**, outside tracked source, with a key belonging to that deployment.
All three entry points (firmware bootstrap, standalone app and map iframe) load
the same configuration. A configured key retains the original map flow;
reverse-lookup failures fall back to coordinates. No real key was used to test
the optional enabled path: unit tests use a fake value and stubbed requests.

Any configured browser key is visible to clients and needs appropriate Google
application/API restrictions. Moving the value to deployment configuration is
not a way to keep a browser key secret; never put a server-side credential there.

This cleanup is a separate commit from the scheduling selector. For eventual
upstream contribution, prepare focused firmware and App patches against their
respective repositories. The maintainers can adopt the scheduling changes
without changing their Maps deployment; optionally, they can adopt this
configuration improvement separately. Do not submit the subtree import itself
as an App feature patch or copy the inherited key into a new build.

The historical import still contains the inherited value. No history was
rewritten, no key was revoked, and the GitHub alert was not dismissed as a false
positive or marked revoked. Restrictions/revocation can only be verified by its
owner. Removing the current copy alone does not resolve historical exposure.

Validation: 376 browser tests passed, including disabled-map fallback and a
stubbed configured-key failure path. A Google API-key-pattern scan of tracked
working files and the rebuilt UI archive found no matches.

### Editor validation

The DEMO firmware compiled on the Pi. Browser coverage checks both selectable
modes, saved selection, draft isolation, one valve per program, disabled/master/
bundle exclusion, cycle timing, calibration validation, shared windows and group
references. Test installation backups and the compiled candidate are under
`/home/codex/irrigation-build-records/scheduling-ui/`, with `before-editor` names.
Only the dedicated DEMO installation and loopback valve receiver are used.

The final UI suite passed **387 tests**, and all **32 offline replay tests**
passed. ESLint and packaging succeeded. Browser review confirmed form layout,
draft save/reopen and the five-minute ON / nine-minute elapsed illustration.

The guarded `python3 -m tools.valve_sim.check_scheduling_mode` check on ospi-dev
verified malformed-mode rejection without partial option changes, an intact due
Standard program remaining inactive in mode 1, that same program running after
returning to Standard, and atomic rejection of a mode change while watering was
queued. Its synthetic program was removed and both simulated valves were OFF
at completion. Results: `scheduling-ui/soil-mode-checks.txt` in the build records.

## Shared program controls

Owner direction: reuse the Standard editor’s code wherever functionality is
the same, rather than maintaining parallel controls for soil-water mode.

- Both editors use `Programs.makeNameField` and `makeEnabledField`. Soil-water
  Enabled is now the same checkbox as Standard, rather than a separate select.
- Soil-water cycle, soak, minimum useful pulse and example ON duration use the
  existing `UIDom.showDurationBox` and `Dates` formatting. A common
  `bindDurationButton` also handles Standard’s Repeat Every control. Standard
  keeps its minute precision and existing interval bound; soil durations allow
  seconds and do not offer sunrise/sunset duration substitutions.
- Existing v1 browser drafts remain in minutes. The UI converts to/from seconds
  at the control boundary, retaining blank (uncalibrated) versus zero soak.
- The shared picker interprets solar-duration sentinels only when its solar
  choices are enabled; otherwise those numbers represent literal seconds.

Inspected distinction: this upstream revision has repeated program starts,
not a standalone cycle-and-soak form component. Repeat Every measures the
interval between starts; minimum soak measures OFF time after a pulse. Reuse
of duration controls does not equate those two scheduling semantics. The
new mode’s depletion accounting and pulse planning remain separate.

Validation for this refactor: 391 browser tests passed; changed modules passed
ESLint and the UI package built successfully. On ospi-dev, the existing draft
opened with one-minute cycle and soak. The shared picker’s 30-second selection
updated the preview to ten pulses and fourteen elapsed minutes. Reopening the
unsaved draft restored its original five pulses / nine minutes. No controller
scheduling settings, programs or valve commands changed during this UI check.

## Priority Groups page

Edit Options → Scheduling → Priority Groups appears for the saved soil-water
mode. Each group has only a name and its position in the ordered list. Move up
and Move down change the order; highest priority comes first. Additional group
properties are explicitly deferred. Add group creates a blank row; Save draft
validates and persists the entire edit in browser storage for this controller.

Names must be nonempty and unique (case-insensitive). A rename updates all
program assignments atomically, including name swaps. Used groups cannot be
removed; at least one group remains. The program dropdown follows saved order.
The old shared-settings textarea was removed, leaving one group editor.

Group saving rejects conflicting group edits from another window and preserves
other current draft data. Program and shared-settings saves reload current
groups so they cannot silently undo a rename or reorder. The existing ordered
name schema remains compatible; controller persistence is still future work.

Validation: 398 browser tests passed, covering conditional navigation, add and
reorder, reference-preserving renames, removal restrictions, duplicate/blank
names, stale group edits and preservation when shared settings are saved.
