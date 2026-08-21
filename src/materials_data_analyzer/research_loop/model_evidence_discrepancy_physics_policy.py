"""Physics-semantic public policy for model/evidence discrepancy comparison.

This layer sits above the provenance-hardening policy.  It binds the selected heat-solver
response to its physical unit and space/time coordinates, cross-checks persistent
hypothesis state against the evaluated graph, and preserves verified negative graph
status even when the optional portfolio is omitted.

No unit conversion, interpolation, empirical authority decision, or epistemic status
promotion is performed here.  Unsupported semantics become non-comparable or fail
closed rather than being guessed.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .kernel import ResearchLoopError
from .model_evidence_discrepancy_policy import (
    MODEL_EVIDENCE_DISCREPANCY_HARDENING_POLICY_VERSION,
    ModelEvidenceDiscrepancyPolicyError,
    _comparison_input_from_report,
    _priority_sort,
    _repository_root_from_request,
    build_policy_hardened_model_evidence_discrepancy_report,
)

MODEL_EVIDENCE_DISCREPANCY_PHYSICS_POLICY_VERSION = "1.0"
COORDINATE_VERIFICATION_SCHEMA_VERSION = "1.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_STATUS_TO_PORTFOLIO = {
    "inconclusive": (
        "active_discrimination_required",
        "continue_discriminating_research",
    ),
    "provisionally_supported": (
        "positive_closeout_required",
        "seek_domain_closeout_no_auto_promotion",
    ),
    "contested": (
        "contested_discrimination_required",
        "prioritize_discriminating_work",
    ),
    "contradicted_within_verified_scope": (
        "challenge_or_retirement_review",
        "seek_replication_or_scope_review",
    ),
    "falsified_within_verified_scope": (
        "retired_falsified_within_verified_scope",
        "do_not_repeat_without_new_hypothesis_identity",
    ),
}
_STRONG_DIAGNOSES = {
    "empirical_model_discrepancy",
    "agreement_within_declared_tolerance",
}
_STRONG_ONLY_PROPOSALS = {
    "model-evidence:bounded-domain-closeout-review",
    "model-evidence:discriminate-model-vs-hypothesis",
    "model-evidence:independent-matched-replication",
}


class ModelEvidenceDiscrepancyPhysicsPolicyError(ResearchLoopError):
    """Raised when physical comparison semantics cannot be verified."""


def _canonical_sha256(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(
            "physics-policy state must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(f"{field} must be an object")
    return value


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(f"{field} must be a sequence")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(
            f"{field} must be non-empty trimmed text"
        )
    return value


def _sha(value: object, field: str) -> str:
    text = _text(value, field)
    if _SHA256.fullmatch(text) is None:
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(
            f"{field} must be lowercase SHA-256"
        )
    return text


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(f"{field} must be finite")
    result = float(value)
    if not math.isfinite(result):
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(f"{field} must be finite")
    return result


def _read_json(path: Path, field: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(
            f"could not read {field} JSON"
        ) from exc
    if not isinstance(value, dict):
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(f"{field} root must be an object")
    return value


def _bound_file(
    value: object,
    *,
    artifact_root: Path,
    field: str,
) -> dict[str, Any]:
    item = _mapping(value, field)
    if set(item) != {"path", "sha256"}:
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(f"{field} field set drifted")
    path = Path(_text(item.get("path"), f"{field}.path")).expanduser()
    if not path.is_absolute():
        path = artifact_root / path
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(
            f"{field} does not resolve"
        ) from exc
    try:
        resolved.relative_to(artifact_root)
    except ValueError as exc:
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(
            f"{field} escapes artifact_root"
        ) from exc
    if not resolved.is_file():
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(f"{field} must be a file")
    data = resolved.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != _sha(item.get("sha256"), f"{field}.sha256"):
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(f"{field} checksum drifted")
    return {"path": str(resolved), "sha256": actual, "bytes": len(data)}


def _require_kelvin_contract(comparison_spec: Mapping[str, Any]) -> None:
    model = _mapping(comparison_spec.get("model_response"), "comparison_spec.model_response")
    empirical = _mapping(
        comparison_spec.get("empirical_response"),
        "comparison_spec.empirical_response",
    )
    tolerance = _mapping(comparison_spec.get("tolerance"), "comparison_spec.tolerance")
    if model.get("selector") != "final_temperature_K":
        return
    if (
        model.get("unit") != "K"
        or empirical.get("unit") != "K"
        or tolerance.get("unit") != "K"
    ):
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(
            "final_temperature_K comparison requires model, empirical, and tolerance units exactly K; v1 performs no implicit conversion"
        )


def _coordinate_verification(
    path: str | Path,
    *,
    artifact_root: Path,
    report: Mapping[str, Any],
) -> dict[str, Any]:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = artifact_root / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(
            "coordinate_verification_path does not resolve"
        ) from exc
    try:
        resolved.relative_to(artifact_root)
    except ValueError as exc:
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(
            "coordinate_verification_path escapes artifact_root"
        ) from exc
    raw = resolved.read_bytes()
    manifest = _read_json(resolved, "coordinate_verification")
    required = {
        "schema_version",
        "evidence_id",
        "target_node_id",
        "position_m",
        "time_s",
        "verification_artifact",
    }
    if set(manifest) != required:
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(
            "coordinate verification field set drifted"
        )
    if manifest.get("schema_version") != COORDINATE_VERIFICATION_SCHEMA_VERSION:
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(
            "unsupported coordinate verification schema_version"
        )
    evidence = _mapping(report.get("empirical_evidence"), "report.empirical_evidence")
    target = _mapping(report.get("target"), "report.target")
    if manifest.get("evidence_id") != evidence.get("evidence_id"):
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(
            "coordinate verification evidence_id drifted"
        )
    if manifest.get("target_node_id") != target.get("node_id"):
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(
            "coordinate verification target drifted"
        )
    verification_artifact = _bound_file(
        manifest.get("verification_artifact"),
        artifact_root=artifact_root,
        field="coordinate_verification.verification_artifact",
    )
    bindings = _mapping(report.get("input_bindings"), "report.input_bindings")
    solver_binding = _mapping(bindings.get("solver_result"), "report.input_bindings.solver_result")
    solver_result = _read_json(
        Path(_text(solver_binding.get("path"), "report.input_bindings.solver_result.path")),
        "solver_result",
    )
    comparison = _mapping(report.get("comparison_contract"), "report.comparison_contract")
    model_response = _mapping(comparison.get("model_response"), "report.comparison_contract.model_response")
    index = model_response.get("index")
    if isinstance(index, bool) or not isinstance(index, int):
        raise ModelEvidenceDiscrepancyPhysicsPolicyError("model response index is malformed")
    grid = solver_result.get("spatial_grid_m")
    time = _mapping(solver_result.get("time"), "solver_result.time")
    if not isinstance(grid, list) or index < 0 or index >= len(grid):
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(
            "solver result does not contain the selected spatial coordinate"
        )
    expected_position = _finite(grid[index], f"solver_result.spatial_grid_m[{index}]")
    expected_time = _finite(time.get("duration_s"), "solver_result.time.duration_s")
    declared_position = _finite(manifest.get("position_m"), "coordinate_verification.position_m")
    declared_time = _finite(manifest.get("time_s"), "coordinate_verification.time_s")
    position_match = math.isclose(
        declared_position,
        expected_position,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    )
    time_match = math.isclose(
        declared_time,
        expected_time,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    )
    return {
        "manifest_binding": {
            "path": str(resolved),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
        },
        "position_m": declared_position,
        "expected_position_m": expected_position,
        "position_matches_selected_model_response": position_match,
        "time_s": declared_time,
        "expected_time_s": expected_time,
        "time_matches_selected_model_response": time_match,
        "verification_artifact": verification_artifact,
        "coordinate_semantics_independently_adjudicated_by_policy": False,
        "passed": position_match and time_match,
    }


def _downgrade_coordinate_comparability(report: dict[str, Any], *, reason: str) -> None:
    gates = dict(_mapping(report.get("gates"), "report.gates"))
    comparability = dict(_mapping(gates.get("comparability"), "report.gates.comparability"))
    comparability["passed"] = False
    reasons = list(comparability.get("reasons", []))
    if reason not in reasons:
        reasons.append(reason)
    comparability["reasons"] = reasons
    comparability["coordinate_provenance_verified"] = False
    gates["comparability"] = comparability
    report["gates"] = gates

    quantitative = dict(_mapping(report.get("quantitative_comparison"), "report.quantitative_comparison"))
    quantitative["performed"] = False
    quantitative["model_value"] = None
    quantitative["empirical_value"] = None
    quantitative["absolute_error"] = None
    report["quantitative_comparison"] = quantitative

    diagnoses = [
        dict(_mapping(item, "report.diagnosis"))
        for item in _sequence(report.get("diagnoses", []), "report.diagnoses")
        if isinstance(item, Mapping) and item.get("diagnosis_type") not in _STRONG_DIAGNOSES
    ]
    if not any(
        item.get("diagnosis_type") == "provenance_or_protocol_incompatibility"
        for item in diagnoses
    ):
        diagnoses.append(
            {
                "diagnosis_id": "model-evidence:provenance_or_protocol_incompatibility",
                "diagnosis_type": "provenance_or_protocol_incompatibility",
                "severity": "high",
                "statement": (
                    "The empirical response is not bound to the selected solver space/time coordinate."
                ),
                "evidence_basis": [reason],
                "blocks_empirical_falsification": True,
                "epistemic_edge_created": False,
            }
        )
    report["diagnoses"] = diagnoses
    proposals = [
        dict(_mapping(item, "report.ranked_next_action"))
        for item in _sequence(report.get("ranked_next_actions", []), "report.ranked_next_actions")
        if isinstance(item, Mapping) and item.get("proposal_id") not in _STRONG_ONLY_PROPOSALS
    ]
    if not any(
        item.get("proposal_id") == "model-evidence:bind-empirical-space-time"
        for item in proposals
    ):
        proposals.append(
            {
                "proposal_id": "model-evidence:bind-empirical-space-time",
                "action_class": "protocol_semantic_reconciliation",
                "description": (
                    "Bind the empirical response to the exact spatial position and final time "
                    "selected from the audited solver result."
                ),
                "rationale": reason,
                "information_gain_priority": "highest",
                "information_gain_is_calibrated_probability": False,
                "execution_mode": "plan_only",
                "availability_asserted": False,
                "automatic_execution_authorized": False,
            }
        )
    report["ranked_next_actions"] = _priority_sort(proposals)
    ancestry = dict(_mapping(report.get("ancestry"), "report.ancestry"))
    ancestry["current_diagnosis_types"] = sorted(
        {str(item.get("diagnosis_type")) for item in diagnoses}
    )
    report["ancestry"] = ancestry
    report["stop_recommendation"] = {
        "recommendation": "replan_to_resolve_upstream_comparison_gates",
        "rationale": reason,
        "automatic_stop_authorized": False,
        "positive_scientific_closeout_granted": False,
    }


def _validate_portfolio_against_graph(report: Mapping[str, Any]) -> None:
    portfolio = report.get("hypothesis_portfolio_state")
    if portfolio is None:
        return
    target = _mapping(report.get("target"), "report.target")
    assessment = _mapping(report.get("epistemic_assessment"), "report.epistemic_assessment")
    status = _text(target.get("epistemic_status"), "report.target.epistemic_status")
    if assessment.get("status") != status:
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(
            "target epistemic status differs from evaluated assessment"
        )
    expected = _STATUS_TO_PORTFOLIO.get(status)
    if expected is None:
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(
            "unsupported graph status for hypothesis portfolio comparison"
        )
    item = _mapping(portfolio, "report.hypothesis_portfolio_state")
    if item.get("epistemic_status") != status:
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(
            "portfolio epistemic_status differs from evaluated graph"
        )
    if item.get("portfolio_state") != expected[0]:
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(
            "portfolio_state differs from the state implied by the evaluated graph"
        )
    if item.get("research_directive") != expected[1]:
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(
            "portfolio research_directive differs from the evaluated graph"
        )
    for field in (
        "verified_support_edges",
        "verified_contradiction_edges",
        "verified_falsification_edges",
    ):
        if list(item.get(field, [])) != list(assessment.get(field, [])):
            raise ModelEvidenceDiscrepancyPhysicsPolicyError(
                f"portfolio {field} differs from evaluated graph assessment"
            )


def _preserve_negative_graph_status(report: dict[str, Any]) -> None:
    target = _mapping(report.get("target"), "report.target")
    status = target.get("epistemic_status")
    if status not in {
        "falsified_within_verified_scope",
        "contradicted_within_verified_scope",
    }:
        return
    proposals = [
        dict(_mapping(item, "report.ranked_next_action"))
        for item in _sequence(report.get("ranked_next_actions", []), "report.ranked_next_actions")
    ]
    if status == "falsified_within_verified_scope":
        proposal_id = "model-evidence:preserve-falsified-status"
        action_class = "hypothesis_reframe"
        description = (
            "Preserve the verified falsification and create a new hypothesis identity before any rescue attempt."
        )
        rationale = "Verified graph falsification cannot be weakened by model agreement or portfolio omission."
        recommendation = "preserve_falsification_and_reframe"
    else:
        proposal_id = "model-evidence:preserve-contradiction-review"
        action_class = "hypothesis_review"
        description = (
            "Preserve the verified contradiction and complete challenge/scope review before positive continuation."
        )
        rationale = "Verified graph contradiction cannot be weakened by model agreement or portfolio omission."
        recommendation = "preserve_contradiction_and_review_scope"
    if not any(item.get("proposal_id") == proposal_id for item in proposals):
        proposals.append(
            {
                "proposal_id": proposal_id,
                "action_class": action_class,
                "description": description,
                "rationale": rationale,
                "information_gain_priority": "highest",
                "information_gain_is_calibrated_probability": False,
                "execution_mode": "plan_only",
                "availability_asserted": False,
                "automatic_execution_authorized": False,
            }
        )
    report["ranked_next_actions"] = _priority_sort(proposals)
    report["stop_recommendation"] = {
        "recommendation": recommendation,
        "rationale": rationale,
        "automatic_stop_authorized": False,
        "positive_scientific_closeout_granted": False,
    }


def build_physics_hardened_model_evidence_discrepancy_report(
    *,
    model_adapter_id: str,
    action_report_path: str | Path,
    execution_request_path: str | Path,
    empirical_evidence_path: str | Path,
    comparison_spec: Mapping[str, Any],
    evaluated_graph: Mapping[str, Any],
    target_node_id: str,
    artifact_root: str | Path,
    hypothesis_portfolio: Mapping[str, Any] | None = None,
    previous_report: Mapping[str, Any] | None = None,
    replication_verification_path: str | Path | None = None,
    coordinate_verification_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build the strongest public v1 model/evidence comparison contract."""
    _require_kelvin_contract(comparison_spec)
    root = Path(artifact_root).expanduser().resolve(strict=True)
    report = build_policy_hardened_model_evidence_discrepancy_report(
        model_adapter_id=model_adapter_id,
        action_report_path=action_report_path,
        execution_request_path=execution_request_path,
        empirical_evidence_path=empirical_evidence_path,
        comparison_spec=comparison_spec,
        evaluated_graph=evaluated_graph,
        target_node_id=target_node_id,
        artifact_root=root,
        hypothesis_portfolio=hypothesis_portfolio,
        previous_report=previous_report,
        replication_verification_path=replication_verification_path,
    )
    _validate_portfolio_against_graph(report)
    coordinate = None
    coordinate_verified = False
    reason = "empirical space/time coordinate verification is absent"
    if coordinate_verification_path is not None:
        coordinate = _coordinate_verification(
            coordinate_verification_path,
            artifact_root=root,
            report=report,
        )
        coordinate_verified = coordinate["passed"] is True
        reason = (
            "empirical response position/time matches selected audited solver response"
            if coordinate_verified
            else "empirical response position/time does not match selected audited solver response"
        )
    gates = dict(_mapping(report.get("gates"), "report.gates"))
    comparability = dict(_mapping(gates.get("comparability"), "report.gates.comparability"))
    comparability["coordinate_provenance_verified"] = coordinate_verified
    comparability["coordinate_provenance_reason"] = reason
    gates["comparability"] = comparability
    report["gates"] = gates
    if not coordinate_verified:
        _downgrade_coordinate_comparability(report, reason=reason)
    _preserve_negative_graph_status(report)
    report["ranked_next_actions"] = _priority_sort(
        _sequence(report.get("ranked_next_actions", []), "report.ranked_next_actions")
    )
    report["physics_comparison_hardening"] = {
        "policy_version": MODEL_EVIDENCE_DISCREPANCY_PHYSICS_POLICY_VERSION,
        "final_temperature_selector_requires_kelvin": True,
        "coordinate_verification": coordinate,
        "empirical_coordinates_must_match_solver_grid_and_final_time": True,
        "portfolio_state_must_match_evaluated_graph": True,
        "negative_graph_status_preserved_without_optional_portfolio": True,
        "coordinate_semantics_independently_adjudicated_by_policy": False,
    }
    report.pop("report_sha256", None)
    report["report_sha256"] = _canonical_sha256(report)
    return report


