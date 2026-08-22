"""Public recursive discrepancy reports that never fabricate missing empirical evidence.

The existing physics/provenance discrepancy critic remains authoritative when an empirical
artifact exists.  This module adds one deliberately narrower public mode for the recursive
architecture acceptance path: an audited reference-heat execution may be diagnosed before
empirical evidence exists.  Missing empirical evidence is represented as missing evidence,
never as a synthetic observation.

No function in this module creates execution authority, an epistemic edge, or scientific
truth.  Every heat result is independently recomputed and rebound to the immutable research
ledger through ``verify_heat_conduction_action_report_pinned``.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .heat_conduction_action import verify_heat_conduction_action_report_pinned
from .kernel import ResearchLoopError
from .model_evidence_discrepancy_physics_policy import (
    build_physics_hardened_model_evidence_discrepancy_report,
    validate_physics_hardened_model_evidence_discrepancy_report,
)

PUBLIC_RECURSIVE_DISCREPANCY_SCHEMA_VERSION = "1.0"
PUBLIC_RECURSIVE_DISCREPANCY_POLICY_VERSION = "1.0"
_NO_EMPIRICAL_MODE = "no_empirical_artifact"
_SUPPORTED_ADAPTER = "reference-heat-conduction"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TARGET_TYPES = {"hypothesis", "claim", "conclusion"}


class PublicRecursiveDiscrepancyError(ResearchLoopError):
    """Raised when recursive discrepancy evidence/provenance cannot be reconstructed."""


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
        raise PublicRecursiveDiscrepancyError(
            "public recursive discrepancy state must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PublicRecursiveDiscrepancyError(f"{field} must be an object")
    return value


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise PublicRecursiveDiscrepancyError(f"{field} must be a sequence")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise PublicRecursiveDiscrepancyError(f"{field} must be non-empty trimmed text")
    return value


def _sha(value: object, field: str) -> str:
    text = _text(value, field)
    if _SHA256.fullmatch(text) is None:
        raise PublicRecursiveDiscrepancyError(f"{field} must be lowercase SHA-256")
    return text


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in pairs:
        if key in result:
            raise PublicRecursiveDiscrepancyError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = item
    return result


def _json_snapshot(path: str | Path, *, field: str) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        resolved = Path(path).expanduser().resolve(strict=True)
    except OSError as exc:
        raise PublicRecursiveDiscrepancyError(f"{field} does not resolve") from exc
    if not resolved.is_file():
        raise PublicRecursiveDiscrepancyError(f"{field} must be a file")
    raw = resolved.read_bytes()
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublicRecursiveDiscrepancyError(f"{field} must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise PublicRecursiveDiscrepancyError(f"{field} root must be an object")
    return value, {
        "path": str(resolved),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _file_record(path: str | Path, *, field: str) -> dict[str, Any]:
    try:
        resolved = Path(path).expanduser().resolve(strict=True)
    except OSError as exc:
        raise PublicRecursiveDiscrepancyError(f"{field} does not resolve") from exc
    if not resolved.is_file():
        raise PublicRecursiveDiscrepancyError(f"{field} must be a file")
    raw = resolved.read_bytes()
    return {
        "path": str(resolved),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _record_matches(
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
    *,
    field: str,
) -> None:
    if (
        expected.get("path") != actual.get("path")
        or expected.get("sha256") != actual.get("sha256")
        or expected.get("bytes") != actual.get("bytes")
    ):
        raise PublicRecursiveDiscrepancyError(
            f"{field} current bytes differ from discrepancy binding"
        )


def _graph_target(
    evaluated_graph: Mapping[str, Any],
    *,
    target_node_id: str,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    graph = dict(_mapping(evaluated_graph, "evaluated_graph"))
    graph_id = _text(graph.get("graph_id"), "evaluated_graph.graph_id")
    nodes = _sequence(graph.get("nodes"), "evaluated_graph.nodes")
    node_matches = [
        _mapping(item, "evaluated_graph.node")
        for item in nodes
        if isinstance(item, Mapping) and item.get("node_id") == target_node_id
    ]
    if len(node_matches) != 1:
        raise PublicRecursiveDiscrepancyError(
            "target_node_id must identify exactly one graph node"
        )
    node = node_matches[0]
    if node.get("node_type") not in _TARGET_TYPES:
        raise PublicRecursiveDiscrepancyError(
            "recursive discrepancy target must be hypothesis, claim, or conclusion"
        )
    assessments = _sequence(
        graph.get("assessments"),
        "evaluated_graph.assessments",
    )
    assessment_matches = [
        dict(_mapping(item, "evaluated_graph.assessment"))
        for item in assessments
        if isinstance(item, Mapping) and item.get("node_id") == target_node_id
    ]
    if len(assessment_matches) != 1:
        raise PublicRecursiveDiscrepancyError(
            "target requires exactly one evaluated assessment"
        )
    assessment = assessment_matches[0]
    if assessment.get("confidence_score") is not None:
        raise PublicRecursiveDiscrepancyError(
            "recursive discrepancy does not accept invented numeric confidence"
        )
    if assessment.get("final_positive_support_granted") is not False:
        raise PublicRecursiveDiscrepancyError(
            "recursive discrepancy cannot consume automatic final-positive support"
        )
    target = {
        "graph_id": graph_id,
        "node_id": target_node_id,
        "node_type": _text(node.get("node_type"), "target.node_type"),
        "statement": _text(node.get("statement"), "target.statement"),
        "epistemic_status": assessment.get("status"),
    }
    return target, assessment, _canonical_sha256(graph)


def _verified_embedded_report_sha(
    report: Mapping[str, Any],
    *,
    field: str,
) -> str:
    value = dict(_mapping(report, field))
    embedded = _sha(value.pop("report_sha256", None), f"{field}.report_sha256")
    if _canonical_sha256(value) != embedded:
        raise PublicRecursiveDiscrepancyError(
            f"{field}.report_sha256 does not match canonical content"
        )
    return embedded


def _previous_ancestry(
    previous_report: Mapping[str, Any] | None,
    *,
    current_target: Mapping[str, Any],
) -> tuple[int, str | None, list[str]]:
    if previous_report is None:
        return 1, None, []
    previous = _mapping(previous_report, "previous_discrepancy_report")
    previous_sha = _verified_embedded_report_sha(
        previous,
        field="previous_discrepancy_report",
    )
    target = _mapping(previous.get("target"), "previous_discrepancy_report.target")
    for field in ("node_id", "node_type", "statement"):
        if target.get(field) != current_target.get(field):
            raise PublicRecursiveDiscrepancyError(
                f"previous discrepancy target identity changed: {field}"
            )
    iteration = previous.get("iteration_index")
    if isinstance(iteration, bool) or not isinstance(iteration, int) or iteration < 1:
        raise PublicRecursiveDiscrepancyError(
            "previous discrepancy iteration_index is malformed"
        )
    diagnoses = _sequence(
        previous.get("diagnoses", []),
        "previous_discrepancy_report.diagnoses",
    )
    prior_types = sorted(
        {
            str(item.get("diagnosis_type"))
            for item in diagnoses
            if isinstance(item, Mapping)
            and isinstance(item.get("diagnosis_type"), str)
        }
    )
    return iteration + 1, previous_sha, prior_types


def _verify_heat_model(
    *,
    action_report_path: str | Path,
    execution_request_path: str | Path,
) -> dict[str, Any]:
    request, request_record = _json_snapshot(
        execution_request_path,
        field="execution_request",
    )
    report, report_record = _json_snapshot(
        action_report_path,
        field="heat_action_report",
    )
    try:
        verified = verify_heat_conduction_action_report_pinned(
            action_report_path,
            request_value=request,
            request_path=execution_request_path,
            request_record=request_record,
        )
    except ResearchLoopError as exc:
        raise PublicRecursiveDiscrepancyError(
            "audited heat action failed pinned deterministic verification"
        ) from exc
    if verified.get("report_sha256") != report_record["sha256"]:
        raise PublicRecursiveDiscrepancyError(
            "pinned heat verifier report SHA differs from current report bytes"
        )
    if (
        verified.get("deterministic_recomputation_verified") is not True
        or verified.get("ledger_artifact_binding_verified") is not True
        or verified.get("physics_solver") is not True
        or verified.get("empirical_validation_performed") is not False
        or verified.get("scientific_status_upgrade_authorized") is not False
    ):
        raise PublicRecursiveDiscrepancyError(
            "pinned heat verifier did not preserve the required computational-only boundary"
        )
    solver = _mapping(report.get("solver_result"), "heat_action_report.solver_result")
    solver_record = _file_record(
        _text(solver.get("path"), "heat_action_report.solver_result.path"),
        field="solver_result",
    )
    if verified.get("solver_result_sha256") != solver_record["sha256"]:
        raise PublicRecursiveDiscrepancyError(
            "pinned heat verifier solver SHA differs from current solver bytes"
        )
    return {
        "request": request,
        "request_record": request_record,
        "report_record": report_record,
        "solver_record": solver_record,
        "verification": dict(verified),
    }


def _proposal(
    suffix: str,
    *,
    action_class: str,
    description: str,
    rationale: str,
    priority: str,
    execution_mode: str,
) -> dict[str, Any]:
    return {
        "proposal_id": f"public-recursive:{suffix}",
        "action_class": action_class,
        "description": description,
        "rationale": rationale,
        "information_gain_priority": priority,
        "information_gain_is_calibrated_probability": False,
        "execution_mode": execution_mode,
        "availability_asserted": False,
        "automatic_execution_authorized": False,
    }


def _build_no_empirical_report(
    *,
    model_adapter_id: str,
    action_report_path: str | Path,
    execution_request_path: str | Path,
    evaluated_graph: Mapping[str, Any],
    target_node_id: str,
    previous_report: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if model_adapter_id != _SUPPORTED_ADAPTER:
        raise PublicRecursiveDiscrepancyError(
            "no-empirical recursive mode supports only the audited reference heat adapter"
        )
    target, assessment, graph_sha = _graph_target(
        evaluated_graph,
        target_node_id=_text(target_node_id, "target_node_id"),
    )
    model = _verify_heat_model(
        action_report_path=action_report_path,
        execution_request_path=execution_request_path,
    )
    iteration_index, previous_sha, prior_types = _previous_ancestry(
        previous_report,
        current_target=target,
    )
    verification = model["verification"]
    numerical_valid = (
        verification.get("registered_outcome")
        == "numerically_validated_reference_solution"
        and verification.get("validation_state") == "passed"
        and verification.get("run_status") == "completed"
    )

    if numerical_valid:
        diagnoses = [
            {
                "diagnosis_id": "public-recursive:empirical-evidence-not-acquired",
                "diagnosis_type": "empirical_evidence_not_acquired",
                "severity": "high",
                "statement": (
                    "The audited numerical reference is admissible, but no empirical "
                    "artifact exists for a physical model/evidence comparison."
                ),
                "evidence_basis": [
                    "numerical_validity=passed",
                    "empirical_evidence_artifact=absent",
                ],
                "blocks_empirical_falsification": True,
                "epistemic_edge_created": False,
            }
        ]
        proposals = [
            _proposal(
                "acquire-independent-empirical-evidence",
                action_class="external_evidence_search",
                description=(
                    "Acquire a provenance-bound independent empirical artifact under a "
                    "declared comparison protocol before attempting physical interpretation."
                ),
                rationale=(
                    "A numerically valid reference calculation is not empirical evidence."
                ),
                priority="highest",
                execution_mode="explicit_authorization_required",
            )
        ]
        stop_recommendation = {
            "recommendation": "await_real_empirical_evidence_or_authorized_acquisition",
            "rationale": (
                "No empirical observation exists; manufacturing one would violate the "
                "scientific evidence boundary."
            ),
            "automatic_stop_authorized": False,
            "positive_scientific_closeout_granted": False,
        }
    else:
        diagnoses = [
            {
                "diagnosis_id": "public-recursive:numerical-invalidity",
                "diagnosis_type": "numerical_invalidity",
                "severity": "high",
                "statement": (
                    "The audited reference heat execution is not numerically admissible "
                    "for physical interpretation."
                ),
                "evidence_basis": [
                    f"registered_outcome={verification.get('registered_outcome')}",
                    f"validation_state={verification.get('validation_state')}",
                    f"run_status={verification.get('run_status')}",
                ],
                "blocks_empirical_falsification": True,
                "epistemic_edge_created": False,
            }
        ]
        proposals = [
            _proposal(
                "validate-or-refine-numerics",
                action_class="numerical_validation",
                description=(
                    "Run a separately authorized, checksum-bound numerical validation "
                    "before any empirical interpretation."
                ),
                rationale=(
                    "The pinned solver result failed its declared numerical validation gate."
                ),
                priority="highest",
                execution_mode="plan_only",
            )
        ]
        stop_recommendation = {
            "recommendation": "replan_before_physical_interpretation",
            "rationale": (
                "Numerical validity is a prerequisite for any physical comparison."
            ),
            "automatic_stop_authorized": False,
            "positive_scientific_closeout_granted": False,
        }

    diagnosis_types = [item["diagnosis_type"] for item in diagnoses]
    gates = {
        "numerical_validity": {
            "passed": numerical_valid,
            "registered_outcome": verification.get("registered_outcome"),
            "validation_state": verification.get("validation_state"),
            "deterministic_recomputation_verified": verification.get(
                "deterministic_recomputation_verified"
            ),
            "ledger_artifact_binding_verified": verification.get(
                "ledger_artifact_binding_verified"
            ),
        },
        "empirical_evidence_acquired": {
            "passed": False,
            "artifact_binding": None,
            "synthetic_substitution_allowed": False,
        },
    }

    result: dict[str, Any] = {
        "schema_version": PUBLIC_RECURSIVE_DISCREPANCY_SCHEMA_VERSION,
        "policy_version": PUBLIC_RECURSIVE_DISCREPANCY_POLICY_VERSION,
        "public_recursive_discrepancy_mode": _NO_EMPIRICAL_MODE,
        "critic_id": (
            f"public-recursive:{target['graph_id']}:{target['node_id']}:"
            f"{model['report_record']['sha256'][:12]}"
        ),
        "iteration_index": iteration_index,
        "target": target,
        "epistemic_assessment": dict(assessment),
        "empirical_evidence": None,
        "empirical_evidence_status": {
            "status": "not_acquired",
            "artifact_binding": None,
            "synthetic_measurement_created": False,
            "synthetic_measurement_accepted": False,
        },
        "input_bindings": {
            "model_adapter_id": model_adapter_id,
            "model_action_report": dict(model["report_record"]),
            "execution_request": dict(model["request_record"]),
            "solver_result": dict(model["solver_record"]),
            "evaluated_graph": {"canonical_sha256": graph_sha},
            "previous_discrepancy_report": (
                {"report_sha256": previous_sha} if previous_sha is not None else None
            ),
            "empirical_evidence": None,
        },
        "gates": gates,
        "quantitative_comparison": {
            "performed": False,
            "reason": (
                "numerical_validity_failed"
                if not numerical_valid
                else "empirical_evidence_not_acquired"
            ),
            "model_value": None,
            "empirical_value": None,
            "absolute_error": None,
        },
        "diagnoses": diagnoses,
        "alternative_explanations": [],
        "ranked_next_actions": proposals,
        "stop_recommendation": stop_recommendation,
        "ancestry": {
            "previous_report_sha256": previous_sha,
            "prior_diagnosis_types": prior_types,
            "current_diagnosis_types": sorted(set(diagnosis_types)),
        },
        "provenance_hardening": {
            "heat_action_pinned_recomputation_verified": True,
            "immutable_research_ledger_binding_verified": True,
            "solver_result_sha256": model["solver_record"]["sha256"],
            "empirical_artifact_required_before_empirical_comparison": True,
            "missing_empirical_evidence_is_represented_as_an_explicit_evidence_gap": True,
        },
        "physics_comparison_hardening": {
            "numerical_validity_precedes_physical_interpretation": True,
            "empirical_comparison_performed": False,
            "empirical_coordinate_semantics_claimed": False,
            "material_or_process_validity_claimed": False,
        },
        "autonomy_boundary": {
            "diagnostic_orchestration_only": True,
            "scientific_status_changed": False,
            "epistemic_edge_created": False,
            "confidence_probability_estimated": False,
            "automatic_execution_authorized": False,
            "physical_experiment_executed": False,
            "network_access_performed": False,
            "synthetic_empirical_measurement_created": False,
            "model_agreement_confirms_hypothesis": False,
        },
    }
    for rank, proposal in enumerate(result["ranked_next_actions"], start=1):
        proposal["rank"] = rank
    result["report_sha256"] = _canonical_sha256(result)
    return result


def build_public_recursive_discrepancy_report(
    *,
    model_adapter_id: str,
    action_report_path: str | Path,
    execution_request_path: str | Path,
    evaluated_graph: Mapping[str, Any],
    target_node_id: str,
    empirical_evidence_path: str | Path | None = None,
    comparison_spec: Mapping[str, Any] | None = None,
    artifact_root: str | Path | None = None,
    hypothesis_portfolio: Mapping[str, Any] | None = None,
    previous_report: Mapping[str, Any] | None = None,
    replication_verification_path: str | Path | None = None,
    coordinate_verification_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build the strongest public discrepancy available without inventing evidence.

    If ``empirical_evidence_path`` exists, the pre-existing physics/provenance-hardened
    critic is used unchanged.  If it is absent, only the narrow audited-reference mode
    above is permitted.
    """
    if empirical_evidence_path is not None:
        if comparison_spec is None or artifact_root is None:
            raise PublicRecursiveDiscrepancyError(
                "empirical discrepancy mode requires comparison_spec and artifact_root"
            )
        return build_physics_hardened_model_evidence_discrepancy_report(
            model_adapter_id=model_adapter_id,
            action_report_path=action_report_path,
            execution_request_path=execution_request_path,
            empirical_evidence_path=empirical_evidence_path,
            comparison_spec=comparison_spec,
            evaluated_graph=evaluated_graph,
            target_node_id=target_node_id,
            artifact_root=artifact_root,
            hypothesis_portfolio=hypothesis_portfolio,
            previous_report=previous_report,
            replication_verification_path=replication_verification_path,
            coordinate_verification_path=coordinate_verification_path,
        )
    if comparison_spec is not None:
        raise PublicRecursiveDiscrepancyError(
            "comparison_spec cannot substitute for an absent empirical artifact"
        )
    if replication_verification_path is not None or coordinate_verification_path is not None:
        raise PublicRecursiveDiscrepancyError(
            "empirical replication/coordinate verification cannot be supplied without empirical evidence"
        )
    if hypothesis_portfolio is not None:
        raise PublicRecursiveDiscrepancyError(
            "no-empirical recursive mode binds target state directly to the evaluated graph"
        )
    return _build_no_empirical_report(
        model_adapter_id=model_adapter_id,
        action_report_path=action_report_path,
        execution_request_path=execution_request_path,
        evaluated_graph=evaluated_graph,
        target_node_id=target_node_id,
        previous_report=previous_report,
    )


