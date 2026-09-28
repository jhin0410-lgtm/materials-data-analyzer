from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from materials_data_analyzer.research_loop.evidence_packet import canonical_sha256
from materials_data_analyzer.research_loop.in625_blind_challenge_history import (
    authorize_in625_blind_history_request,
    build_in625_blind_history_request,
    execute_in625_blind_history_acquisition,
    verify_in625_blind_history_acquisition,
)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path} must contain one JSON object")
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _sha(value: str, field: str) -> str:
    if (
        len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise RuntimeError(f"{field} must be lowercase SHA-256")
    return value


def _require_file_sha(path: Path, expected: str, field: str) -> None:
    expected = _sha(expected, field)
    observed = hashlib.sha256(path.read_bytes()).hexdigest()
    if observed != expected:
        raise RuntimeError(
            f"{field} changed after freeze: expected {expected}, observed {observed}"
        )


def compile_request(args: argparse.Namespace) -> int:
    _require_file_sha(args.inquiry, args.inquiry_file_sha256, "inquiry file SHA-256")
    inquiry = _load_json(args.inquiry)
    expected_object = _sha(
        args.inquiry_object_sha256,
        "inquiry object SHA-256",
    )
    if canonical_sha256(inquiry) != expected_object:
        raise RuntimeError("inquiry object changed after freeze")

    request = build_in625_blind_history_request(
        inquiry,
        trusted_inquiry_sha256=expected_object,
    )
    _write_json(args.output, request)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "file_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                "request_object_sha256": canonical_sha256(request),
                "source_count": request["network_contract"]["max_requests"],
                "selected_action_id": request["selected_planner_action"]["action_id"],
            },
            sort_keys=True,
        )
    )
    return 0


def authorize(args: argparse.Namespace) -> int:
    _require_file_sha(args.request, args.request_file_sha256, "request file SHA-256")
    request = _load_json(args.request)
    expected_object = _sha(
        args.request_object_sha256,
        "request object SHA-256",
    )
    if canonical_sha256(request) != expected_object:
        raise RuntimeError("request object changed after freeze")

    receipt = authorize_in625_blind_history_request(
        request,
        trusted_request_sha256=expected_object,
    )
    _write_json(args.output, receipt)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "file_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                "authorization_object_sha256": canonical_sha256(receipt),
                "network_execution_authorized": receipt[
                    "network_execution_authorized"
                ],
                "authorized_request_count": receipt["authorized_request_count"],
                "unrestricted_search_authorized": receipt[
                    "unrestricted_search_authorized"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


def execute(args: argparse.Namespace) -> int:
    _require_file_sha(args.request, args.request_file_sha256, "request file SHA-256")
    _require_file_sha(
        args.authorization,
        args.authorization_file_sha256,
        "authorization file SHA-256",
    )
    request = _load_json(args.request)
    authorization = _load_json(args.authorization)

    expected_request = _sha(
        args.request_object_sha256,
        "request object SHA-256",
    )
    expected_authorization = _sha(
        args.authorization_object_sha256,
        "authorization object SHA-256",
    )
    if canonical_sha256(request) != expected_request:
        raise RuntimeError("request object changed after freeze")
    if canonical_sha256(authorization) != expected_authorization:
        raise RuntimeError("authorization object changed after freeze")

    result = execute_in625_blind_history_acquisition(
        request,
        authorization_receipt=authorization,
        trusted_authorization_sha256=expected_authorization,
        source_output_dir=args.source_output_dir,
    )
    verified = verify_in625_blind_history_acquisition(
        result,
        request=request,
        authorization_receipt=authorization,
        trusted_authorization_sha256=expected_authorization,
        source_output_dir=args.source_output_dir,
    )
    if verified != result:
        raise RuntimeError("retained-byte replay changed blind-history result")

    _write_json(args.output, verified)
    facts = verified["verified_historical_context"]
    print(
        json.dumps(
            {
                "output": str(args.output),
                "file_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                "result_object_sha256": canonical_sha256(verified),
                "source_count": verified["source_count"],
                "blind_simulation_count": facts[
                    "amb2018_total_blind_modeling_simulations"
                ],
                "melt_pool_geometry_submission_count": facts[
                    "amb2018_02_melt_pool_geometry_submission_count"
                ],
                "none_of_10_mp_groups_came_close": facts[
                    "nist_retrospective_statement_none_of_10_mp_groups_came_close_to_measurements"
                ],
                "individual_numeric_predictions_acquired": facts[
                    "individual_blind_submission_numeric_predictions_acquired"
                ],
                "specific_cause_established": verified["bounded_interpretation"][
                    "specific_cause_of_retrospective_improvement_established"
                ],
                "scientific_status_promoted": verified["authority_boundary"][
                    "scientific_status_promoted"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Execute the planner-selected finite NIST AMB2018 blind-history evidence action."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)

    compile_cmd = sub.add_parser("compile-request")
    compile_cmd.add_argument("--inquiry", type=Path, required=True)
    compile_cmd.add_argument("--inquiry-file-sha256", required=True)
    compile_cmd.add_argument("--inquiry-object-sha256", required=True)
    compile_cmd.add_argument("--output", type=Path, required=True)
    compile_cmd.set_defaults(func=compile_request)

    auth = sub.add_parser("authorize")
    auth.add_argument("--request", type=Path, required=True)
    auth.add_argument("--request-file-sha256", required=True)
    auth.add_argument("--request-object-sha256", required=True)
    auth.add_argument("--output", type=Path, required=True)
    auth.set_defaults(func=authorize)

    run = sub.add_parser("execute")
    run.add_argument("--request", type=Path, required=True)
    run.add_argument("--request-file-sha256", required=True)
    run.add_argument("--request-object-sha256", required=True)
    run.add_argument("--authorization", type=Path, required=True)
    run.add_argument("--authorization-file-sha256", required=True)
    run.add_argument("--authorization-object-sha256", required=True)
    run.add_argument("--source-output-dir", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.set_defaults(func=execute)
    return parser


def main() -> int:
    args = _parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
