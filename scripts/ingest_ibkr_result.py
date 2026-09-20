"""Turn an Interactive Brokers price-history payload into a data file the app reads.

The IBKR price-history endpoint returns parallel arrays rather than rows:

    {"chart_start": "...", "time": [...], "open": [...], "high": [...],
     "low": [...], "close": [...], "volume": [...]}

Save one of those responses to a file and run this to file it under
``data/external/ibkr/<SYMBOL>_<interval>.json``, where the ``ibkr`` provider
picks it up automatically. Currency payloads carry no ``volume`` array; that is
handled.

Usage
-----
    python scripts/ingest_ibkr_result.py SPY 1d --source ~/Downloads/spy.json
    python scripts/ingest_ibkr_result.py EURUSD 1d --source eur.json --keep

    # Take the newest JSON in a directory, which is convenient when a tool
    # writes responses there automatically:
    python scripts/ingest_ibkr_result.py SPY 1d --source-dir ./responses
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import IBKR_SNAPSHOT_DIR  # noqa: E402
from src.services.providers import IBKRSnapshotProvider  # noqa: E402

REQUIRED = ("time", "open", "high", "low", "close")


def newest_in(directory: Path, pattern: str) -> Path:
    """The most recently modified file in ``directory`` matching ``pattern``."""
    files = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime)
    if not files:
        raise SystemExit(f"no files matching {pattern!r} in {directory}")
    return files[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("symbol", help="Canonical symbol, e.g. SPY or EURUSD.")
    parser.add_argument("interval", nargs="?", default="1d",
                        help="Bar size the payload holds: 1d, 1h, 30m, ... (default 1d)")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--source", type=Path, help="The JSON file to ingest.")
    source.add_argument("--source-dir", type=Path,
                        help="Directory to take the newest matching JSON from.")
    parser.add_argument("--pattern", default="*.json",
                        help="Glob used with --source-dir (default *.json).")
    parser.add_argument("--keep", action="store_true",
                        help="Keep the source file. By default it is removed once filed.")
    args = parser.parse_args()

    path = args.source if args.source else newest_in(args.source_dir, args.pattern)
    try:
        payload = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"could not read {path}: {exc}") from None

    missing = [key for key in REQUIRED if key not in payload]
    if missing:
        raise SystemExit(f"{path} is missing {missing}; is this an IBKR price-history response?")

    # Parse before writing, so a malformed payload fails here rather than later
    # inside a backtest.
    frame = IBKRSnapshotProvider.parse(payload)
    if len(frame) == 0:
        raise SystemExit(f"{path} carries no bars")

    IBKR_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    destination = IBKR_SNAPSHOT_DIR / f"{args.symbol.upper()}_{args.interval}.json"
    destination.write_text(json.dumps(payload, separators=(",", ":")))
    if not args.keep:
        Path(path).unlink(missing_ok=True)

    print(
        f"{args.symbol.upper()}: {len(frame)} bars "
        f"{payload.get('chart_start', '?')[:10]} to {payload.get('chart_end', '?')[:10]} "
        f"-> {destination.relative_to(destination.parents[3])}"
    )


if __name__ == "__main__":
    main()
