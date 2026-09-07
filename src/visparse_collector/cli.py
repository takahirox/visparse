"""Separate CLI for optional browser execution."""

import argparse
import sys

from visparse.contracts import canonical
from .browser import CaptureOptions, capture


def main(argv=None):
    parser = argparse.ArgumentParser(prog="visparse-collector")
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("capture")
    command.add_argument("url")
    command.add_argument("--screenshots", default="artifacts")
    command.add_argument("--viewport", action="append", default=[])
    command.add_argument("--timeout", type=float, default=30)
    command.add_argument("--max-nodes", type=int, default=40)
    command.add_argument("--max-scan", type=int, default=5000)
    command.add_argument("--wait-until", default="load", choices=["load", "domcontentloaded", "networkidle"])
    command.add_argument("--full-page", action="store_true")
    args = parser.parse_args(argv)
    try:
        viewports = tuple(tuple(int(v) for v in raw.split("x")) for raw in args.viewport) or CaptureOptions().viewports
        options = CaptureOptions(viewports=viewports, timeout_seconds=args.timeout, max_nodes=args.max_nodes,
                                 max_scan=args.max_scan, wait_until=args.wait_until, full_page=args.full_page)
        sys.stdout.write(canonical(capture(args.url, args.screenshots, options)))
        return 0
    except Exception as error:
        sys.stderr.write(f"visparse-collector: {error}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
