"""Run from repository root: python3 -m tools.irrigation_replay FIXTURE."""
import argparse
import json
from pathlib import Path
from .replay import replay


def main():
    parser = argparse.ArgumentParser(description='Offline irrigation fixture replay; no device access')
    parser.add_argument('fixture', type=Path)
    args = parser.parse_args()
    try:
        result = replay(json.loads(args.fixture.read_text()))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(2, f'Invalid fixture: {exc}\n')
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
