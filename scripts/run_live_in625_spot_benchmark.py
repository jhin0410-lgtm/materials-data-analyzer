from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from materials_data_analyzer.research_loop.acquisition_record_binding import (
    authenticate_acquisition_record_binding,
)
from materials_data_analyzer.research_loop.comparability_engine import (
    AuthenticatedEvidenceInput,
)
from materials_data_analyzer.research_loop.evidence_packet import canonical_sha256
from materials_data_analyzer.research_loop.evidence_provider_contract import (
    AuthenticatedProviderStateInput,
    adapt_authenticated_planning_gaps,
)
from materials_data_analyzer.research_loop.evidence_provider_planning import (
    build_provider_planner_program_state,
)
from materials_data_analyzer.research_loop.in625_competency_evidence import (
    build_mds2_2923_ammt_195_800_validation_material,
)
from materials_data_analyzer.research_loop.in625_spot_size_sensitivity import (
    authorize_in625_spot_size_sensitivity_request,
    build_in625_spot_size_sensitivity_request,
    execute_in625_spot_size_sensitivity,
    verify_in625_spot_size_sensitivity,
)
from materials_data_analyzer.research_loop.research_agent import (
    build_research_agent_iteration,
)


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(value))


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path} must contain a JSON object")
    return value


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_file_sha(path: Path, expected: str, label: str) -> None:
    if len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
        raise RuntimeError(f"{label} expected SHA-256 is malformed")
    observed = _file_sha(path)
    if observed != expected:
        raise RuntimeError(
            f"{label} changed after freeze: expected {expected}, observed {observed}"
        )


def _package_for_artifact(root: Path, artifact_name: str) -> tuple[Path, dict[str, Any]]:
    matches: list[tuple[Path, dict[str, Any]]] = []
    for receipt_path in sorted(root.glob("packages/*/acquisition_receipt.json")):
        receipt = _load_json(receipt_path)
        if receipt.get("artifact_path") == artifact_name:
            matches.append((receipt_path.parent, receipt))
    if len(matches) != 1:
        raise RuntimeError(
            f"artifact {artifact_name!r} must resolve to one package; found {len(matches)}"
        )
    return matches[0]


def _authenticated_artifact(
    root: Path, artifact_name: str
) -> tuple[bytes, bytes, dict[str, Any]]:
    package, receipt = _package_for_artifact(root, artifact_name)
    evidence_bytes = (package / artifact_name).read_bytes()
    metadata_bytes = (package / "source_metadata.json").read_bytes()
    manifest_bytes = (package / "acquisition_manifest.json").read_bytes()
    declaration_bytes = (package / "acquisition_declaration.json").read_bytes()
    authenticated = authenticate_acquisition_record_binding(
        evidence_bytes=evidence_bytes,
        acquisition_manifest_bytes=manifest_bytes,
        acquisition_declaration_bytes=declaration_bytes,
    )
    if authenticated.get("recorded_acquisition_provenance_authenticated") is not True:
        raise RuntimeError(f"acquisition package failed authentication: {artifact_name}")
    if hashlib.sha256(evidence_bytes).hexdigest() != receipt.get("artifact_sha256"):
        raise RuntimeError(f"receipt SHA mismatch: {artifact_name}")
    if len(evidence_bytes) != receipt.get("artifact_size_bytes"):
        raise RuntimeError(f"receipt size mismatch: {artifact_name}")
    if hashlib.sha256(metadata_bytes).hexdigest() != receipt.get("metadata_sha256"):
        raise RuntimeError(f"metadata SHA mismatch: {artifact_name}")
    return evidence_bytes, metadata_bytes, receipt


