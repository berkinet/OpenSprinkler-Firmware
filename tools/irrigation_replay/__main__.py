"""Run from repository root: python3 -m tools.irrigation_replay FIXTURE."""
import argparse
import json
from pathlib import Path
from .replay import replay
from .draft import InputErrors
from .engine import audit, dry_run


def main():
    parser = argparse.ArgumentParser(description='Offline irrigation fixture replay; no device access')
    parser.add_argument('fixture', type=Path, nargs='?')
    parser.add_argument('--draft', type=Path, help='exported soil-water browser draft')
    parser.add_argument('--runtime', type=Path, help='explicit runtime snapshot for a draft dry run')
    args = parser.parse_args()
    if bool(args.fixture) == bool(args.draft) or (args.runtime and not args.draft):
        parser.error('use FIXTURE or --draft DRAFT [--runtime SNAPSHOT]')
    try:
        if args.draft:
            draft = json.loads(args.draft.read_text())
            result = dry_run(draft, json.loads(args.runtime.read_text())) if args.runtime else audit(draft)
        else:
            result = replay(json.loads(args.fixture.read_text()))
    except InputErrors as exc:
        print(json.dumps(dict(status='blocked', mode='offline_no_controller_io',
                              issues=exc.issues), indent=2))
        parser.exit(2)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(2, f'Invalid fixture: {exc}\n')
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