def validate_public_recursive_discrepancy_report(
    report: Mapping[str, Any],
    *,
    evaluated_graph: Mapping[str, Any],
    hypothesis_portfolio: Mapping[str, Any] | None = None,
    previous_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Deterministically reconstruct either legacy empirical or no-empirical report."""
    value = dict(_mapping(report, "discrepancy_report"))
    if value.get("public_recursive_discrepancy_mode") != _NO_EMPIRICAL_MODE:
        try:
            return validate_physics_hardened_model_evidence_discrepancy_report(
                report,
                evaluated_graph=evaluated_graph,
                hypothesis_portfolio=hypothesis_portfolio,
                previous_report=previous_report,
            )
        except ResearchLoopError as exc:
            raise PublicRecursiveDiscrepancyError(
                "empirical discrepancy report failed the existing physics/provenance policy"
            ) from exc

    if hypothesis_portfolio is not None:
        raise PublicRecursiveDiscrepancyError(
            "unbound hypothesis portfolio cannot be injected into no-empirical validation"
        )
    if value.get("schema_version") != PUBLIC_RECURSIVE_DISCREPANCY_SCHEMA_VERSION:
        raise PublicRecursiveDiscrepancyError(
            "unsupported public recursive discrepancy schema_version"
        )
    if value.get("policy_version") != PUBLIC_RECURSIVE_DISCREPANCY_POLICY_VERSION:
        raise PublicRecursiveDiscrepancyError(
            "unsupported public recursive discrepancy policy_version"
        )
    embedded = _verified_embedded_report_sha(
        value,
        field="discrepancy_report",
    )
    bindings = _mapping(value.get("input_bindings"), "discrepancy_report.input_bindings")
    action = _mapping(
        bindings.get("model_action_report"),
        "input_bindings.model_action_report",
    )
    request = _mapping(
        bindings.get("execution_request"),
        "input_bindings.execution_request",
    )
    target = _mapping(value.get("target"), "discrepancy_report.target")
    rebuilt = _build_no_empirical_report(
        model_adapter_id=_text(
            bindings.get("model_adapter_id"),
            "input_bindings.model_adapter_id",
        ),
        action_report_path=_text(
            action.get("path"),
            "input_bindings.model_action_report.path",
        ),
        execution_request_path=_text(
            request.get("path"),
            "input_bindings.execution_request.path",
        ),
        evaluated_graph=evaluated_graph,
        target_node_id=_text(target.get("node_id"), "discrepancy_report.target.node_id"),
        previous_report=previous_report,
    )
    if rebuilt != value:
        raise PublicRecursiveDiscrepancyError(
            "public recursive discrepancy differs from deterministic reconstruction"
        )
    diagnosis_types = [
        str(item.get("diagnosis_type"))
        for item in _sequence(value.get("diagnoses", []), "discrepancy_report.diagnoses")
        if isinstance(item, Mapping)
    ]
    return {
        "report_sha256": embedded,
        "target_node_id": target.get("node_id"),
        "iteration_index": value.get("iteration_index"),
        "diagnosis_types": diagnosis_types,
        "artifact_bindings_reverified": True,
        "heat_pinned_recomputation_verified": True,
        "empirical_evidence_acquired": False,
        "synthetic_empirical_measurement_accepted": False,
        "scientific_status_changed": False,
        "automatic_execution_authorized": False,
    }


build_model_evidence_discrepancy_report = build_public_recursive_discrepancy_report
validate_model_evidence_discrepancy_report = validate_public_recursive_discrepancy_report


__all__ = [
    "PUBLIC_RECURSIVE_DISCREPANCY_POLICY_VERSION",
    "PUBLIC_RECURSIVE_DISCREPANCY_SCHEMA_VERSION",
    "PublicRecursiveDiscrepancyError",
    "build_model_evidence_discrepancy_report",
    "build_public_recursive_discrepancy_report",
    "validate_model_evidence_discrepancy_report",
    "validate_public_recursive_discrepancy_report",
]
