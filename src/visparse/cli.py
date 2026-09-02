"""Command-line interface for deterministic Visparse operations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .evaluation import evaluate_fixture, load_fixture
from .model import MAX_INPUT_BYTES, ValidationError, load_record, normalize_record, summarize_record


def _read_bounded(path: str) -> bytes:
    if path == "-":
        data = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    else:
        with Path(path).open("rb") as stream:
            data = stream.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise ValidationError(f"input exceeds {MAX_INPUT_BYTES} bytes")
    return data


def _json_line(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="visparse", description="Validate and inspect Visparse JSON")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "normalize", "summarize", "evaluate"):
        command = subparsers.add_parser(name)
        command.add_argument("path", help="JSON path, or - for standard input")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI, returning 0 on success, 1 on failed evaluation, or 2 on error."""
    args = _parser().parse_args(argv)
    try:
        payload = _read_bounded(args.path)
        if args.command == "evaluate":
            result = evaluate_fixture(load_fixture(payload))
            sys.stdout.write(_json_line(result.to_dict()))
            return 0 if not result.failures else 1
        record = load_record(payload)
        if args.command == "validate":
            sys.stdout.write(_json_line({"schema_version": record["schema_version"], "valid": True}))
        elif args.command == "normalize":
            sys.stdout.write(normalize_record(record))
        else:
            sys.stdout.write(_json_line(summarize_record(record)))
        return 0
    except (OSError, ValidationError, TypeError, ValueError) as error:
        sys.stderr.write(f"visparse: {error}\n")
        return 2
