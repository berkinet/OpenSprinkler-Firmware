# Integrated UI source and scheduling-mode setting

## Source and maintenance

The owner requested a Scheduling section under Edit Options, with Standard as
the default and Soil water balance unavailable until its engine integration is
ready. This increment establishes the controller option and UI; it does not
switch algorithms or add watering-window configuration.

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
- `/co?smode=0` saves Standard through normal controller persistence.
- Other values, including malformed or empty input, are rejected before other
  options in the request change. Unsupported stored values normalize to 0 on
  load. This prevents activating an unfinished engine.
- The UI shows this section only when the controller exposes `smode`. It does
  not save the choice in browser storage. Soil water balance is disabled, with
  explanatory text.

When the new engine is ready, extend the accepted values and startup validation
together with scheduling dispatch, then enable its UI choice.

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