def _source_material(
    acquisition_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    workbook, workbook_metadata, workbook_receipt = _authenticated_artifact(
        acquisition_root, "Master_TrackList_Measurements.xlsx"
    )
    readme, readme_metadata, readme_receipt = _authenticated_artifact(
        acquisition_root, "2923_README.txt"
    )
    if workbook_metadata != readme_metadata:
        raise RuntimeError("README and workbook packages use different NERDm metadata bytes")
    material = build_mds2_2923_ammt_195_800_validation_material(
        workbook_bytes=workbook,
        readme_bytes=readme,
        nerdm_metadata_bytes=workbook_metadata,
    )
    if len(material) != 18:
        raise RuntimeError(f"live benchmark expected 18 rows, found {len(material)}")
    return material, {
        "workbook_sha256": str(workbook_receipt["artifact_sha256"]),
        "readme_sha256": str(readme_receipt["artifact_sha256"]),
        "nerdm_metadata_sha256": hashlib.sha256(workbook_metadata).hexdigest(),
    }


def _build_inputs(
    material: list[dict[str, Any]],
    roots: dict[str, Any],
) -> list[AuthenticatedEvidenceInput]:
    by_id = roots.get("trusted_expectation_sha256_by_evidence_id")
    if not isinstance(by_id, dict):
        raise RuntimeError("expectation root map is missing")
    inputs: list[AuthenticatedEvidenceInput] = []
    for item in material:
        evidence_id = item.get("evidence_id")
        if not isinstance(evidence_id, str) or evidence_id not in by_id:
            raise RuntimeError(f"missing expectation trust root for {evidence_id!r}")
        expected = item.get("expected")
        packet = item.get("packet")
        artifacts = item.get("artifacts")
        if not isinstance(expected, dict) or not isinstance(packet, dict) or not isinstance(
            artifacts, dict
        ):
            raise RuntimeError("validation material is malformed")
        trusted = by_id[evidence_id]
        if canonical_sha256(expected) != trusted:
            raise RuntimeError(f"frozen expectation root drifted for {evidence_id}")
        inputs.append(
            AuthenticatedEvidenceInput(
                packet=packet,
                artifacts=artifacts,
                expected=expected,
                trusted_expectation_sha256=str(trusted),
            )
        )
    return inputs


def _base_program() -> dict[str, Any]:
    return {
        "mission": {
            "mission_id": "in625-live-spot-sensitivity-benchmark-v1",
            "research_question": (
                "Does existing authenticated mds2 evidence show that spot diameter must remain "
                "explicit context before direct NIST-vs-mds2 quantitative comparison?"
            ),
            "autonomy_policy": {
                "goal_generation": "bounded_autonomous",
                "reasoning_proposals": "schema_validated",
                "typed_computational_actions": "explicit_request",
                "network_evidence_search": "explicit_authorization",
                "physical_experiment_execution": "external_only",
            },
        },
        "generated_goals": [],
    }


def freeze_evidence(args: argparse.Namespace) -> int:
    root = args.acquisition_root.resolve(strict=True)
    material, source = _source_material(root)
    roots = {
        "schema_version": "1.0",
        "purpose": "externally_frozen_live_benchmark_expectation_roots",
        "source": source,
        "evidence_count": len(material),
        "trusted_expectation_sha256_by_evidence_id": {
            str(item["evidence_id"]): canonical_sha256(item["expected"])
            for item in material
        },
        "packet_sha256_by_evidence_id": {
            str(item["evidence_id"]): str(item["packet"]["packet_sha256"])
            for item in material
        },
        "scientific_status_promoted": False,
    }
    _write_json(args.output, roots)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "file_sha256": _file_sha(args.output),
                "evidence_count": len(material),
                **source,
            },
            sort_keys=True,
        )
    )
    return 0


