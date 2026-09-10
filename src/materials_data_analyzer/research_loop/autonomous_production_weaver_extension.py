"""Extend autonomous IN625 production through Weaver 2021 full-text acquisition."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from . import weaver_2021_full_text_acquisition as weaver_acquisition
from . import weaver_2021_full_text_capability as weaver_capability
from .autonomous_production_reference_chain_extension import (
    run_autonomous_production as run_reference_chain_production,
)
from .capability_expansion import build_capability_gap, build_capability_specification
from .capability_registry import promote_verified_capability
from .capability_resolver import resolve_or_discover_capability
from .weaver_2021_full_text_capability_verifier import (
    verify_weaver_2021_full_text_capability_candidate,
)
from .weaver_2021_full_text_policy import authenticate_weaver_2021_full_text_policy

AUTONOMOUS_PRODUCTION_SCHEMA_VERSION = "1.9"
AUTONOMOUS_PRODUCTION_POLICY_VERSION = "1.9"
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
    "mds2_2923_experiment_identity_reference_chain_assessment",
    weaver_capability.ACTION_CLASS,
)


class AutonomousProductionWeaverExtensionError(ValueError):
    """Raised when Weaver production extension violates predecessor or source authority."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionWeaverExtensionError(message)


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
        raise AutonomousProductionWeaverExtensionError(
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


def _validate_execution_against_verification(
    *,
    evidence: Mapping[str, Any],
    verification: Mapping[str, Any],
) -> tuple[str, str]:
    """Fail closed if execution bytes drift from independently verified Weaver bytes."""
    evidence_sha = _validate_self_hash(evidence, "report_sha256_without_self_field")
    source = evidence.get("source")
    _require(isinstance(source, Mapping), "Weaver execution source binding is missing")
    source_sha = source.get("source_sha256")
    _require(
        isinstance(source_sha, str) and len(source_sha) == 64,
        "Weaver execution source SHA-256 is missing",
    )
    smoke = verification.get("real_source_smoke_receipt")
    _require(
        isinstance(smoke, Mapping),
        "Weaver verification smoke receipt is missing",
    )
    _validate_self_hash(smoke, "report_sha256_without_self_field")
    _require(
        evidence.get("core_claims_matched") is True
        and smoke.get("core_claims_matched") is True
        and smoke.get("evidence_self_hash_recomputed") is True,
        "Weaver execution core claims were not independently verified",
    )
    _require(
        smoke.get("network_requests_performed") == 2
        and smoke.get("execution_evidence_reuse_authorized") is False,
        "Weaver verifier/execution independence contract drifted",
    )
    _require(
        smoke.get("weaver_evidence_sha256") == evidence_sha
        and smoke.get("weaver_source_sha256") == source_sha,
        "Weaver execution evidence drifted after independent verification",
    )
    return evidence_sha, source_sha


def _resolved_output(root: Path, output_root: str | Path) -> Path:
    output = Path(output_root).expanduser()
    if not output.is_absolute():
        output = root / output
    output = output.resolve(strict=True)
    try:
        output.relative_to(root)
    except ValueError as exc:
        raise AutonomousProductionWeaverExtensionError(
            "autonomous production output escaped repository root"
        ) from exc
    return output


def _stop(reason_code: str, action_class: str, **extra: Any) -> dict[str, Any]:
    return {
        "status": "stopped",
        "reason_code": reason_code,
        "requested_action_class": action_class,
        "scope": "verified_registry_and_mission_pinned_weaver_authority",
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


def _reauthenticate_candidate(
    *,
    resolution: Mapping[str, Any],
    candidate: Mapping[str, Any],
    specification: Mapping[str, Any],
    predecessor_manifest_sha256: str,
) -> dict[str, Any]:
    spec_sha = _validate_self_hash(
        specification,
        "capability_specification_sha256_without_self_field",
    )
    candidate_sha = _validate_self_hash(
        candidate,
        "capability_candidate_sha256_without_self_field",
    )
    resolution_candidate = resolution.get("candidate")
    _require(
        resolution.get("resolution_status") == "bounded_candidate_discovered"
        and isinstance(resolution_candidate, Mapping)
        and dict(resolution_candidate) == dict(candidate),
        "predecessor Weaver resolution/candidate binding drifted",
    )
    _require(
        candidate.get("state") == "candidate"
        and candidate.get("action_class") == weaver_capability.ACTION_CLASS
        and candidate.get("implementation_id") == weaver_capability.IMPLEMENTATION_ID
        and candidate.get("factory_id") == weaver_capability.FACTORY_ID
        and candidate.get("mechanism") == weaver_capability.MECHANISM
        and candidate.get("capability_specification_sha256") == spec_sha,
        "predecessor Weaver capability identity drifted",
    )
    _require(
        candidate.get("network_authority_granted") is False
        and candidate.get("execution_authority_granted") is False
        and candidate.get("scientific_status_change_authorized") is False
        and candidate.get("self_promotion_requested") is False,
        "predecessor Weaver candidate attempted authority before verification",
    )
    receipt: dict[str, Any] = {
        "schema_version": "1.0",
        "artifact_type": "predecessor_capability_candidate_reauthentication",
        "resolution_status": "predecessor_candidate_reauthenticated",
        "action_class": weaver_capability.ACTION_CLASS,
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


def run_autonomous_production(
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    output_root: str | Path,
    max_cycles: int = 14,
) -> dict[str, Any]:
    """Verify/promote the fifth capability, acquire Weaver full text, and re-diagnose."""
    if (
        isinstance(max_cycles, bool)
        or not isinstance(max_cycles, int)
        or max_cycles < 1
        or max_cycles > 14
    ):
        raise AutonomousProductionWeaverExtensionError(
            "max_cycles must be an integer from 1 to 14"
        )
    root = Path(repository_root).expanduser().resolve(strict=True)
    mission = Path(mission_path).expanduser().resolve(strict=True)
    try:
        mission.relative_to(root)
    except ValueError as exc:
        raise AutonomousProductionWeaverExtensionError(
            "mission_path must remain inside repository_root"
        ) from exc
    _require(
        hashlib.sha256(mission.read_bytes()).hexdigest() == expected_mission_sha256,
        "mission bytes do not match independently pinned mission SHA-256",
    )
    if max_cycles <= 12:
        return run_reference_chain_production(
            repository_root=root,
            mission_path=mission,
            expected_mission_sha256=expected_mission_sha256,
            output_root=output_root,
            max_cycles=max_cycles,
        )

    run_reference_chain_production(
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=expected_mission_sha256,
        output_root=output_root,
        max_cycles=12,
    )
    output = _resolved_output(root, output_root)
    predecessor = _read_json(
        output / "autonomous-production-manifest.json",
        "reference-chain predecessor manifest",
    )
    predecessor_sha = _validate_self_hash(predecessor, "manifest_sha256")
    _require(
        predecessor.get("generated_next_action_class") == weaver_capability.ACTION_CLASS
        and predecessor.get("fifth_capability_gap_emitted") is True
        and predecessor.get("fifth_capability_candidate_discovered") is True
        and predecessor.get("fifth_capability_candidate_promoted") is False
        and predecessor.get("fourth_research_action_resumed") is True,
        "predecessor did not stop at exact Weaver candidate frontier",
    )
    _require(
        predecessor.get("bridge_established") is False
        and predecessor.get("directly_comparable_mds2_rows") == 0
        and predecessor.get("issue_76_exact_target_cells_satisfied") == 0,
        "predecessor scientific boundary drifted",
    )
    raw_cycles = predecessor.get("cycles")
    _require(isinstance(raw_cycles, list) and len(raw_cycles) == 12, "predecessor cycles drifted")
    cycles = [dict(item) for item in raw_cycles if isinstance(item, Mapping)]
    _require(len(cycles) == 12, "predecessor cycle entries are invalid")

    registry = _read_json(
        output / "capability-registry-promoted-4.json",
        "fourth promoted capability registry",
    )
    fifth_gap = _read_json(output / "capability-gap-5.json", "fifth capability gap")
    fifth_spec = _read_json(
        output / "capability-specification-5.json", "fifth capability specification"
    )
    fifth_resolution = _read_json(
        output / "capability-resolution-5.json", "fifth capability resolution"
    )
    fifth_candidate = _read_json(
        output / "capability-candidate-5.json", "fifth capability candidate"
    )
    reference_graph = _read_json(
        output / "mds2-2923-experiment-identity-reference-chain.json",
        "mds2 reference graph",
    )
    _validate_self_hash(fifth_gap, "capability_gap_sha256_without_self_field")
    _validate_self_hash(fifth_spec, "capability_specification_sha256_without_self_field")
    graph_sha = _validate_self_hash(reference_graph, "report_sha256_without_self_field")
    _require(
        fifth_gap.get("requested_action_class") == weaver_capability.ACTION_CLASS
        and fifth_spec.get("requested_action_class") == weaver_capability.ACTION_CLASS
        and predecessor.get("reference_chain_assessment_sha256") == graph_sha,
        "fifth capability predecessor bindings drifted",
    )
    candidate_reauthentication = _reauthenticate_candidate(
        resolution=fifth_resolution,
        candidate=fifth_candidate,
        specification=fifth_spec,
        predecessor_manifest_sha256=predecessor_sha,
    )
    _write_json(
        output / "capability-resolution-5-derived.json",
        candidate_reauthentication,
    )

    cycle13: dict[str, Any] = {
        "cycle_index": 13,
        "predecessor_cycle_sha256": cycles[-1]["cycle_sha256"],
        "input_blocker": "weaver_primary_full_text_acquisition_candidate_unverified",
        "selected_action_class": weaver_capability.ACTION_CLASS,
        "capability_available": False,
        "resolution_status": candidate_reauthentication["resolution_status"],
        "bounded_candidate_discovered": False,
        "predecessor_candidate_reauthenticated": True,
        "candidate_rediscovery_performed": False,
        "capability_candidate_sha256": fifth_candidate[
            "capability_candidate_sha256_without_self_field"
        ],
        "predecessor_manifest_sha256": predecessor_sha,
        "caller_authored_url_used": False,
        "caller_authored_pmcid_used": False,
        "arbitrary_code_generation_performed": False,
        "global_evidence_unavailability_claimed": False,
        "new_verified_information": False,
        "scientific_status_changed": False,
    }
    cycle13["cycle_sha256"] = _canonical_sha(cycle13)
    cycles.append(cycle13)
    if max_cycles == 13:
        return _finalize(
            output=output,
            predecessor_manifest=predecessor,
            cycles=cycles,
            stop=_stop(
                "maximum_cycles_reached",
                weaver_capability.ACTION_CLASS,
                capability_expansion_ready=True,
            ),
            updates={
                "fifth_capability_candidate_discovered": True,
                "fifth_capability_candidate_promoted": False,
                "fifth_research_action_resumed": False,
                "fifth_candidate_reauthenticated_from_predecessor": True,
                "fifth_candidate_rediscovery_performed": False,
                "generated_next_action_class": weaver_capability.ACTION_CLASS,
            },
        )

    verification = verify_weaver_2021_full_text_capability_candidate(
        capability_specification=fifth_spec,
        candidate=fifth_candidate,
        available_verified_primitives=_VERIFIED_PRIMITIVES,
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=expected_mission_sha256,
        verification_context={
            "reference_graph": reference_graph,
            "predecessor_manifest": predecessor,
        },
        perform_real_source_smoke=True,
    )
    _write_json(output / "capability-verification-5.json", verification)
    _require(
        verification.get("promotion_eligible") is True,
        "Weaver full-text capability failed independent verification",
    )
    promoted_registry = promote_verified_capability(
        registry=registry,
        candidate=fifth_candidate,
        verification_receipt=verification,
    )
    _write_json(output / "capability-registry-promoted-5.json", promoted_registry)
    resolved = resolve_or_discover_capability(
        registry=promoted_registry,
        capability_specification=fifth_spec,
        available_verified_primitives=_VERIFIED_PRIMITIVES,
    )
    _write_json(output / "capability-post-promotion-resolution-5.json", resolved)
    _require(
        resolved.get("resolution_status") == "verified_capability_resolved"
        and resolved.get("implementation_id") == weaver_capability.IMPLEMENTATION_ID,
        "promoted Weaver capability did not resolve exact blocked action",
    )

    qualification = authenticate_weaver_2021_full_text_policy(
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=expected_mission_sha256,
    )
    _write_json(output / "weaver-full-text-policy-qualification.json", qualification)
    authorization = weaver_acquisition.build_derived_weaver_authorization(
        qualification=qualification,
        reference_graph=reference_graph,
        predecessor_manifest=predecessor,
    )
    _write_json(output / "weaver-derived-full-text-authorization.json", authorization)
    evidence = weaver_acquisition.execute_derived_weaver_acquisition(
        authorization=authorization
    )
    evidence_sha, evidence_source_sha = _validate_execution_against_verification(
        evidence=evidence,
        verification=verification,
    )
    _write_json(output / "weaver-2021-full-text-acquisition.json", evidence)
    gate = evidence.get("gate_assessment")
    scope = evidence.get("evidence_scope")
    _require(
        isinstance(gate, Mapping)
        and isinstance(scope, Mapping)
        and scope.get("weaver_full_text_acquired") is True
        and scope.get("weaver_article_identity_established") is True
        and evidence.get("core_claims_matched") is True
        and gate.get("exact_mds2_experiment_identity_established") is False
        and gate.get("machine_setting_to_calibrated_power_relation_established") is False
        and gate.get("directly_comparable_mds2_rows") == 0
        and gate.get("direct_numerical_cross_source_validation_authorized") is False
        and gate.get("issue_76_exact_target_cells_satisfied") == 0,
        "Weaver acquisition improperly promoted scientific equivalence",
    )
    next_action = evidence.get("next_action")
    _require(
        isinstance(next_action, Mapping)
        and next_action.get("action_class") == weaver_acquisition.NEXT_ACTION_CLASS,
        "Weaver next action drifted",
    )

    cycle14: dict[str, Any] = {
        "cycle_index": 14,
        "predecessor_cycle_sha256": cycle13["cycle_sha256"],
        "input_blocker": "missing_source_adapter",
        "selected_action_class": weaver_capability.ACTION_CLASS,
        "capability_available": True,
        "capability_verification_sha256": verification[
            "capability_verification_sha256_without_self_field"
        ],
        "promoted_registry_sha256": promoted_registry[
            "capability_registry_sha256_without_self_field"
        ],
        "implementation_id": weaver_capability.IMPLEMENTATION_ID,
        "research_action_resumed": True,
        "execution_network_requests_performed": evidence["network_requests_performed"],
        "verifier_smoke_network_requests_performed": verification[
            "real_source_smoke_receipt"
        ]["network_requests_performed"],
        "weaver_evidence_sha256": evidence_sha,
        "weaver_source_sha256": evidence_source_sha,
        "weaver_article_identity_established": True,
        "weaver_core_claims_matched": True,
        "execution_matches_verified_source_bytes": True,
        "exact_mds2_experiment_identity_established": False,
        "bridge_established": False,
        "directly_comparable_mds2_rows": 0,
        "issue_76_exact_target_cells_satisfied": 0,
        "output_next_action_class": next_action["action_class"],
        "new_verified_information": True,
        "scientific_status_changed": False,
    }
    cycle14["cycle_sha256"] = _canonical_sha(cycle14)
    cycles.append(cycle14)

    sixth_gap = build_capability_gap(
        requested_action=next_action,
        predecessor_report=evidence,
        available_action_classes=_AVAILABLE_ACTION_CLASSES,
    )
    sixth_spec = build_capability_specification(sixth_gap)
    sixth_resolution = resolve_or_discover_capability(
        registry=promoted_registry,
        capability_specification=sixth_spec,
        available_verified_primitives=_VERIFIED_PRIMITIVES,
    )
    _write_json(output / "capability-gap-6.json", sixth_gap)
    _write_json(output / "capability-specification-6.json", sixth_spec)
    _write_json(output / "capability-resolution-6.json", sixth_resolution)
    _require(
        sixth_resolution.get("resolution_status") == "no_bounded_candidate_available",
        "row-identity assessment unexpectedly gained unaudited capability",
    )
    stop = _stop(
        "capability_expansion_required",
        str(next_action["action_class"]),
        capability_gap_class=sixth_gap["gap_class"],
        bounded_candidate_discovered=False,
        caller_authored_url_used=False,
        arbitrary_code_generation_performed=False,
    )
    return _finalize(
        output=output,
        predecessor_manifest=predecessor,
        cycles=cycles,
        stop=stop,
        updates={
            "fifth_capability_candidate_discovered": True,
            "fifth_capability_candidate_promoted": True,
            "fifth_research_action_resumed": True,
            "fifth_candidate_reauthenticated_from_predecessor": True,
            "fifth_candidate_rediscovery_performed": False,
            "weaver_policy_sha256": qualification["policy_sha256"],
            "weaver_authorization_sha256": authorization["authorization_sha256"],
            "weaver_full_text_acquisition_sha256": evidence_sha,
            "weaver_source_sha256": evidence_source_sha,
            "weaver_full_text_acquired": True,
            "weaver_article_identity_established": True,
            "weaver_core_claims_matched": True,
            "weaver_execution_matches_verified_source_bytes": True,
            "exact_mds2_experiment_identity_established": False,
            "exact_machine_setting_to_calibrated_power_relation_established": False,
            "bridge_established": False,
            "directly_comparable_mds2_rows": 0,
            "direct_numerical_cross_source_validation_authorized": False,
            "issue_76_exact_target_cells_satisfied": 0,
            "sixth_capability_gap_emitted": True,
            "generated_next_action_class": next_action["action_class"],
            "final_blocker": "mds2_weaver_row_identity_binding_capability_not_established",
        },
    )


__all__ = [
    "AUTONOMOUS_PRODUCTION_POLICY_VERSION",
    "AUTONOMOUS_PRODUCTION_SCHEMA_VERSION",
    "AutonomousProductionWeaverExtensionError",
    "run_autonomous_production",
]