def validate_physics_hardened_model_evidence_discrepancy_report(
    report: Mapping[str, Any],
    *,
    evaluated_graph: Mapping[str, Any],
    hypothesis_portfolio: Mapping[str, Any] | None = None,
    previous_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Deterministically rebuild the full physics-hardened public report."""
    value = dict(_mapping(report, "discrepancy_report"))
    embedded = _sha(value.pop("report_sha256", None), "discrepancy_report.report_sha256")
    if _canonical_sha256(value) != embedded:
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(
            "discrepancy report canonical SHA-256 does not match its content"
        )
    value["report_sha256"] = embedded
    physics = _mapping(
        value.get("physics_comparison_hardening"),
        "discrepancy_report.physics_comparison_hardening",
    )
    if physics.get("policy_version") != MODEL_EVIDENCE_DISCREPANCY_PHYSICS_POLICY_VERSION:
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(
            "unsupported physics comparison hardening policy_version"
        )
    provenance = _mapping(
        value.get("provenance_hardening"),
        "discrepancy_report.provenance_hardening",
    )
    if provenance.get("policy_version") != MODEL_EVIDENCE_DISCREPANCY_HARDENING_POLICY_VERSION:
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(
            "unsupported provenance hardening policy_version"
        )
    bindings = _mapping(value.get("input_bindings"), "discrepancy_report.input_bindings")
    request = _mapping(bindings.get("execution_request"), "input_bindings.execution_request")
    action = _mapping(bindings.get("model_action_report"), "input_bindings.model_action_report")
    evidence = _mapping(bindings.get("empirical_evidence"), "input_bindings.empirical_evidence")
    root = _repository_root_from_request(
        _text(request.get("path"), "input_bindings.execution_request.path")
    )
    replication_path = None
    replication = provenance.get("replication_verification")
    if replication is not None:
        replication_map = _mapping(replication, "provenance_hardening.replication_verification")
        manifest = _mapping(
            replication_map.get("manifest_binding"),
            "provenance_hardening.replication_verification.manifest_binding",
        )
        replication_path = _text(manifest.get("path"), "replication manifest path")
    coordinate_path = None
    coordinate = physics.get("coordinate_verification")
    if coordinate is not None:
        coordinate_map = _mapping(coordinate, "physics_comparison_hardening.coordinate_verification")
        manifest = _mapping(
            coordinate_map.get("manifest_binding"),
            "physics_comparison_hardening.coordinate_verification.manifest_binding",
        )
        coordinate_path = _text(manifest.get("path"), "coordinate manifest path")
    target = _mapping(value.get("target"), "discrepancy_report.target")
    rebuilt = build_physics_hardened_model_evidence_discrepancy_report(
        model_adapter_id=_text(bindings.get("model_adapter_id"), "input_bindings.model_adapter_id"),
        action_report_path=_text(action.get("path"), "input_bindings.model_action_report.path"),
        execution_request_path=_text(request.get("path"), "input_bindings.execution_request.path"),
        empirical_evidence_path=_text(evidence.get("path"), "input_bindings.empirical_evidence.path"),
        comparison_spec=_comparison_input_from_report(value),
        evaluated_graph=evaluated_graph,
        target_node_id=_text(target.get("node_id"), "discrepancy_report.target.node_id"),
        artifact_root=root,
        hypothesis_portfolio=hypothesis_portfolio,
        previous_report=previous_report,
        replication_verification_path=replication_path,
        coordinate_verification_path=coordinate_path,
    )
    if rebuilt != value:
        raise ModelEvidenceDiscrepancyPhysicsPolicyError(
            "discrepancy report differs from deterministic reconstruction of physics-bound inputs"
        )
    diagnoses = [
        str(item.get("diagnosis_type"))
        for item in _sequence(value.get("diagnoses", []), "discrepancy_report.diagnoses")
        if isinstance(item, Mapping)
    ]
    return {
        "report_sha256": embedded,
        "target_node_id": target.get("node_id"),
        "iteration_index": value.get("iteration_index"),
        "diagnosis_types": diagnoses,
        "artifact_bindings_reverified": True,
        "complete_report_deterministic_rebuild_verified": True,
        "replication_provenance_verified": bool(
            value.get("gates", {}).get("empirical_sufficiency", {}).get(
                "replication_provenance_verified"
            )
        ),
        "coordinate_provenance_verified": bool(
            value.get("gates", {}).get("comparability", {}).get(
                "coordinate_provenance_verified"
            )
        ),
        "scientific_status_changed": False,
        "automatic_execution_authorized": False,
    }


build_model_evidence_discrepancy_report = (
    build_physics_hardened_model_evidence_discrepancy_report
)
validate_model_evidence_discrepancy_report = (
    validate_physics_hardened_model_evidence_discrepancy_report
)


__all__ = [
    "COORDINATE_VERIFICATION_SCHEMA_VERSION",
    "MODEL_EVIDENCE_DISCREPANCY_PHYSICS_POLICY_VERSION",
    "ModelEvidenceDiscrepancyPhysicsPolicyError",
    "build_model_evidence_discrepancy_report",
    "build_physics_hardened_model_evidence_discrepancy_report",
    "validate_model_evidence_discrepancy_report",
    "validate_physics_hardened_model_evidence_discrepancy_report",
]