def freeze_iteration(args: argparse.Namespace) -> int:
    planning_state = {
        "schema_version": "1.0",
        "state_type": "in625_live_spot_sensitivity_unresolved_evidence",
        "unresolved_evidence_gaps": [
            {
                "gap_id": "in625-live:protocol-spot-uncertainty",
                "requirement": (
                    "Analyze the authenticated mds2 AMMT 195 W / 800 mm/s rows for spot-size "
                    "sensitivity and uncertainty before treating spot/protocol context as ignorable."
                ),
                "action_class_hint": "analysis",
            }
        ],
        "scientific_status_changed": False,
        "direct_numerical_cross_source_validation_authorized": False,
        "directly_comparable_mds2_rows": 0,
        "issue_76_exact_target_cells_satisfied": 0,
    }
    provider = adapt_authenticated_planning_gaps(
        planning_state,
        trusted_state_sha256=canonical_sha256(planning_state),
    )
    program = build_provider_planner_program_state(
        _base_program(),
        [
            AuthenticatedProviderStateInput(
                state=provider,
                trusted_provider_state_sha256=provider["provider_state_sha256"],
            )
        ],
    )
    plan = build_research_agent_iteration(
        program,
        budget_units=8.0,
        minimum_utility=0.01,
        max_iterations=8,
    )
    selected = plan.get("selected_next_action")
    if not isinstance(selected, dict) or selected.get("action_class") != "sensitivity_analysis":
        raise RuntimeError(
            f"live planner did not select sensitivity_analysis: {selected!r}"
        )
    iteration: dict[str, Any] = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "episode_stage": "live_self_directed_planning_iteration",
        "provider_state_sha256": provider["provider_state_sha256"],
        "program_state_sha256": canonical_sha256(program),
        "plan": plan,
        "scientific_boundary": {
            "directly_comparable_mds2_rows": 0,
            "direct_numerical_cross_source_validation_authorized": False,
            "issue_76_exact_target_cells_satisfied": 0,
        },
        "authority_boundary": {
            "selected_action_is_authorized": False,
            "request_compiled": False,
            "execution_performed": False,
            "scientific_status_changed": False,
        },
    }
    iteration["iteration_sha256"] = canonical_sha256(iteration)
    _write_json(args.output, iteration)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "file_sha256": _file_sha(args.output),
                "iteration_object_sha256": canonical_sha256(iteration),
                "selected_action_id": selected["action_id"],
                "selected_action_class": selected["action_class"],
            },
            sort_keys=True,
        )
    )
    return 0


def compile_request(args: argparse.Namespace) -> int:
    _require_file_sha(args.expectation_roots, args.expectation_roots_file_sha256, "expectation roots")
    _require_file_sha(args.iteration, args.iteration_file_sha256, "planner iteration")
    roots = _load_json(args.expectation_roots)
    iteration = _load_json(args.iteration)
    material, source = _source_material(args.acquisition_root.resolve(strict=True))
    if roots.get("source") != source:
        raise RuntimeError("frozen evidence roots are bound to different source bytes")
    inputs = _build_inputs(material, roots)
    request = build_in625_spot_size_sensitivity_request(
        iteration,
        trusted_iteration_sha256=canonical_sha256(iteration),
        evidence_inputs=inputs,
    )
    _write_json(args.output, request)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "file_sha256": _file_sha(args.output),
                "request_object_sha256": canonical_sha256(request),
                "evidence_packet_count": len(inputs),
            },
            sort_keys=True,
        )
    )
    return 0


def authorize(args: argparse.Namespace) -> int:
    _require_file_sha(args.request, args.request_file_sha256, "request")
    request = _load_json(args.request)
    receipt = authorize_in625_spot_size_sensitivity_request(
        request,
        trusted_request_sha256=canonical_sha256(request),
    )
    _write_json(args.output, receipt)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "file_sha256": _file_sha(args.output),
                "authorization_object_sha256": canonical_sha256(receipt),
                "execution_authorized": receipt["execution_authorized"],
                "network_access_authorized": receipt["network_access_authorized"],
                "physical_experiment_authorized": receipt["physical_experiment_authorized"],
            },
            sort_keys=True,
        )
    )
    return 0


