from __future__ import annotations

import argparse
import time

from .processor import process_pending_jobs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TimelineForChatGPT worker")
    subparsers = parser.add_subparsers(dest="command", required=True)

    daemon = subparsers.add_parser("daemon", help="Poll for pending jobs.")
    daemon.add_argument("--poll-interval", type=int, default=5)

    subparsers.add_parser("run-once", help="Process pending jobs once.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run-once":
        process_pending_jobs()
        return 0

    while True:
        process_pending_jobs()
        time.sleep(max(1, int(args.poll_interval)))


if __name__ == "__main__":
    raise SystemExit(main())
