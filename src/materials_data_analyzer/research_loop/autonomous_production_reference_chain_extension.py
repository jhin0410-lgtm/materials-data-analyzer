"""Extend autonomous IN625 production through the mds2-2923 reference-chain frontier."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from . import mds2_2923_experiment_identity_reference_chain as reference_chain
from . import mds2_2923_reference_chain_capability as reference_capability
from .autonomous_production_candidate_acquisition_extension import (
    run_autonomous_production as run_candidate_acquisition_production,
)
from .capability_expansion import build_capability_gap, build_capability_specification
from .capability_registry import promote_verified_capability
from .capability_resolver import resolve_or_discover_capability
from .mds2_2923_reference_chain_capability_verifier import (
    verify_reference_chain_capability_candidate,
)
from .nist_mds2_2923_reference_chain_evidence import (
    acquire_naderi_reference_chain_evidence,
)
from .nist_mds2_2923_reference_chain_policy import (
    authenticate_nist_mds2_2923_reference_chain_policy,
)

AUTONOMOUS_PRODUCTION_SCHEMA_VERSION = "1.8"
AUTONOMOUS_PRODUCTION_POLICY_VERSION = "1.8"
_VERIFIED_PRIMITIVES = (
    "exact_multisource_policy_authentication",
    "exact_allowlisted_source_acquisition",
    "provenance_bound_bridge_frontier_evaluation",
    "mission_pinned_source_index_authentication",
    "bounded_official_index_retrieval",
    "provenance_bound_candidate_ranking",
    "authenticated_discovery_report_binding",
    "derived_candidate_url_authorization",
    "candidate_page_local_download_derivation",
    "bounded_nist_pdf_acquisition",
    "provenance_bound_calibration_intake",
)
_AVAILABLE_ACTION_CLASSES = (
    "external_evidence_search",
    "reviewed_physical_comparability_assessment",
    "nist_mds2_2923_geometry_evidence_acquisition",
    "reviewed_geometry_condition_mapping_assessment",
    "ammt_mds2_2923_calibration_protocol_bridge_evidence_acquisition",
    "experiment_specific_calibration_record_source_discovery",
    "experiment_specific_calibration_record_candidate_acquisition",
    reference_capability.ACTION_CLASS,
)


class AutonomousProductionReferenceChainExtensionError(ValueError):
    """Raised when reference-chain extension would violate predecessor or source authority."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionReferenceChainExtensionError(message)


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _read_json(path: Path, field: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AutonomousProductionReferenceChainExtensionError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    _require(isinstance(value, dict), f"{field} root must be an object")
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _validate_self_hash(value: Mapping[str, Any], field: str) -> str:
    digest = value.get(field)
    _require(isinstance(digest, str) and len(digest) == 64, f"{field} is missing")
    unsigned = dict(value)
    unsigned.pop(field, None)
    _require(_canonical_sha(unsigned) == digest, f"{field} is invalid")
    return digest


def _authenticate_predecessor_candidate(
    *,
    predecessor_resolution: Mapping[str, Any],
    predecessor_candidate: Mapping[str, Any],
    capability_specification: Mapping[str, Any],
    predecessor_manifest_sha256: str,
) -> dict[str, Any]:
    """Re-authenticate the exact cycle-10 candidate without rediscovering it."""
    spec_sha = _validate_self_hash(
        capability_specification,
        "capability_specification_sha256_without_self_field",
    )
    candidate_sha = _validate_self_hash(
        predecessor_candidate,
        "capability_candidate_sha256_without_self_field",
    )
    resolution_candidate = predecessor_resolution.get("candidate")
    _require(
        predecessor_resolution.get("resolution_status") == "bounded_candidate_discovered"
        and isinstance(resolution_candidate, Mapping),
        "predecessor did not persist a bounded reference-chain candidate",
    )
    _require(
        dict(resolution_candidate) == dict(predecessor_candidate),
        "predecessor resolution/candidate artifact binding drifted",
    )
    _require(
        predecessor_candidate.get("state") == "candidate"
        and predecessor_candidate.get("action_class") == reference_capability.ACTION_CLASS
        and predecessor_candidate.get("implementation_id")
        == reference_capability.IMPLEMENTATION_ID
        and predecessor_candidate.get("factory_id") == reference_capability.FACTORY_ID
        and predecessor_candidate.get("mechanism") == reference_capability.MECHANISM,
        "predecessor reference-chain candidate identity drifted",
    )
    _require(
        predecessor_candidate.get("capability_specification_sha256") == spec_sha,
        "predecessor candidate specification binding drifted",
    )
    _require(
        predecessor_candidate.get("network_authority_granted") is False
        and predecessor_candidate.get("execution_authority_granted") is False
        and predecessor_candidate.get("scientific_status_change_authorized") is False
        and predecessor_candidate.get("self_promotion_requested") is False,
        "predecessor candidate attempted to acquire authority before verification",
    )
    receipt: dict[str, Any] = {
        "schema_version": "1.0",
        "artifact_type": "predecessor_capability_candidate_reauthentication",
        "resolution_status": "predecessor_candidate_reauthenticated",
        "action_class": reference_capability.ACTION_CLASS,
        "capability_specification_sha256": spec_sha,
        "capability_candidate_sha256": candidate_sha,
        "predecessor_manifest_sha256": predecessor_manifest_sha256,
        "candidate_rediscovery_performed": False,
        "unrestricted_discovery_performed": False,
        "network_authority_granted": False,
        "execution_authority_granted": False,
        "scientific_status_changed": False,
    }
    receipt["report_sha256_without_self_field"] = _canonical_sha(receipt)
    return receipt


def _resolved_output(root: Path, output_root: str | Path) -> Path:
    output = Path(output_root).expanduser()
    if not output.is_absolute():
        output = root / output
    output = output.resolve(strict=True)
    try:
        output.relative_to(root)
    except ValueError as exc:
        raise AutonomousProductionReferenceChainExtensionError(
            "autonomous production output escaped repository root"
        ) from exc
    return output


def _stop(reason_code: str, action_class: str, **extra: Any) -> dict[str, Any]:
    return {
        "status": "stopped",
        "reason_code": reason_code,
        "requested_action_class": action_class,
        "scope": "verified_registry_and_mission_pinned_reference_authority",
        "global_evidence_unavailability_claimed": False,
        "positive_scientific_closeout": False,
        "scientific_status_changed": False,
        **extra,
    }


def _finalize(
    *,
    output: Path,
    predecessor_manifest: Mapping[str, Any],
    cycles: list[dict[str, Any]],
    stop: Mapping[str, Any],
    updates: Mapping[str, Any],
) -> dict[str, Any]:
    result = dict(predecessor_manifest)
    result.pop("manifest_sha256", None)
    result.update(
        {
            "schema_version": AUTONOMOUS_PRODUCTION_SCHEMA_VERSION,
            "policy_version": AUTONOMOUS_PRODUCTION_POLICY_VERSION,
            "cycles": cycles,
            "stop": dict(stop),
            "scientific_status_changed": False,
            "positive_scientific_closeout_established": False,
            "global_evidence_unavailability_claimed": False,
            **dict(updates),
        }
    )
    result["manifest_sha256"] = _canonical_sha(result)
    _write_json(output / "bounded-stop.json", stop)
    _write_json(output / "autonomous-production-manifest.json", result)
    return result


def run_autonomous_production(
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    output_root: str | Path,
    max_cycles: int = 12,
) -> dict[str, Any]:
    """Run the fourth capability expansion and resume exact reference-chain assessment."""
    if (
        isinstance(max_cycles, bool)
        or not isinstance(max_cycles, int)
        or max_cycles < 1
        or max_cycles > 12
    ):
        raise AutonomousProductionReferenceChainExtensionError(
            "max_cycles must be an integer from 1 to 12"
        )
    root = Path(repository_root).expanduser().resolve(strict=True)
    mission = Path(mission_path).expanduser().resolve(strict=True)
    try:
        mission.relative_to(root)
    except ValueError as exc:
        raise AutonomousProductionReferenceChainExtensionError(
            "mission_path must remain inside repository_root"
        ) from exc
    _require(
        hashlib.sha256(mission.read_bytes()).hexdigest() == expected_mission_sha256,
        "mission bytes do not match independently pinned mission SHA-256",
    )

    if max_cycles <= 10:
        return run_candidate_acquisition_production(
            repository_root=root,
            mission_path=mission,
            expected_mission_sha256=expected_mission_sha256,
            output_root=output_root,
            max_cycles=max_cycles,
        )

    run_candidate_acquisition_production(
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=expected_mission_sha256,
        output_root=output_root,
        max_cycles=10,
    )
    output = _resolved_output(root, output_root)
    predecessor = _read_json(
        output / "autonomous-production-manifest.json",
        "candidate-acquisition predecessor manifest",
    )
    predecessor_sha = _validate_self_hash(predecessor, "manifest_sha256")
    _require(
        predecessor.get("generated_next_action_class") == reference_capability.ACTION_CLASS
        and predecessor.get("fourth_capability_gap_emitted") is True
        and predecessor.get("fourth_capability_candidate_discovered") is True
        and predecessor.get("fourth_capability_candidate_promoted") is False
        and predecessor.get("third_research_action_resumed") is True,
        "predecessor did not stop at exact discovered reference-chain candidate frontier",
    )
    _require(
        predecessor.get("bridge_established") is False
        and predecessor.get("directly_comparable_mds2_rows") == 0
        and predecessor.get("issue_76_exact_target_cells_satisfied") == 0,
        "predecessor scientific boundary drifted",
    )
    raw_cycles = predecessor.get("cycles")
    _require(isinstance(raw_cycles, list) and len(raw_cycles) == 10, "predecessor cycles drifted")
    cycles = [dict(item) for item in raw_cycles if isinstance(item, Mapping)]
    _require(len(cycles) == 10, "predecessor cycle entries are invalid")

    registry = _read_json(
        output / "capability-registry-promoted-3.json",
        "third promoted capability registry",
    )
    fourth_gap = _read_json(output / "capability-gap-4.json", "fourth capability gap")
    fourth_spec = _read_json(
        output / "capability-specification-4.json", "fourth capability specification"
    )
    predecessor_resolution = _read_json(
        output / "capability-resolution-4.json",
        "predecessor fourth capability resolution",
    )
    predecessor_candidate = _read_json(
        output / "capability-candidate-4.json",
        "predecessor fourth capability candidate",
    )
    _validate_self_hash(fourth_gap, "capability_gap_sha256_without_self_field")
    _validate_self_hash(
        fourth_spec, "capability_specification_sha256_without_self_field"
    )
    _require(
        fourth_gap.get("requested_action_class") == reference_capability.ACTION_CLASS
        and fourth_spec.get("requested_action_class") == reference_capability.ACTION_CLASS,
        "fourth gap/spec action drifted",
    )
    candidate_reauthentication = _authenticate_predecessor_candidate(
        predecessor_resolution=predecessor_resolution,
        predecessor_candidate=predecessor_candidate,
        capability_specification=fourth_spec,
        predecessor_manifest_sha256=predecessor_sha,
    )
    _write_json(
        output / "capability-resolution-4-derived.json",
        candidate_reauthentication,
    )
    candidate = dict(predecessor_candidate)

    nist_intake = _read_json(output / "nist-scientific-intake.json", "NIST scientific intake")
    multisource = _read_json(
        output / "multisource-source-acquisition.json", "multisource evidence"
    )
    source_discovery = _read_json(
        output / "calibration-record-source-discovery.json", "calibration source discovery"
    )
    calibration_assessment = _read_json(
        output / "nist-ammt-calibration-candidate-bridge-assessment.json",
        "calibration candidate bridge assessment",
    )
    for report, field in (
        (nist_intake, "report_sha256_without_self_field"),
        (multisource, "report_sha256_without_self_field"),
        (source_discovery, "report_sha256_without_self_field"),
        (calibration_assessment, "report_sha256_without_self_field"),
    ):
        _validate_self_hash(report, field)
    metadata_path = (output / "nist-mds2-2923" / "nerdm-metadata.json").resolve(strict=True)
    try:
        metadata_path.relative_to(output)
    except ValueError as exc:
        raise AutonomousProductionReferenceChainExtensionError(
            "predecessor NERDm metadata escaped output root"
        ) from exc
    metadata_bytes = metadata_path.read_bytes()
    metadata_sha = hashlib.sha256(metadata_bytes).hexdigest()
    source = nist_intake.get("source")
    _require(
        isinstance(source, Mapping)
        and source.get("nerdm_metadata_sha256") == metadata_sha
        and predecessor.get("nist_mds2_2923_metadata_sha256") == metadata_sha,
        "predecessor NERDm byte binding drifted",
    )

    cycle11: dict[str, Any] = {
        "cycle_index": 11,
        "predecessor_cycle_sha256": cycles[-1]["cycle_sha256"],
        "input_blocker": "experiment_identity_reference_chain_capability_not_established",
        "selected_action_class": reference_capability.ACTION_CLASS,
        "capability_available": False,
        "resolution_status": candidate_reauthentication["resolution_status"],
        "bounded_candidate_discovered": False,
        "predecessor_candidate_reauthenticated": True,
        "candidate_rediscovery_performed": False,
        "capability_candidate_sha256": candidate[
            "capability_candidate_sha256_without_self_field"
        ],
        "predecessor_manifest_sha256": predecessor_sha,
        "nerdm_metadata_sha256": metadata_sha,
        "caller_authored_url_used": False,
        "arbitrary_code_generation_performed": False,
        "global_evidence_unavailability_claimed": False,
        "new_verified_information": False,
        "scientific_status_changed": False,
    }
    cycle11["cycle_sha256"] = _canonical_sha(cycle11)
    cycles.append(cycle11)
    if max_cycles == 11:
        return _finalize(
            output=output,
            predecessor_manifest=predecessor,
            cycles=cycles,
            stop=_stop(
                "maximum_cycles_reached",
                reference_capability.ACTION_CLASS,
                capability_expansion_ready=True,
            ),
            updates={
                "fourth_capability_candidate_discovered": True,
                "fourth_capability_candidate_promoted": False,
                "fourth_research_action_resumed": False,
                "fourth_candidate_reauthenticated_from_predecessor": True,
                "fourth_candidate_rediscovery_performed": False,
                "generated_next_action_class": reference_capability.ACTION_CLASS,
            },
        )

    verification_context = {
        "nerdm_metadata_bytes": metadata_bytes,
        "nist_intake": nist_intake,
        "multisource_evidence": multisource,
        "source_discovery_report": source_discovery,
        "calibration_candidate_assessment": calibration_assessment,
    }
    verification = verify_reference_chain_capability_candidate(
        capability_specification=fourth_spec,
        candidate=candidate,
        available_verified_primitives=_VERIFIED_PRIMITIVES,
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=expected_mission_sha256,
        verification_context=verification_context,
        perform_real_source_smoke=True,
    )
    _write_json(output / "capability-verification-4.json", verification)
    _require(
        verification.get("promotion_eligible") is True,
        "reference-chain capability failed independent verification",
    )
    promoted_registry = promote_verified_capability(
        registry=registry,
        candidate=candidate,
        verification_receipt=verification,
    )
    _write_json(output / "capability-registry-promoted-4.json", promoted_registry)
    resolved = resolve_or_discover_capability(
        registry=promoted_registry,
        capability_specification=fourth_spec,
        available_verified_primitives=_VERIFIED_PRIMITIVES,
    )
    _write_json(output / "capability-post-promotion-resolution-4.json", resolved)
    _require(
        resolved.get("resolution_status") == "verified_capability_resolved"
        and resolved.get("implementation_id") == reference_capability.IMPLEMENTATION_ID,
        "promoted reference-chain capability did not resolve exact blocked action",
    )

    qualification = authenticate_nist_mds2_2923_reference_chain_policy(
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=expected_mission_sha256,
    )
    _write_json(
        output / "nist-mds2-2923-reference-chain-policy-qualification.json",
        qualification,
    )
    naderi = acquire_naderi_reference_chain_evidence(qualification=qualification)
    _write_json(output / "nist-mds2-2923-reference-chain-evidence.json", naderi)
    graph = reference_chain.build_mds2_2923_experiment_identity_reference_chain(
        nerdm_metadata_bytes=metadata_bytes,
        nist_intake=nist_intake,
        naderi_reference_evidence=naderi,
        multisource_evidence=multisource,
        source_discovery_report=source_discovery,
        calibration_candidate_assessment=calibration_assessment,
    )
    _write_json(output / "mds2-2923-experiment-identity-reference-chain.json", graph)
    gate = graph.get("calibration_and_protocol_gate")
    identity = graph.get("experiment_identity")
    _require(
        isinstance(gate, Mapping)
        and isinstance(identity, Mapping)
        and gate.get("directly_comparable_mds2_rows") == 0
        and gate.get("direct_numerical_cross_source_validation_authorized") is False
        and gate.get("issue_76_exact_target_cells_satisfied") == 0
        and identity.get("exact_mds2_experiment_identity_established") is False,
        "reference-chain execution improperly promoted scientific equivalence",
    )
    next_action = graph.get("next_action")
    _require(
        isinstance(next_action, Mapping)
        and next_action.get("action_class") == reference_chain.NEXT_ACTION_CLASS,
        "reference-chain next action drifted",
    )

    cycle12: dict[str, Any] = {
        "cycle_index": 12,
        "predecessor_cycle_sha256": cycle11["cycle_sha256"],
        "input_blocker": "missing_analysis_executor",
        "selected_action_class": reference_capability.ACTION_CLASS,
        "capability_available": True,
        "capability_verification_sha256": verification[
            "capability_verification_sha256_without_self_field"
        ],
        "promoted_registry_sha256": promoted_registry[
            "capability_registry_sha256_without_self_field"
        ],
        "implementation_id": reference_capability.IMPLEMENTATION_ID,
        "research_action_resumed": True,
        "execution_network_requests_performed": naderi["network_requests_performed"],
        "verifier_smoke_network_requests_performed": 1,
        "reference_graph_sha256": graph["report_sha256_without_self_field"],
        "dataset_publication_association_established": True,
        "condition_signature_match_established": True,
        "exact_mds2_experiment_identity_established": False,
        "bridge_established": False,
        "directly_comparable_mds2_rows": 0,
        "issue_76_exact_target_cells_satisfied": 0,
        "output_next_action_class": next_action["action_class"],
        "new_verified_information": True,
        "scientific_status_changed": False,
    }
    cycle12["cycle_sha256"] = _canonical_sha(cycle12)
    cycles.append(cycle12)

    fifth_gap = build_capability_gap(
        requested_action=next_action,
        predecessor_report=graph,
        available_action_classes=_AVAILABLE_ACTION_CLASSES,
    )
    fifth_spec = build_capability_specification(fifth_gap)
    fifth_resolution = resolve_or_discover_capability(
        registry=promoted_registry,
        capability_specification=fifth_spec,
        available_verified_primitives=_VERIFIED_PRIMITIVES,
    )
    _write_json(output / "capability-gap-5.json", fifth_gap)
    _write_json(output / "capability-specification-5.json", fifth_spec)
    _write_json(output / "capability-resolution-5.json", fifth_resolution)
    fifth_candidate = fifth_resolution.get("candidate")
    _require(
        fifth_resolution.get("resolution_status") == "bounded_candidate_discovered"
        and isinstance(fifth_candidate, Mapping),
        "Weaver acquisition bounded capability candidate was not discovered",
    )
    _write_json(output / "capability-candidate-5.json", fifth_candidate)
    stop = _stop(
        "capability_expansion_required",
        str(next_action["action_class"]),
        capability_gap_class=fifth_gap["gap_class"],
        bounded_candidate_discovered=True,
        caller_authored_url_used=False,
        arbitrary_code_generation_performed=False,
    )
    return _finalize(
        output=output,
        predecessor_manifest=predecessor,
        cycles=cycles,
        stop=stop,
        updates={
            "fourth_capability_candidate_discovered": True,
            "fourth_capability_candidate_promoted": True,
            "fourth_research_action_resumed": True,
            "fourth_candidate_reauthenticated_from_predecessor": True,
            "fourth_candidate_rediscovery_performed": False,
            "reference_chain_policy_sha256": qualification["policy_sha256"],
            "naderi_reference_evidence_sha256": naderi[
                "report_sha256_without_self_field"
            ],
            "reference_chain_assessment_sha256": graph[
                "report_sha256_without_self_field"
            ],
            "dataset_to_weaver_association_established": True,
            "naderi_to_weaver_experiment_detail_reference_established": True,
            "mds2_195_800_condition_signature_match": True,
            "exact_mds2_experiment_identity_established": False,
            "exact_machine_setting_to_calibrated_power_relation_established": False,
            "bridge_established": False,
            "directly_comparable_mds2_rows": 0,
            "direct_numerical_cross_source_validation_authorized": False,
            "issue_76_exact_target_cells_satisfied": 0,
            "fifth_capability_gap_emitted": True,
            "fifth_capability_candidate_discovered": True,
            "fifth_capability_candidate_promoted": False,
            "fifth_research_action_resumed": False,
            "generated_next_action_class": next_action["action_class"],
            "final_blocker": "weaver_primary_full_text_acquisition_candidate_unverified",
        },
    )


__all__ = [
    "AUTONOMOUS_PRODUCTION_POLICY_VERSION",
    "AUTONOMOUS_PRODUCTION_SCHEMA_VERSION",
    "AutonomousProductionReferenceChainExtensionError",
    "_authenticate_predecessor_candidate",
    "run_autonomous_production",
]
