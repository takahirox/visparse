"""Command-line interface for deterministic Visparse operations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .evaluation import evaluate_fixture, load_fixture
from .codex import CodexAnalyzer, CodexAnalyzerError
from .design import CodexDesignAnalyzer, normalize_design_profile
from .inspection import (
    inspection_capabilities,
    load_inspection,
    normalize_inspection,
    summarize_inspection,
)
from .model import MAX_INPUT_BYTES, SourceEvidence, ValidationError, load_record, normalize_record, summarize_record


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
    for name in ("inspect", "inspect-summary"):
        command = subparsers.add_parser(name)
        command.add_argument("path", help="inspection bundle path, or - for standard input")
    subparsers.add_parser("inspect-capabilities")
    analyze = subparsers.add_parser("analyze")
    analyze.add_argument("image", metavar="IMAGE", help="image path")
    analyze_design = subparsers.add_parser("analyze-design")
    analyze_design.add_argument(
        "images", metavar="REFERENCE_IMAGE", nargs="+",
        help="one or more reference-site screenshot paths",
    )
    analyze_design.add_argument(
        "--target", metavar="TARGET_IMAGE", action="append", default=[],
        help="target-site screenshot path; repeat for multiple viewports",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI, returning 0 on success, 1 on failed evaluation, or 2 on error."""
    args = _parser().parse_args(argv)
    try:
        if args.command == "analyze":
            source = SourceEvidence.from_file("source-1", args.image)
            record = CodexAnalyzer().analyze(source)
            sys.stdout.write(normalize_record(record))
            return 0
        if args.command == "analyze-design":
            references = [
                SourceEvidence.from_file(f"reference-{index}", path)
                for index, path in enumerate(args.images, 1)
            ]
            targets = [
                SourceEvidence.from_file(f"target-{index}", path)
                for index, path in enumerate(args.target, 1)
            ]
            profile = CodexDesignAnalyzer().analyze(references, targets)
            sys.stdout.write(normalize_design_profile(profile))
            return 0
        if args.command == "inspect-capabilities":
            sys.stdout.write(_json_line(inspection_capabilities()))
            return 0
        payload = _read_bounded(args.path)
        if args.command in {"inspect", "inspect-summary"}:
            inspection = load_inspection(payload)
            if args.command == "inspect":
                sys.stdout.write(normalize_inspection(inspection))
            else:
                sys.stdout.write(_json_line(summarize_inspection(inspection)))
            return 0
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
    except (OSError, ValidationError, TypeError, ValueError, CodexAnalyzerError) as error:
        sys.stderr.write(f"visparse: {error}\n")
        return 2
