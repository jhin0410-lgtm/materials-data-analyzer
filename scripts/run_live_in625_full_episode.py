from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from materials_data_analyzer.research_loop.comparability_engine import (
    AuthenticatedEvidenceInput,
    DEFAULT_RULE_REGISTRY,
)
from materials_data_analyzer.research_loop.evidence_packet import canonical_sha256
from materials_data_analyzer.research_loop.evidence_packet_adapters import (
    build_nist_ambench_trace_validation_material,
)
from materials_data_analyzer.research_loop.in625_competency_benchmark import (
    build_in625_competency_bootstrap,
    build_in625_competency_iteration,
)
from materials_data_analyzer.research_loop.in625_competency_closeout import (
    build_in625_competency_bounded_closeout,
)
from materials_data_analyzer.research_loop.in625_competency_evidence import (
    build_mds2_2923_ammt_195_800_validation_material,
)
from materials_data_analyzer.research_loop.in625_geometry_condition_mapping_assessment import (
    build_geometry_condition_mapping_assessment,
)
from materials_data_analyzer.research_loop.in625_geometry_condition_multisource_policy import (
    authenticate_geometry_condition_multisource_policy,
)
from materials_data_analyzer.research_loop.in625_geometry_condition_source_acquisition import (
    acquire_geometry_condition_sources,
)
from materials_data_analyzer.research_loop.nist_mds2_2923_scientific_intake import (
    audit_mds2_2923,
)
from materials_data_analyzer.research_loop.acquisition_record_binding import (
    authenticate_acquisition_record_binding,
)


