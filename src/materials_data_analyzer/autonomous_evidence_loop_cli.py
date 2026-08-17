"""Installed CLI for mission-authorized trusted external-evidence research loops."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from materials_data_analyzer.research_loop.autonomous_evidence_loop import (
    ACQUISITION_BLOCKED,
    AutonomousEvidenceLoopError,
)
from materials_data_analyzer.research_loop.public_data_acquisition import (
    DEFAULT_MAX_AUTO_ARTIFACT_BYTES,
    DEFAULT_MAX_AUTO_BATCH_BYTES,
    PublicAcquisitionError,
)
from materials_data_analyzer.research_loop.public_scientific_intake_router import (
    route_public_scientific_intake,
)
from materials_data_analyzer.research_loop.trusted_discovery_authorization import (
    TrustedDiscoveryAuthorizationError,
    run_mission_authorized_evidence_loop,
)
from materials_data_analyzer.research_loop.trusted_source_discovery import (
    TrustedSourceDiscoveryError,
)

_MIB = 1024 * 1024


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _load_json(path: Path, *, field: str) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{field} must be valid duplicate-free UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{field} root must be an object")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mda-autonomous-evidence-loop",
        description=(
            "Run one bounded trusted-source research loop selected by the self-directed "
            "planner. Exact mission-pinned policy bytes satisfy the planner's explicit "
            "network authorization gate; unknown providers and scientific semantics remain fail-closed."
        ),
    )
    parser.add_argument("--program-state", required=True, type=Path)
    parser.add_argument("--self-directed-plan", required=True, type=Path)
    parser.add_argument("--trusted-policy", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--max-iterations", type=_positive_int, default=3)
    parser.add_argument("--max-records-per-iteration", type=_positive_int, default=3)
    parser.add_argument("--max-files-per-product", type=_positive_int, default=4)
    parser.add_argument(
        "--max-auto-mib",
        type=_positive_int,
        default=DEFAULT_MAX_AUTO_ARTIFACT_BYTES // _MIB,
        help="Maximum automatically acquired size of one artifact in MiB.",
    )
    parser.add_argument(
        "--max-auto-batch-mib",
        type=_positive_int,
        default=DEFAULT_MAX_AUTO_BATCH_BYTES // _MIB,
        help="Maximum automatically acquired bytes per selected product in MiB.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.timeout_seconds <= 0:
        print("error: --timeout-seconds must be positive", file=sys.stderr)
        return 2
    try:
        program_state = _load_json(args.program_state, field="program-state")
        self_directed_plan = _load_json(
            args.self_directed_plan, field="self-directed-plan"
        )
        trusted_policy_bytes = args.trusted_policy.read_bytes()
        report = run_mission_authorized_evidence_loop(
            program_state,
            self_directed_plan,
            trusted_policy_bytes=trusted_policy_bytes,
            output_root=args.output_root,
            intake_handler=route_public_scientific_intake,
            max_iterations=args.max_iterations,
            max_records_per_iteration=args.max_records_per_iteration,
            max_files_per_product=args.max_files_per_product,
            max_auto_bytes=args.max_auto_mib * _MIB,
            max_total_auto_bytes=args.max_auto_batch_mib * _MIB,
            timeout_seconds=args.timeout_seconds,
        )
    except (
        AutonomousEvidenceLoopError,
        TrustedDiscoveryAuthorizationError,
        TrustedSourceDiscoveryError,
        PublicAcquisitionError,
        OSError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    if report["evidence_loop"]["terminal_status"] == ACQUISITION_BLOCKED:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