def execute(args: argparse.Namespace) -> int:
    _require_file_sha(args.expectation_roots, args.expectation_roots_file_sha256, "expectation roots")
    _require_file_sha(args.request, args.request_file_sha256, "request")
    _require_file_sha(args.authorization, args.authorization_file_sha256, "authorization")
    roots = _load_json(args.expectation_roots)
    request = _load_json(args.request)
    receipt = _load_json(args.authorization)
    material, source = _source_material(args.acquisition_root.resolve(strict=True))
    if roots.get("source") != source:
        raise RuntimeError("frozen evidence roots are bound to different source bytes")
    inputs = _build_inputs(material, roots)
    result = execute_in625_spot_size_sensitivity(
        request,
        authorization_receipt=receipt,
        trusted_authorization_sha256=canonical_sha256(receipt),
        evidence_inputs=inputs,
    )
    verified = verify_in625_spot_size_sensitivity(
        result,
        request=request,
        authorization_receipt=receipt,
        trusted_authorization_sha256=canonical_sha256(receipt),
        evidence_inputs=inputs,
    )
    if verified != result:
        raise RuntimeError("independent recomputation changed the live result")
    _write_json(args.output, verified)
    analysis = verified["analysis"]
    print(
        json.dumps(
            {
                "output": str(args.output),
                "file_sha256": _file_sha(args.output),
                "result_object_sha256": canonical_sha256(verified),
                "row_count": analysis["row_count"],
                "physical_track_count": analysis["physical_track_count"],
                "spot_level_count": analysis["spot_level_count"],
                "spot_diameter_range_um": analysis["spot_diameter_range_um"],
                "width_linear_slope_um_per_um_spot": analysis["width"][
                    "linear_slope_um_per_um_spot"
                ],
                "width_pearson_r": analysis["width"]["pearson_r_spot_vs_width"],
                "width_leave_one_level_sign_stable": analysis["width"][
                    "leave_one_level_sign_stable"
                ],
                "depth_linear_slope_um_per_um_spot": analysis["depth"][
                    "linear_slope_um_per_um_spot"
                ],
                "depth_pearson_r": analysis["depth"]["pearson_r_spot_vs_depth"],
                "depth_leave_one_level_sign_stable": analysis["depth"][
                    "leave_one_level_sign_stable"
                ],
                "protocol_equivalence_established": verified[
                    "scientific_interpretation"
                ]["protocol_equivalence_established"],
                "direct_cross_source_authorized": verified[
                    "scientific_interpretation"
                ]["cross_source_numerical_validation_authorized"],
                "issue_76_exact_target_cells_satisfied": verified[
                    "scientific_interpretation"
                ]["issue_76_exact_target_cells_satisfied"],
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
        description="Run the staged live IN625 mds2 spot-size diagnostic benchmark."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    freeze = sub.add_parser("freeze-evidence")
    freeze.add_argument("--acquisition-root", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    freeze.set_defaults(func=freeze_evidence)

    iteration = sub.add_parser("freeze-iteration")
    iteration.add_argument("--output", type=Path, required=True)
    iteration.set_defaults(func=freeze_iteration)

    compile_cmd = sub.add_parser("compile-request")
    compile_cmd.add_argument("--acquisition-root", type=Path, required=True)
    compile_cmd.add_argument("--expectation-roots", type=Path, required=True)
    compile_cmd.add_argument("--expectation-roots-file-sha256", required=True)
    compile_cmd.add_argument("--iteration", type=Path, required=True)
    compile_cmd.add_argument("--iteration-file-sha256", required=True)
    compile_cmd.add_argument("--output", type=Path, required=True)
    compile_cmd.set_defaults(func=compile_request)

    auth = sub.add_parser("authorize")
    auth.add_argument("--request", type=Path, required=True)
    auth.add_argument("--request-file-sha256", required=True)
    auth.add_argument("--output", type=Path, required=True)
    auth.set_defaults(func=authorize)

    run = sub.add_parser("execute")
    run.add_argument("--acquisition-root", type=Path, required=True)
    run.add_argument("--expectation-roots", type=Path, required=True)
    run.add_argument("--expectation-roots-file-sha256", required=True)
    run.add_argument("--request", type=Path, required=True)
    run.add_argument("--request-file-sha256", required=True)
    run.add_argument("--authorization", type=Path, required=True)
    run.add_argument("--authorization-file-sha256", required=True)
    run.add_argument("--output", type=Path, required=True)
    run.set_defaults(func=execute)
    return parser


def main() -> int:
    args = _parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