MISSION_REL = Path("configs/research/autonomous_in625_production_mission.v1.json")
POLICY_REL = Path(
    "configs/research/in625_geometry_condition_multisource_acquisition_policy.v1.json"
)
REGISTRY_REL = Path(
    "configs/research/in625_geometry_condition_source_reconnaissance.v1.json"
)
TARGET_PROCESS_REL = Path(
    "data/case_studies/nist_ambench_2018_02/source_process_conditions.csv"
)
TARGET_RESPONSE_REL = Path(
    "data/case_studies/nist_ambench_2018_02/source_melt_pool_measurements.csv"
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
        raise RuntimeError(f"{path} must contain one JSON object")
    return value


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _require_sha(value: object, label: str) -> str:
    _require(
        isinstance(value, str)
        and len(value) == 64
        and all(ch in "0123456789abcdef" for ch in value),
        f"{label} must be lowercase SHA-256",
    )
    return str(value)


def _require_file_sha(path: Path, expected: str, label: str) -> None:
    _require_sha(expected, f"{label} expected SHA-256")
    observed = _file_sha(path)
    _require(
        observed == expected,
        f"{label} changed after freeze: expected {expected}, observed {observed}",
    )


def _require_object_sha(value: Mapping[str, Any], expected: str, label: str) -> None:
    _require_sha(expected, f"{label} object SHA-256")
    observed = canonical_sha256(value)
    _require(
        observed == expected,
        f"{label} object changed after freeze: expected {expected}, observed {observed}",
    )


def _package_for_artifact(root: Path, artifact_name: str) -> tuple[Path, dict[str, Any]]:
    matches: list[tuple[Path, dict[str, Any]]] = []
    for receipt_path in sorted(root.glob("packages/*/acquisition_receipt.json")):
        receipt = _load_json(receipt_path)
        if receipt.get("artifact_path") == artifact_name:
            matches.append((receipt_path.parent, receipt))
    _require(
        len(matches) == 1,
        f"artifact {artifact_name!r} must resolve to exactly one authenticated package",
    )
    return matches[0]


def _authenticated_artifact(
    root: Path,
    artifact_name: str,
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
    _require(
        authenticated.get("recorded_acquisition_provenance_authenticated") is True,
        f"acquisition provenance did not authenticate for {artifact_name}",
    )
    _require(
        hashlib.sha256(evidence_bytes).hexdigest() == receipt.get("artifact_sha256"),
        f"artifact receipt SHA mismatch for {artifact_name}",
    )
    _require(
        len(evidence_bytes) == receipt.get("artifact_size_bytes"),
        f"artifact receipt byte-size mismatch for {artifact_name}",
    )
    _require(
        hashlib.sha256(metadata_bytes).hexdigest() == receipt.get("metadata_sha256"),
        f"metadata receipt SHA mismatch for {artifact_name}",
    )
    return evidence_bytes, metadata_bytes, receipt


def _mds2_source_material(
    acquisition_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, str], bytes, bytes, bytes]:
    workbook, workbook_metadata, workbook_receipt = _authenticated_artifact(
        acquisition_root,
        "Master_TrackList_Measurements.xlsx",
    )
    readme, readme_metadata, readme_receipt = _authenticated_artifact(
        acquisition_root,
        "2923_README.txt",
    )
    _require(
        workbook_metadata == readme_metadata,
        "README and workbook packages use different NERDm metadata bytes",
    )
    material = build_mds2_2923_ammt_195_800_validation_material(
        workbook_bytes=workbook,
        readme_bytes=readme,
        nerdm_metadata_bytes=workbook_metadata,
    )
    _require(len(material) == 18, "live mds2 target subset must contain exactly 18 rows")
    roots = {
        "workbook_sha256": str(workbook_receipt["artifact_sha256"]),
        "readme_sha256": str(readme_receipt["artifact_sha256"]),
        "nerdm_metadata_sha256": hashlib.sha256(workbook_metadata).hexdigest(),
    }
    return material, roots, workbook, readme, workbook_metadata


def _context_attribute(packet: Mapping[str, Any], context: str, name: str) -> object:
    contexts = packet.get("contexts")
    _require(isinstance(contexts, Mapping), "packet contexts are missing")
    section = contexts.get(context)
    _require(isinstance(section, Mapping), f"packet context {context!r} is missing")
    attrs = section.get("attributes")
    _require(isinstance(attrs, list), f"packet context {context!r} attributes are missing")
    matches = [
        item.get("value")
        for item in attrs
        if isinstance(item, Mapping) and item.get("name") == name
    ]
    _require(len(matches) == 1, f"packet attribute {context}.{name} must occur once")
    return matches[0]


def _select_nist_item(repository_root: Path) -> dict[str, Any]:
    material = build_nist_ambench_trace_validation_material(repository_root)
    matches = [
        item
        for item in material
        if isinstance(item, dict)
        and float(_context_attribute(item["packet"], "process", "scan_speed_mm_s")) == 800.0
    ]
    _require(bool(matches), "no authenticated NIST AM-Bench 800 mm/s trace packet is available")
    return sorted(matches, key=lambda item: str(item["evidence_id"]))[0]


def _direct_comparison_claim() -> dict[str, Any]:
    required = {
        "material_identity",
        "process_route",
        "sample_acquisition_identity",
        "instrument_state_calibration",
        "acquisition_parameters",
        "units_reference_conventions",
        "target_response_semantics",
    }
    dimensions = [rule.dimension for rule in DEFAULT_RULE_REGISTRY]
    return {
        "claim_id": "in625-direct-cross-source-quantitative-comparison-v1",
        "claim_type": "direct_quantitative_cross_source_validation",
        "required_dimensions": [
            dimension for dimension in dimensions if dimension in required
        ],
        "irrelevant_dimensions": [
            dimension for dimension in dimensions if dimension not in required
        ],
        "allowed_transformations": [],
        "requires_independent_replication": False,
        "maximum_downstream_use_requested": "comparative",
    }


def _input_from_item(item: Mapping[str, Any], trusted_expectation_sha256: str) -> AuthenticatedEvidenceInput:
    packet = item.get("packet")
    artifacts = item.get("artifacts")
    expected = item.get("expected")
    _require(
        isinstance(packet, Mapping)
        and isinstance(artifacts, Mapping)
        and isinstance(expected, Mapping),
        "validation material item is malformed",
    )
    _require(
        canonical_sha256(expected) == trusted_expectation_sha256,
        f"expectation root drifted for {item.get('evidence_id')!r}",
    )
    return AuthenticatedEvidenceInput(
        packet=packet,
        artifacts=artifacts,
        expected=expected,
        trusted_expectation_sha256=trusted_expectation_sha256,
    )


def _material_index(material: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in material:
        evidence_id = item.get("evidence_id")
        _require(isinstance(evidence_id, str) and evidence_id, "evidence_id is missing")
        _require(evidence_id not in result, "duplicate evidence_id in validation material")
        result[evidence_id] = item
    return result


def _load_authenticated_context(
    *,
    path: Path,
    file_sha256: str,
    object_sha256: str,
) -> dict[str, Any]:
    _require_file_sha(path, file_sha256, "full-episode context")
    context = _load_json(path)
    _require_object_sha(context, object_sha256, "full-episode context")
    embedded = _require_sha(context.get("context_sha256"), "context.context_sha256")
    unsigned = copy.deepcopy(context)
    unsigned.pop("context_sha256", None)
    _require(
        canonical_sha256(unsigned) == embedded,
        "context embedded self-hash mismatch",
    )
    return context


def _reconstruct_inputs(
    *,
    repository_root: Path,
    acquisition_root: Path,
    context: Mapping[str, Any],
) -> tuple[
    AuthenticatedEvidenceInput,
    AuthenticatedEvidenceInput,
    list[AuthenticatedEvidenceInput],
]:
    mds2_material, source_roots, _workbook, _readme, _metadata = _mds2_source_material(
        acquisition_root
    )
    _require(
        context.get("mds2_source_roots") == source_roots,
        "live mds2 source bytes differ from frozen context",
    )
    mds2_by_id = _material_index(mds2_material)
    mds2_roots = context.get("mds2_expectation_sha256_by_evidence_id")
    _require(isinstance(mds2_roots, Mapping), "frozen mds2 expectation roots are missing")
    _require(
        set(mds2_by_id) == set(mds2_roots),
        "live mds2 evidence universe differs from frozen context",
    )
    spot_inputs = [
        _input_from_item(mds2_by_id[evidence_id], str(mds2_roots[evidence_id]))
        for evidence_id in sorted(mds2_by_id)
    ]

    comparison_id = context.get("mds2_comparison_evidence_id")
    _require(
        isinstance(comparison_id, str) and comparison_id in mds2_by_id,
        "frozen mds2 comparison evidence id is unavailable",
    )
    mds2_comparison = _input_from_item(
        mds2_by_id[comparison_id],
        str(mds2_roots[comparison_id]),
    )

    nist_item = _select_nist_item(repository_root)
    _require(
        nist_item.get("evidence_id") == context.get("nist_comparison_evidence_id"),
        "NIST comparison evidence identity changed after freeze",
    )
    nist_root = _require_sha(
        context.get("nist_comparison_expectation_sha256"),
        "nist comparison expectation root",
    )
    nist_input = _input_from_item(nist_item, nist_root)
    _require(
        nist_input.packet.get("packet_sha256")
        == context.get("nist_comparison_packet_sha256"),
        "NIST comparison packet changed after freeze",
    )
    return nist_input, mds2_comparison, spot_inputs


def freeze_context(args: argparse.Namespace) -> int:
    repository_root = args.repository_root.expanduser().resolve(strict=True)
    acquisition_root = args.acquisition_root.expanduser().resolve(strict=True)
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    mds2_material, source_roots, workbook, readme, metadata = _mds2_source_material(
        acquisition_root
    )
    mds2_by_id = _material_index(mds2_material)
    mds2_expectation_roots = {
        evidence_id: canonical_sha256(item["expected"])
        for evidence_id, item in sorted(mds2_by_id.items())
    }
    mds2_packet_roots = {
        evidence_id: str(item["packet"]["packet_sha256"])
        for evidence_id, item in sorted(mds2_by_id.items())
    }
    comparison_id = sorted(mds2_by_id)[0]

    nist_item = _select_nist_item(repository_root)
    nist_expectation_sha = canonical_sha256(nist_item["expected"])

    mission = (repository_root / MISSION_REL).resolve(strict=True)
    policy = (repository_root / POLICY_REL).resolve(strict=True)
    registry_path = (repository_root / REGISTRY_REL).resolve(strict=True)
    qualification = authenticate_geometry_condition_multisource_policy(
        repository_root=repository_root,
        mission_path=mission,
        expected_mission_sha256=args.expected_mission_sha256,
        policy_path=policy,
        registry_path=registry_path,
    )
    registry = _load_json(registry_path)
    multisource = acquire_geometry_condition_sources(
        qualification=qualification,
        source_registry=registry,
    )
    intake = audit_mds2_2923(
        workbook_bytes=workbook,
        readme_bytes=readme,
        nerdm_metadata_bytes=metadata,
    )
    bridge = build_geometry_condition_mapping_assessment(
        nist_intake=intake,
        multisource_evidence=multisource,
        target_process_bytes=(repository_root / TARGET_PROCESS_REL).read_bytes(),
        target_response_bytes=(repository_root / TARGET_RESPONSE_REL).read_bytes(),
    )
    claim = _direct_comparison_claim()

    _require(
        bridge["gate_decision"]["directly_comparable_mds2_rows"] == 0
        and bridge["gate_decision"]["direct_numerical_validation_authorized"] is False
        and bridge["gate_decision"]["issue_76_exact_target_cells_satisfied"] == 0,
        "live bridge unexpectedly widened direct comparison authority",
    )

    context: dict[str, Any] = {
        "schema_version": "1.0",
        "context_type": "in625_live_full_episode_frozen_context",
        "mission_file_sha256": args.expected_mission_sha256,
        "multisource_policy_qualification_sha256": canonical_sha256(qualification),
        "multisource_acquisition_report_sha256": multisource[
            "report_sha256_without_self_field"
        ],
        "multisource_source_sha256_by_id": {
            str(item["source_id"]): str(item["source_sha256"])
            for item in multisource["sources"]
        },
        "mds2_source_roots": source_roots,
        "mds2_expectation_sha256_by_evidence_id": mds2_expectation_roots,
        "mds2_packet_sha256_by_evidence_id": mds2_packet_roots,
        "mds2_comparison_evidence_id": comparison_id,
        "nist_comparison_evidence_id": nist_item["evidence_id"],
        "nist_comparison_expectation_sha256": nist_expectation_sha,
        "nist_comparison_packet_sha256": nist_item["packet"]["packet_sha256"],
        "bridge_state": bridge,
        "bridge_state_sha256": canonical_sha256(bridge),
        "direct_comparison_claim": claim,
        "direct_comparison_claim_sha256": canonical_sha256(claim),
        "authority_boundary": {
            "scientific_status_promoted": False,
            "direct_cross_source_comparison_authorized": False,
            "issue_76_exact_target_cells_satisfied": 0,
        },
    }
    context["context_sha256"] = canonical_sha256(context)

    _write_json(output_dir / "multisource_policy_qualification.json", qualification)
    _write_json(output_dir / "multisource_source_acquisition.json", multisource)
    _write_json(output_dir / "geometry_condition_mapping_assessment.json", bridge)
    _write_json(output_dir / "direct_comparison_claim.json", claim)
    _write_json(output_dir / "full_episode_context.json", context)
    _write_json(
        output_dir / "expectation_roots.json",
        {
            "schema_version": "1.0",
            "purpose": "externally_frozen_live_benchmark_expectation_roots",
            "source": source_roots,
            "evidence_count": len(mds2_material),
            "trusted_expectation_sha256_by_evidence_id": mds2_expectation_roots,
            "packet_sha256_by_evidence_id": mds2_packet_roots,
            "scientific_status_promoted": False,
        },
    )
    print(
        json.dumps(
            {
                "context_file_sha256": _file_sha(output_dir / "full_episode_context.json"),
                "context_object_sha256": canonical_sha256(context),
                "bridge_state_sha256": context["bridge_state_sha256"],
                "claim_sha256": context["direct_comparison_claim_sha256"],
                "nist_evidence_id": context["nist_comparison_evidence_id"],
                "mds2_comparison_evidence_id": comparison_id,
                "spot_evidence_count": len(mds2_material),
                "multisource_count": len(multisource["sources"]),
            },
            sort_keys=True,
        )
    )
    return 0


def build_bootstrap(args: argparse.Namespace) -> int:
    repository_root = args.repository_root.expanduser().resolve(strict=True)
    acquisition_root = args.acquisition_root.expanduser().resolve(strict=True)
    context = _load_authenticated_context(
        path=args.context,
        file_sha256=args.context_file_sha256,
        object_sha256=args.context_object_sha256,
    )
    nist_input, mds2_comparison, _spot_inputs = _reconstruct_inputs(
        repository_root=repository_root,
        acquisition_root=acquisition_root,
        context=context,
    )
    bridge = context.get("bridge_state")
    claim = context.get("direct_comparison_claim")
    _require(
        isinstance(bridge, Mapping) and isinstance(claim, Mapping),
        "frozen context bridge/claim are malformed",
    )
    bootstrap = build_in625_competency_bootstrap(
        nist_evidence=nist_input,
        mds2_evidence=mds2_comparison,
        bridge_state=bridge,
        trusted_bridge_state_sha256=_require_sha(
            context.get("bridge_state_sha256"), "bridge_state_sha256"
        ),
        direct_comparison_claim=claim,
        trusted_claim_scope_sha256=_require_sha(
            context.get("direct_comparison_claim_sha256"),
            "direct_comparison_claim_sha256",
        ),
    )
    iteration = build_in625_competency_iteration(
        bootstrap,
        trusted_bootstrap_sha256=canonical_sha256(bootstrap),
    )
    selected = iteration["plan"]["selected_next_action"]
    _require(isinstance(selected, Mapping), "full benchmark planner selected no action")
    _require(
        selected.get("action_class") == "sensitivity_analysis",
        "full authenticated state did not autonomously select the implemented sensitivity "
        f"capability; selected={selected!r}",
    )
    _write_json(args.bootstrap_output, bootstrap)
    _write_json(args.iteration_output, iteration)
    print(
        json.dumps(
            {
                "bootstrap_file_sha256": _file_sha(args.bootstrap_output),
                "bootstrap_object_sha256": canonical_sha256(bootstrap),
                "iteration_file_sha256": _file_sha(args.iteration_output),
                "iteration_object_sha256": canonical_sha256(iteration),
                "comparability_status": bootstrap["comparability_assessment"][
                    "assessment_status"
                ],
                "hypothesis_count": len(bootstrap["hypothesis_portfolio"]),
                "candidate_action_count": len(iteration["plan"]["ranked_actions"]),
                "selected_action_id": selected.get("action_id"),
                "selected_action_class": selected.get("action_class"),
                "selected_utility": selected.get("utility_score"),
            },
            sort_keys=True,
        )
    )
    return 0


def closeout(args: argparse.Namespace) -> int:
    repository_root = args.repository_root.expanduser().resolve(strict=True)
    acquisition_root = args.acquisition_root.expanduser().resolve(strict=True)
    context = _load_authenticated_context(
        path=args.context,
        file_sha256=args.context_file_sha256,
        object_sha256=args.context_object_sha256,
    )
    nist_input, mds2_comparison, spot_inputs = _reconstruct_inputs(
        repository_root=repository_root,
        acquisition_root=acquisition_root,
        context=context,
    )

    for path, expected, label in (
        (args.bootstrap, args.bootstrap_file_sha256, "bootstrap"),
        (args.iteration, args.iteration_file_sha256, "iteration"),
        (args.request, args.request_file_sha256, "request"),
        (args.authorization, args.authorization_file_sha256, "authorization"),
        (args.result, args.result_file_sha256, "verified result"),
    ):
        _require_file_sha(path, expected, label)

    bootstrap = _load_json(args.bootstrap)
    iteration = _load_json(args.iteration)
    request = _load_json(args.request)
    authorization = _load_json(args.authorization)
    result = _load_json(args.result)
    _require_object_sha(bootstrap, args.bootstrap_object_sha256, "bootstrap")
    _require_object_sha(iteration, args.iteration_object_sha256, "iteration")
    _require_object_sha(request, args.request_object_sha256, "request")
    _require_object_sha(
        authorization, args.authorization_object_sha256, "authorization"
    )
    _require_object_sha(result, args.result_object_sha256, "verified result")

    claim = context.get("direct_comparison_claim")
    _require(isinstance(claim, Mapping), "frozen direct comparison claim is malformed")
    closeout_value = build_in625_competency_bounded_closeout(
        bootstrap=bootstrap,
        trusted_bootstrap_sha256=args.bootstrap_object_sha256,
        first_iteration=iteration,
        trusted_iteration_sha256=args.iteration_object_sha256,
        nist_evidence=nist_input,
        mds2_comparison_evidence=mds2_comparison,
        direct_comparison_claim=claim,
        trusted_claim_scope_sha256=_require_sha(
            context.get("direct_comparison_claim_sha256"),
            "direct_comparison_claim_sha256",
        ),
        request=request,
        authorization_receipt=authorization,
        trusted_authorization_sha256=args.authorization_object_sha256,
        sensitivity_result=result,
        trusted_result_sha256=args.result_object_sha256,
        spot_evidence_inputs=spot_inputs,
        epistemic_output_root=args.epistemic_output_root,
    )
    _require(
        closeout_value["episode_status"]
        == "external_evidence_required_before_direct_comparison",
        "live full episode did not stop at the expected scientific evidence boundary",
    )
    _require(
        closeout_value["comparability_reassessment"]["assessment_unchanged"] is True
        and closeout_value["comparability_reassessment"]["direct_comparison_authorized"]
        is False,
        "live closeout widened cross-source comparability",
    )
    _require(
        closeout_value["action_trace"]["execution_verified"] is True
        and closeout_value["action_trace"]["independent_recomputation_performed"] is True
        and closeout_value["action_trace"][
            "epistemic_transition_published_and_reauthenticated"
        ]
        is True
        and closeout_value["action_trace"]["scientific_critic_rerun"] is True,
        "live closeout did not complete the action/transition/critic chain",
    )
    _require(
        closeout_value["authority_boundary"]["positive_scientific_closeout_granted"]
        is False
        and closeout_value["authority_boundary"]["scientific_status_promoted"] is False,
        "live full episode improperly promoted scientific authority",
    )
    _write_json(args.output, closeout_value)
    print(
        json.dumps(
            {
                "closeout_file_sha256": _file_sha(args.output),
                "closeout_object_sha256": canonical_sha256(closeout_value),
                "episode_status": closeout_value["episode_status"],
                "comparability_status": closeout_value["comparability_reassessment"][
                    "final_status"
                ],
                "stable_signed_association": closeout_value["bounded_conclusion"][
                    "leave_one_spot_level_signed_association_stable"
                ],
                "next_candidate_action_classes": closeout_value["action_trace"][
                    "next_candidate_action_classes"
                ],
                "stop": closeout_value["stop_decision"]["stop_current_episode"],
            },
            sort_keys=True,
        )
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the real-evidence IN625 full Autonomous Research Scientist episode."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    freeze = sub.add_parser("freeze-context")
    freeze.add_argument("--repository-root", type=Path, required=True)
    freeze.add_argument("--acquisition-root", type=Path, required=True)
    freeze.add_argument("--expected-mission-sha256", required=True)
    freeze.add_argument("--output-dir", type=Path, required=True)
    freeze.set_defaults(func=freeze_context)

    bootstrap = sub.add_parser("build-bootstrap")
    bootstrap.add_argument("--repository-root", type=Path, required=True)
    bootstrap.add_argument("--acquisition-root", type=Path, required=True)
    bootstrap.add_argument("--context", type=Path, required=True)
    bootstrap.add_argument("--context-file-sha256", required=True)
    bootstrap.add_argument("--context-object-sha256", required=True)
    bootstrap.add_argument("--bootstrap-output", type=Path, required=True)
    bootstrap.add_argument("--iteration-output", type=Path, required=True)
    bootstrap.set_defaults(func=build_bootstrap)

    done = sub.add_parser("closeout")
    done.add_argument("--repository-root", type=Path, required=True)
    done.add_argument("--acquisition-root", type=Path, required=True)
    done.add_argument("--context", type=Path, required=True)
    done.add_argument("--context-file-sha256", required=True)
    done.add_argument("--context-object-sha256", required=True)
    for name in ("bootstrap", "iteration", "request", "authorization", "result"):
        done.add_argument(f"--{name}", type=Path, required=True)
        done.add_argument(f"--{name}-file-sha256", required=True)
        done.add_argument(f"--{name}-object-sha256", required=True)
    done.add_argument("--epistemic-output-root", type=Path, required=True)
    done.add_argument("--output", type=Path, required=True)
    done.set_defaults(func=closeout)
    return parser


def main() -> int:
    args = _parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
