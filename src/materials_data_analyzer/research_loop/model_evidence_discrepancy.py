"""Provenance-aware model-evidence discrepancy diagnostics.

This module does not decide scientific truth. It verifies one audited physics-model
execution, binds empirical evidence and comparison semantics, classifies why a
model/evidence comparison is or is not scientifically interpretable, and emits bounded
next-action proposals. It never creates epistemic support/contradiction/falsification
edges, never estimates confidence probabilities, and never authorizes execution.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .heat_conduction_action import verify_heat_conduction_action_report_pinned
from .kernel import ResearchLoopError

MODEL_EVIDENCE_DISCREPANCY_SCHEMA_VERSION = "1.0"
MODEL_EVIDENCE_DISCREPANCY_POLICY_VERSION = "1.0"
_SUPPORTED_MODEL_ADAPTER = "reference-heat-conduction"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TARGET_TYPES = {"hypothesis", "claim", "conclusion"}
_DIAGNOSIS_TYPES = {
    "numerical_invalidity",
    "model_domain_mismatch",
    "parameter_or_property_uncertainty",
    "provenance_or_protocol_incompatibility",
    "insufficient_empirical_evidence",
    "empirical_model_discrepancy",
    "agreement_within_declared_tolerance",
}
_CONTEXT_FIELDS = (
    "protocol_id",
    "material_state_id",
    "sample_identity",
    "conditions_id",
)


class ModelEvidenceDiscrepancyError(ResearchLoopError):
    """Raised when a model/evidence comparison cannot preserve provenance."""


def _canonical_sha256(value: object) -> str:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ModelEvidenceDiscrepancyError(
            "discrepancy state must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(payload).hexdigest()


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ModelEvidenceDiscrepancyError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _read_json_snapshot(path: Path, *, field: str) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved = path.expanduser().resolve(strict=True)
    if not resolved.is_file():
        raise ModelEvidenceDiscrepancyError(f"{field} must be a regular file")
    data = resolved.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ModelEvidenceDiscrepancyError(f"{field} must be UTF-8 JSON") from exc
    try:
        value = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise ModelEvidenceDiscrepancyError(f"invalid {field} JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ModelEvidenceDiscrepancyError(f"{field} root must be an object")
    return value, {
        "path": str(resolved),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def _file_record(path: Path, *, field: str) -> dict[str, Any]:
    resolved = path.expanduser().resolve(strict=True)
    if not resolved.is_file():
        raise ModelEvidenceDiscrepancyError(f"{field} must be a regular file")
    data = resolved.read_bytes()
    return {
        "path": str(resolved),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ModelEvidenceDiscrepancyError(f"{field} must be an object")
    return value


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ModelEvidenceDiscrepancyError(f"{field} must be a sequence")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ModelEvidenceDiscrepancyError(f"{field} must be non-empty trimmed text")
    return value


def _sha(value: object, field: str) -> str:
    text = _text(value, field)
    if _SHA256.fullmatch(text) is None:
        raise ModelEvidenceDiscrepancyError(f"{field} must be lowercase SHA-256")
    return text


def _finite(value: object, field: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelEvidenceDiscrepancyError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ModelEvidenceDiscrepancyError(f"{field} must be finite")
    if nonnegative and result < 0.0:
        raise ModelEvidenceDiscrepancyError(f"{field} must be nonnegative")
    return result


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ModelEvidenceDiscrepancyError(f"{field} must be an integer >= 1")
    return value


def _exact_keys(value: Mapping[str, Any], *, field: str, keys: set[str]) -> None:
    missing = sorted(keys - set(value))
    extra = sorted(set(value) - keys)
    if missing:
        raise ModelEvidenceDiscrepancyError(
            f"{field} is missing required keys: {', '.join(missing)}"
        )
    if extra:
        raise ModelEvidenceDiscrepancyError(
            f"{field} has unknown keys: {', '.join(extra)}"
        )


def _within(path: Path, root: Path, *, field: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ModelEvidenceDiscrepancyError(f"{field} escapes artifact_root") from exc


def _verify_binding(
    value: object,
    *,
    artifact_root: Path,
    field: str,
) -> dict[str, Any]:
    binding = _mapping(value, field)
    _exact_keys(binding, field=field, keys={"path", "sha256"})
    raw_path = _text(binding.get("path"), f"{field}.path")
    expected_sha = _sha(binding.get("sha256"), f"{field}.sha256")
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = artifact_root / path
    resolved = path.resolve(strict=True)
    _within(resolved, artifact_root, field=field)
    record = _file_record(resolved, field=field)
    if record["sha256"] != expected_sha:
        raise ModelEvidenceDiscrepancyError(
            f"{field} bytes differ from declared SHA-256"
        )
    return record


def _normalize_basis_bindings(
    value: object,
    *,
    artifact_root: Path,
    field: str,
) -> list[dict[str, Any]]:
    items = _sequence(value, field)
    records = [
        _verify_binding(item, artifact_root=artifact_root, field=f"{field}[{index}]")
        for index, item in enumerate(items)
    ]
    paths = [str(item["path"]) for item in records]
    if len(paths) != len(set(paths)):
        raise ModelEvidenceDiscrepancyError(f"{field} contains duplicate artifact paths")
    return records


def _graph_target(
    evaluated_graph: Mapping[str, Any],
    *,
    target_node_id: str,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    graph = dict(_mapping(evaluated_graph, "evaluated_graph"))
    graph_id = _text(graph.get("graph_id"), "evaluated_graph.graph_id")
    nodes = _sequence(graph.get("nodes"), "evaluated_graph.nodes")
    matches: list[Mapping[str, Any]] = []
    for index, raw in enumerate(nodes):
        node = _mapping(raw, f"evaluated_graph.nodes[{index}]")
        if node.get("node_id") == target_node_id:
            matches.append(node)
    if len(matches) != 1:
        raise ModelEvidenceDiscrepancyError(
            "target_node_id must identify exactly one epistemic-graph node"
        )
    node = matches[0]
    if node.get("node_type") not in _TARGET_TYPES:
        raise ModelEvidenceDiscrepancyError(
            "discrepancy target must be a hypothesis, claim, or conclusion"
        )
    statement = _text(node.get("statement"), "target.statement")
    assessments = _sequence(graph.get("assessments"), "evaluated_graph.assessments")
    assessment_matches = [
        _mapping(item, "evaluated_graph.assessment")
        for item in assessments
        if isinstance(item, Mapping) and item.get("node_id") == target_node_id
    ]
    if len(assessment_matches) != 1:
        raise ModelEvidenceDiscrepancyError(
            "target requires exactly one evaluated epistemic assessment"
        )
    assessment = dict(assessment_matches[0])
    if assessment.get("node_type") != node.get("node_type"):
        raise ModelEvidenceDiscrepancyError("target assessment node_type drifted")
    if assessment.get("final_positive_support_granted") is not False:
        raise ModelEvidenceDiscrepancyError(
            "discrepancy critic cannot consume automatically final-positive support"
        )
    if assessment.get("confidence_score") is not None:
        raise ModelEvidenceDiscrepancyError(
            "discrepancy critic does not accept numeric confidence scores"
        )
    return (
        {
            "graph_id": graph_id,
            "node_id": target_node_id,
            "node_type": node.get("node_type"),
            "statement": statement,
            "epistemic_status": assessment.get("status"),
        },
        assessment,
        _canonical_sha256(graph),
    )


def _verified_report_sha(report: Mapping[str, Any], *, field: str) -> str:
    value = dict(_mapping(report, field))
    embedded = _sha(value.pop("report_sha256", None), f"{field}.report_sha256")
    actual = _canonical_sha256(value)
    if actual != embedded:
        raise ModelEvidenceDiscrepancyError(
            f"{field} canonical SHA-256 does not match its content"
        )
    return embedded


def _portfolio_target(
    portfolio: Mapping[str, Any] | None,
    *,
    graph_sha256: str,
    target: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    if portfolio is None:
        return None, None
    value = dict(_mapping(portfolio, "hypothesis_portfolio"))
    embedded = _sha(
        value.pop("portfolio_sha256", None),
        "hypothesis_portfolio.portfolio_sha256",
    )
    actual = _canonical_sha256(value)
    if actual != embedded:
        raise ModelEvidenceDiscrepancyError(
            "hypothesis portfolio canonical SHA-256 does not match its content"
        )
    graph_binding = _mapping(
        value.get("evaluated_graph_binding"),
        "hypothesis_portfolio.evaluated_graph_binding",
    )
    if _sha(
        graph_binding.get("canonical_sha256"),
        "hypothesis_portfolio.evaluated_graph_binding.canonical_sha256",
    ) != graph_sha256:
        raise ModelEvidenceDiscrepancyError(
            "hypothesis portfolio is not bound to the current evaluated graph"
        )
    records = _sequence(value.get("hypotheses"), "hypothesis_portfolio.hypotheses")
    target_records = [
        _mapping(item, "hypothesis_portfolio.hypothesis")
        for item in records
        if isinstance(item, Mapping) and item.get("hypothesis_id") == target["node_id"]
    ]
    if target["node_type"] != "hypothesis":
        raise ModelEvidenceDiscrepancyError(
            "a hypothesis portfolio may be supplied only for a hypothesis target"
        )
    if len(target_records) != 1:
        raise ModelEvidenceDiscrepancyError(
            "hypothesis portfolio does not contain the exact target hypothesis"
        )
    record = dict(target_records[0])
    if record.get("statement") != target["statement"]:
        raise ModelEvidenceDiscrepancyError(
            "hypothesis statement differs between graph and portfolio"
        )
    return {
        "hypothesis_id": target["node_id"],
        "portfolio_state": record.get("portfolio_state"),
        "epistemic_status": record.get("epistemic_status"),
        "research_directive": record.get("research_directive"),
        "verified_support_edges": list(record.get("verified_support_edges", [])),
        "verified_contradiction_edges": list(
            record.get("verified_contradiction_edges", [])
        ),
        "verified_falsification_edges": list(
            record.get("verified_falsification_edges", [])
        ),
    }, embedded


def _verify_heat_model(
    *,
    action_report_path: str | Path,
    execution_request_path: str | Path,
) -> dict[str, Any]:
    request_path = Path(execution_request_path).expanduser().resolve(strict=True)
    request_value, request_record = _read_json_snapshot(
        request_path,
        field="execution_request",
    )
    report_path = Path(action_report_path).expanduser().resolve(strict=True)
    verified = verify_heat_conduction_action_report_pinned(
        report_path,
        request_value=request_value,
        request_path=request_path,
        request_record=request_record,
    )
    report_value, report_record = _read_json_snapshot(
        report_path,
        field="model_action_report",
    )
    if verified.get("report_sha256") != report_record["sha256"]:
        raise ModelEvidenceDiscrepancyError(
            "model verifier report checksum does not match current action report"
        )
    solver_result = _mapping(
        report_value.get("solver_result"),
        "model_action_report.solver_result",
    )
    result_path = Path(
        _text(solver_result.get("path"), "model_action_report.solver_result.path")
    ).expanduser().resolve(strict=True)
    result_value, result_record = _read_json_snapshot(
        result_path,
        field="solver_result",
    )
    if verified.get("solver_result_sha256") != result_record["sha256"]:
        raise ModelEvidenceDiscrepancyError(
            "model verifier result checksum does not match current solver result"
        )
    return {
        "adapter_id": _SUPPORTED_MODEL_ADAPTER,
        "action_report": report_record,
        "execution_request": request_record,
        "solver_result": result_record,
        "verification": dict(verified),
        "result": result_value,
    }


def _normalize_empirical_evidence(
    path: str | Path,
    *,
    artifact_root: Path,
    target_node_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved = Path(path).expanduser()
    if not resolved.is_absolute():
        resolved = artifact_root / resolved
    resolved = resolved.resolve(strict=True)
    _within(resolved, artifact_root, field="empirical_evidence_path")
    value, record = _read_json_snapshot(resolved, field="empirical_evidence")
    _exact_keys(
        value,
        field="empirical_evidence",
        keys={
            "schema_version",
            "evidence_id",
            "target_node_id",
            "response",
            "independent_replicates",
            "replication_independence_verified",
            "provenance",
        },
    )
    if value.get("schema_version") != "1.0":
        raise ModelEvidenceDiscrepancyError(
            "unsupported empirical evidence schema_version"
        )
    if value.get("target_node_id") != target_node_id:
        raise ModelEvidenceDiscrepancyError(
            "empirical evidence target_node_id differs from discrepancy target"
        )
    evidence_id = _text(value.get("evidence_id"), "empirical_evidence.evidence_id")
    response = _mapping(value.get("response"), "empirical_evidence.response")
    _exact_keys(
        response,
        field="empirical_evidence.response",
        keys={"name", "value", "unit"},
    )
    provenance = _mapping(value.get("provenance"), "empirical_evidence.provenance")
    _exact_keys(
        provenance,
        field="empirical_evidence.provenance",
        keys={
            "assessment_level",
            "source_identity",
            "protocol_id",
            "material_state_id",
            "sample_identity",
            "conditions_id",
        },
    )
    assessment_level = _text(
        provenance.get("assessment_level"),
        "empirical_evidence.provenance.assessment_level",
    )
    if assessment_level not in {"domain_verified", "diagnostic_only", "unverified"}:
        raise ModelEvidenceDiscrepancyError(
            "unsupported empirical provenance assessment_level"
        )
    normalized_provenance = {
        "assessment_level": assessment_level,
        "source_identity": _text(
            provenance.get("source_identity"),
            "empirical_evidence.provenance.source_identity",
        ),
    }
    for field in _CONTEXT_FIELDS:
        normalized_provenance[field] = _text(
            provenance.get(field),
            f"empirical_evidence.provenance.{field}",
        )
    return {
        "schema_version": "1.0",
        "evidence_id": evidence_id,
        "target_node_id": target_node_id,
        "response": {
            "name": _text(response.get("name"), "empirical_evidence.response.name"),
            "value": _finite(
                response.get("value"),
                "empirical_evidence.response.value",
            ),
            "unit": _text(response.get("unit"), "empirical_evidence.response.unit"),
        },
        "independent_replicates": _positive_int(
            value.get("independent_replicates"),
            "empirical_evidence.independent_replicates",
        ),
        "replication_independence_verified": (
            value.get("replication_independence_verified") is True
        ),
        "provenance": normalized_provenance,
    }, record


def _normalize_comparison_spec(
    value: Mapping[str, Any],
    *,
    artifact_root: Path,
    target_node_id: str,
) -> dict[str, Any]:
    spec = _mapping(value, "comparison_spec")
    _exact_keys(
        spec,
        field="comparison_spec",
        keys={
            "schema_version",
            "target_node_id",
            "model_response",
            "empirical_response",
            "tolerance",
            "model_domain",
            "property_assessment",
            "empirical_sufficiency",
            "required_context",
        },
    )
    if spec.get("schema_version") != "1.0":
        raise ModelEvidenceDiscrepancyError(
            "unsupported comparison_spec schema_version"
        )
    if spec.get("target_node_id") != target_node_id:
        raise ModelEvidenceDiscrepancyError(
            "comparison_spec target_node_id differs from discrepancy target"
        )

    model_response = _mapping(spec.get("model_response"), "comparison_spec.model_response")
    _exact_keys(
        model_response,
        field="comparison_spec.model_response",
        keys={"selector", "index", "response_name", "unit"},
    )
    selector = _text(
        model_response.get("selector"),
        "comparison_spec.model_response.selector",
    )
    if selector != "final_temperature_K":
        raise ModelEvidenceDiscrepancyError(
            "v1 supports only final_temperature_K model response selection"
        )
    index = model_response.get("index")
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise ModelEvidenceDiscrepancyError(
            "comparison_spec.model_response.index must be a nonnegative integer"
        )

    empirical_response = _mapping(
        spec.get("empirical_response"),
        "comparison_spec.empirical_response",
    )
    _exact_keys(
        empirical_response,
        field="comparison_spec.empirical_response",
        keys={"response_name", "unit"},
    )

    tolerance = _mapping(spec.get("tolerance"), "comparison_spec.tolerance")
    _exact_keys(
        tolerance,
        field="comparison_spec.tolerance",
        keys={"metric", "value", "unit", "semantics"},
    )
    if tolerance.get("metric") != "absolute_error":
        raise ModelEvidenceDiscrepancyError(
            "v1 supports only absolute_error comparison metric"
        )

    model_domain = _mapping(spec.get("model_domain"), "comparison_spec.model_domain")
    _exact_keys(
        model_domain,
        field="comparison_spec.model_domain",
        keys={"status", "authority", "basis", "bindings"},
    )
    domain_status = _text(
        model_domain.get("status"),
        "comparison_spec.model_domain.status",
    )
    if domain_status not in {
        "within_declared_scope",
        "outside_declared_scope",
        "not_established",
    }:
        raise ModelEvidenceDiscrepancyError(
            "unsupported comparison_spec.model_domain.status"
        )
    domain_authority = _text(
        model_domain.get("authority"),
        "comparison_spec.model_domain.authority",
    )
    if domain_authority not in {"domain_verified", "diagnostic_only", "unverified"}:
        raise ModelEvidenceDiscrepancyError(
            "unsupported comparison_spec.model_domain.authority"
        )
    domain_bindings = _normalize_basis_bindings(
        model_domain.get("bindings"),
        artifact_root=artifact_root,
        field="comparison_spec.model_domain.bindings",
    )
    if domain_authority == "domain_verified" and not domain_bindings:
        raise ModelEvidenceDiscrepancyError(
            "domain_verified model-domain authority requires at least one bound basis artifact"
        )

    property_assessment = _mapping(
        spec.get("property_assessment"),
        "comparison_spec.property_assessment",
    )
    _exact_keys(
        property_assessment,
        field="comparison_spec.property_assessment",
        keys={"authority", "sensitivity", "bindings"},
    )
    property_authority = _text(
        property_assessment.get("authority"),
        "comparison_spec.property_assessment.authority",
    )
    if property_authority not in {"domain_verified", "diagnostic_only", "unverified"}:
        raise ModelEvidenceDiscrepancyError(
            "unsupported comparison_spec.property_assessment.authority"
        )
    sensitivity = _text(
        property_assessment.get("sensitivity"),
        "comparison_spec.property_assessment.sensitivity",
    )
    if sensitivity not in {"material", "not_material", "not_assessed"}:
        raise ModelEvidenceDiscrepancyError(
            "unsupported comparison_spec.property_assessment.sensitivity"
        )
    property_bindings = _normalize_basis_bindings(
        property_assessment.get("bindings"),
        artifact_root=artifact_root,
        field="comparison_spec.property_assessment.bindings",
    )
    if property_authority == "domain_verified" and not property_bindings:
        raise ModelEvidenceDiscrepancyError(
            "domain_verified property authority requires at least one bound basis artifact"
        )

    sufficiency = _mapping(
        spec.get("empirical_sufficiency"),
        "comparison_spec.empirical_sufficiency",
    )
    _exact_keys(
        sufficiency,
        field="comparison_spec.empirical_sufficiency",
        keys={"minimum_independent_replicates"},
    )

    required_context = _mapping(
        spec.get("required_context"),
        "comparison_spec.required_context",
    )
    _exact_keys(
        required_context,
        field="comparison_spec.required_context",
        keys=set(_CONTEXT_FIELDS),
    )

    return {
        "schema_version": "1.0",
        "target_node_id": target_node_id,
        "model_response": {
            "selector": selector,
            "index": index,
            "response_name": _text(
                model_response.get("response_name"),
                "comparison_spec.model_response.response_name",
            ),
            "unit": _text(
                model_response.get("unit"),
                "comparison_spec.model_response.unit",
            ),
        },
        "empirical_response": {
            "response_name": _text(
                empirical_response.get("response_name"),
                "comparison_spec.empirical_response.response_name",
            ),
            "unit": _text(
                empirical_response.get("unit"),
                "comparison_spec.empirical_response.unit",
            ),
        },
        "tolerance": {
            "metric": "absolute_error",
            "value": _finite(
                tolerance.get("value"),
                "comparison_spec.tolerance.value",
                nonnegative=True,
            ),
            "unit": _text(
                tolerance.get("unit"),
                "comparison_spec.tolerance.unit",
            ),
            "semantics": _text(
                tolerance.get("semantics"),
                "comparison_spec.tolerance.semantics",
            ),
        },
        "model_domain": {
            "status": domain_status,
            "authority": domain_authority,
            "basis": _text(
                model_domain.get("basis"),
                "comparison_spec.model_domain.basis",
            ),
            "bindings": domain_bindings,
        },
        "property_assessment": {
            "authority": property_authority,
            "sensitivity": sensitivity,
            "bindings": property_bindings,
        },
        "empirical_sufficiency": {
            "minimum_independent_replicates": _positive_int(
                sufficiency.get("minimum_independent_replicates"),
                "comparison_spec.empirical_sufficiency.minimum_independent_replicates",
            )
        },
        "required_context": {
            field: _text(
                required_context.get(field),
                f"comparison_spec.required_context.{field}",
            )
            for field in _CONTEXT_FIELDS
        },
    }


def _model_value(result: Mapping[str, Any], spec: Mapping[str, Any]) -> float:
    model_response = _mapping(spec.get("model_response"), "comparison.model_response")
    values = result.get("final_temperature_K")
    if not isinstance(values, list):
        raise ModelEvidenceDiscrepancyError(
            "validated model result does not contain final_temperature_K"
        )
    index = model_response.get("index")
    if isinstance(index, bool) or not isinstance(index, int) or index >= len(values):
        raise ModelEvidenceDiscrepancyError(
            "model response index is outside the solver result"
        )
    return _finite(values[index], f"solver_result.final_temperature_K[{index}]")


def _diagnosis(
    diagnosis_type: str,
    *,
    severity: str,
    statement: str,
    evidence_basis: Sequence[str],
    blocks_empirical_falsification: bool,
) -> dict[str, Any]:
    if diagnosis_type not in _DIAGNOSIS_TYPES:
        raise ModelEvidenceDiscrepancyError(
            f"unsupported discrepancy diagnosis type: {diagnosis_type}"
        )
    return {
        "diagnosis_id": f"model-evidence:{diagnosis_type}",
        "diagnosis_type": diagnosis_type,
        "severity": severity,
        "statement": statement,
        "evidence_basis": list(evidence_basis),
        "blocks_empirical_falsification": blocks_empirical_falsification,
        "epistemic_edge_created": False,
    }


def _proposal(
    suffix: str,
    *,
    action_class: str,
    description: str,
    rationale: str,
    priority: str,
    execution_mode: str = "plan_only",
) -> dict[str, Any]:
    return {
        "proposal_id": f"model-evidence:{suffix}",
        "action_class": action_class,
        "description": description,
        "rationale": rationale,
        "information_gain_priority": priority,
        "information_gain_is_calibrated_probability": False,
        "execution_mode": execution_mode,
        "availability_asserted": False,
        "automatic_execution_authorized": False,
    }


def _alternative(
    alternative_id: str,
    statement: str,
    evidence_needed: Sequence[str],
) -> dict[str, Any]:
    return {
        "alternative_id": f"model-evidence:{alternative_id}",
        "statement": statement,
        "evidence_needed": list(evidence_needed),
        "proposal_only": True,
        "scientific_status_changed": False,
    }


def _previous_ancestry(
    previous_report: Mapping[str, Any] | None,
    *,
    target: Mapping[str, Any],
) -> tuple[int, str | None, list[str]]:
    if previous_report is None:
        return 1, None, []
    previous = dict(_mapping(previous_report, "previous_discrepancy_report"))
    previous_sha = _verified_report_sha(
        previous,
        field="previous_discrepancy_report",
    )
    previous_target = _mapping(
        previous.get("target"),
        "previous_discrepancy_report.target",
    )
    if (
        previous_target.get("node_id") != target["node_id"]
        or previous_target.get("node_type") != target["node_type"]
        or previous_target.get("statement") != target["statement"]
    ):
        raise ModelEvidenceDiscrepancyError(
            "previous discrepancy report target identity differs from current target"
        )
    previous_iteration = previous.get("iteration_index")
    if (
        isinstance(previous_iteration, bool)
        or not isinstance(previous_iteration, int)
        or previous_iteration < 1
    ):
        raise ModelEvidenceDiscrepancyError(
            "previous discrepancy report iteration_index is malformed"
        )
    diagnoses = _sequence(
        previous.get("diagnoses"),
        "previous_discrepancy_report.diagnoses",
    )
    prior_types = sorted(
        {
            str(item.get("diagnosis_type"))
            for item in diagnoses
            if isinstance(item, Mapping)
            and item.get("diagnosis_type") in _DIAGNOSIS_TYPES
        }
    )
    return previous_iteration + 1, previous_sha, prior_types


def build_model_evidence_discrepancy_report(
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
) -> dict[str, Any]:
    """Build one fail-closed discrepancy diagnosis over verified model/evidence inputs."""
    if model_adapter_id != _SUPPORTED_MODEL_ADAPTER:
        raise ModelEvidenceDiscrepancyError(
            "v1 discrepancy critic supports only the audited reference-heat adapter"
        )
    target_id = _text(target_node_id, "target_node_id")
    root = Path(artifact_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ModelEvidenceDiscrepancyError("artifact_root must be a directory")

    target, assessment, graph_sha = _graph_target(
        evaluated_graph,
        target_node_id=target_id,
    )
    portfolio_target, portfolio_sha = _portfolio_target(
        hypothesis_portfolio,
        graph_sha256=graph_sha,
        target=target,
    )
    model = _verify_heat_model(
        action_report_path=action_report_path,
        execution_request_path=execution_request_path,
    )
    evidence, evidence_record = _normalize_empirical_evidence(
        empirical_evidence_path,
        artifact_root=root,
        target_node_id=target_id,
    )
    spec = _normalize_comparison_spec(
        comparison_spec,
        artifact_root=root,
        target_node_id=target_id,
    )
    iteration_index, previous_sha, prior_diagnoses = _previous_ancestry(
        previous_report,
        target=target,
    )

    verification = model["verification"]
    numerical_valid = (
        verification.get("deterministic_recomputation_verified") is True
        and verification.get("ledger_artifact_binding_verified") is True
        and verification.get("registered_outcome")
        == "numerically_validated_reference_solution"
        and verification.get("validation_state") == "passed"
        and verification.get("run_status") == "completed"
    )
    model_domain = spec["model_domain"]
    model_domain_valid = (
        model_domain["status"] == "within_declared_scope"
        and model_domain["authority"] == "domain_verified"
        and bool(model_domain["bindings"])
    )
    property_assessment = spec["property_assessment"]
    property_valid = (
        property_assessment["authority"] == "domain_verified"
        and bool(property_assessment["bindings"])
        and property_assessment["sensitivity"] != "not_assessed"
    )

    compatibility_reasons: list[str] = []
    empirical_response = evidence["response"]
    if spec["model_response"]["response_name"] != spec["empirical_response"]["response_name"]:
        compatibility_reasons.append("model/empirical response-name declarations differ")
    if spec["empirical_response"]["response_name"] != empirical_response["name"]:
        compatibility_reasons.append("empirical artifact response name differs from comparison contract")
    units = {
        spec["model_response"]["unit"],
        spec["empirical_response"]["unit"],
        spec["tolerance"]["unit"],
        empirical_response["unit"],
    }
    if len(units) != 1:
        compatibility_reasons.append("response/tolerance units are not exactly identical")
    if evidence["provenance"]["assessment_level"] != "domain_verified":
        compatibility_reasons.append("empirical provenance is not domain_verified")
    for field in _CONTEXT_FIELDS:
        if evidence["provenance"][field] != spec["required_context"][field]:
            compatibility_reasons.append(f"{field} differs from the declared comparison context")
    comparable = not compatibility_reasons

    minimum_replicates = spec["empirical_sufficiency"][
        "minimum_independent_replicates"
    ]
    empirical_sufficient = (
        evidence["independent_replicates"] >= minimum_replicates
        and evidence["replication_independence_verified"] is True
        and evidence["provenance"]["assessment_level"] == "domain_verified"
    )

    diagnoses: list[dict[str, Any]] = []
    alternatives: list[dict[str, Any]] = []
    proposals: list[dict[str, Any]] = []

    if not numerical_valid:
        diagnoses.append(
            _diagnosis(
                "numerical_invalidity",
                severity="high",
                statement=(
                    "The audited model execution is not numerically admissible for "
                    "physical model/evidence interpretation."
                ),
                evidence_basis=[
                    f"registered_outcome={verification.get('registered_outcome')}",
                    f"validation_state={verification.get('validation_state')}",
                    f"run_status={verification.get('run_status')}",
                ],
                blocks_empirical_falsification=True,
            )
        )
        alternatives.append(
            _alternative(
                "numerical-artifact",
                "The apparent model/evidence difference may be a numerical-method or discretization artifact.",
                [
                    "declared grid/time-step refinement evidence",
                    "independent numerical-method validation",
                ],
            )
        )
        proposals.append(
            _proposal(
                "validate-or-refine-numerics",
                action_class="numerical_validation",
                description=(
                    "Run a separately authorized numerical refinement or independent-method "
                    "validation before interpreting the model physically."
                ),
                rationale="Failed/rejected numerical validation blocks empirical interpretation.",
                priority="highest",
            )
        )
    else:
        if not model_domain_valid:
            diagnoses.append(
                _diagnosis(
                    "model_domain_mismatch",
                    severity="high",
                    statement=(
                        "Numerical validation passed, but model applicability to the declared "
                        "empirical regime is outside scope or not domain-verified."
                    ),
                    evidence_basis=[
                        f"model_domain.status={model_domain['status']}",
                        f"model_domain.authority={model_domain['authority']}",
                    ],
                    blocks_empirical_falsification=True,
                )
            )
            alternatives.append(
                _alternative(
                    "missing-physics-or-scope",
                    "The discrepancy may reflect omitted physics or a comparison outside the model's declared applicability.",
                    [
                        "domain-verified applicability assessment",
                        "additional-physics model or narrowed empirical scope",
                    ],
                )
            )
            proposals.append(
                _proposal(
                    "refine-model-scope",
                    action_class="model_scope_refinement",
                    description=(
                        "Refine the model scope or add explicitly justified physics before "
                        "testing the empirical hypothesis."
                    ),
                    rationale="A numerically valid model can still be scientifically out of domain.",
                    priority="highest",
                )
            )

        if not property_valid:
            diagnoses.append(
                _diagnosis(
                    "parameter_or_property_uncertainty",
                    severity="high",
                    statement=(
                        "Model property/parameter authority or sensitivity evidence is "
                        "insufficient for a strong empirical comparison."
                    ),
                    evidence_basis=[
                        f"property.authority={property_assessment['authority']}",
                        f"property.sensitivity={property_assessment['sensitivity']}",
                        f"property.binding_count={len(property_assessment['bindings'])}",
                    ],
                    blocks_empirical_falsification=True,
                )
            )
            proposals.extend(
                [
                    _proposal(
                        "parameter-sensitivity",
                        action_class="sensitivity_analysis",
                        description=(
                            "Quantify model sensitivity to the explicit material/property "
                            "inputs without imputing missing values."
                        ),
                        rationale=(
                            "Sensitivity determines whether property uncertainty can explain "
                            "the comparison outcome."
                        ),
                        priority="high",
                    ),
                    _proposal(
                        "authoritative-property-evidence",
                        action_class="external_evidence_search",
                        description=(
                            "Acquire provenance-bound authoritative property evidence for the "
                            "modeled condition."
                        ),
                        rationale=(
                            "Property values require empirical authority before they can support "
                            "a material-specific interpretation."
                        ),
                        priority="high",
                        execution_mode="explicit_authorization_required",
                    ),
                ]
            )

        if not comparable:
            diagnoses.append(
                _diagnosis(
                    "provenance_or_protocol_incompatibility",
                    severity="high",
                    statement=(
                        "The model and empirical evidence are not directly comparable under "
                        "the declared response/provenance/protocol contract."
                    ),
                    evidence_basis=compatibility_reasons,
                    blocks_empirical_falsification=True,
                )
            )
            proposals.append(
                _proposal(
                    "reconcile-protocol-semantics",
                    action_class="protocol_semantic_reconciliation",
                    description=(
                        "Reconcile units, response semantics, material state, sample identity, "
                        "conditions, and protocol before any pooled comparison."
                    ),
                    rationale="Non-comparable evidence must remain stratified rather than averaged.",
                    priority="highest",
                )
            )

        if not empirical_sufficient:
            diagnoses.append(
                _diagnosis(
                    "insufficient_empirical_evidence",
                    severity="medium",
                    statement=(
                        "Empirical coverage or replication is insufficient for a decisive "
                        "model/hypothesis comparison."
                    ),
                    evidence_basis=[
                        f"independent_replicates={evidence['independent_replicates']}",
                        f"minimum_required={minimum_replicates}",
                        (
                            "replication_independence_verified="
                            f"{evidence['replication_independence_verified']}"
                        ),
                    ],
                    blocks_empirical_falsification=True,
                )
            )
            proposals.append(
                _proposal(
                    "independent-empirical-replication",
                    action_class="replication",
                    description=(
                        "Obtain a provenance-disjoint empirical replication under the same "
                        "declared comparison context."
                    ),
                    rationale="Additional independent empirical evidence is more informative than repeated reuse of the same source lineage.",
                    priority="high",
                )
            )

    quantitative_allowed = (
        numerical_valid
        and model_domain_valid
        and property_valid
        and comparable
        and empirical_sufficient
    )
    model_value: float | None = None
    absolute_error: float | None = None
    if quantitative_allowed:
        model_value = _model_value(model["result"], spec)
        empirical_value = float(empirical_response["value"])
        absolute_error = abs(model_value - empirical_value)
        tolerance = float(spec["tolerance"]["value"])
        if absolute_error <= tolerance:
            diagnoses.append(
                _diagnosis(
                    "agreement_within_declared_tolerance",
                    severity="informational",
                    statement=(
                        "The verified model response and comparable empirical response agree "
                        "within the explicitly declared tolerance."
                    ),
                    evidence_basis=[
                        f"absolute_error={absolute_error}",
                        f"tolerance={tolerance}",
                        f"unit={spec['tolerance']['unit']}",
                    ],
                    blocks_empirical_falsification=False,
                )
            )
            proposals.append(
                _proposal(
                    "bounded-domain-closeout-review",
                    action_class="manual_review",
                    description=(
                        "Perform domain closeout review or seek independent counterevidence; "
                        "do not treat numerical agreement as automatic hypothesis confirmation."
                    ),
                    rationale="Agreement validates only this bounded comparison contract.",
                    priority="medium",
                )
            )
        else:
            diagnoses.append(
                _diagnosis(
                    "empirical_model_discrepancy",
                    severity="high",
                    statement=(
                        "A residual discrepancy remains after numerical validity, model-domain "
                        "applicability, property authority, comparability, and empirical "
                        "sufficiency gates passed."
                    ),
                    evidence_basis=[
                        f"absolute_error={absolute_error}",
                        f"tolerance={tolerance}",
                        f"unit={spec['tolerance']['unit']}",
                    ],
                    blocks_empirical_falsification=False,
                )
            )
            alternatives.extend(
                [
                    _alternative(
                        "model-form-error",
                        "The residual may reflect missing or mis-specified model physics rather than a false empirical observation.",
                        ["alternative model form", "matched-condition validation"],
                    ),
                    _alternative(
                        "hypothesis-scope-tension",
                        "The residual may expose a genuine limitation in the current hypothesis scope.",
                        [
                            "independent matched-condition replication",
                            "prespecified hypothesis reframe criteria",
                        ],
                    ),
                ]
            )
            proposals.extend(
                [
                    _proposal(
                        "discriminate-model-vs-hypothesis",
                        action_class="discriminating_analysis",
                        description=(
                            "Plan a discriminating test that separates model-form failure from "
                            "hypothesis-scope failure."
                        ),
                        rationale="A fully admissible residual discrepancy requires model/hypothesis discrimination, not immediate falsification.",
                        priority="highest",
                    ),
                    _proposal(
                        "independent-matched-replication",
                        action_class="replication",
                        description=(
                            "Repeat the empirical comparison with provenance-disjoint matched-condition evidence."
                        ),
                        rationale="Independent replication tests whether the residual is reproducible.",
                        priority="high",
                    ),
                ]
            )

    if portfolio_target is not None:
        state = portfolio_target.get("portfolio_state")
        if state == "retired_falsified_within_verified_scope":
            proposals.insert(
                0,
                _proposal(
                    "preserve-falsified-status",
                    action_class="hypothesis_reframe",
                    description=(
                        "Preserve the existing verified falsification and reframe a new "
                        "hypothesis identity before any rescue attempt."
                    ),
                    rationale="A discrepancy report cannot reactivate a falsified hypothesis.",
                    priority="highest",
                ),
            )
        elif state == "challenge_or_retirement_review":
            proposals.insert(
                0,
                _proposal(
                    "preserve-contradiction-review",
                    action_class="hypothesis_review",
                    description=(
                        "Preserve the verified contradiction and complete challenge/retirement "
                        "review before positive-claim continuation."
                    ),
                    rationale="A model comparison cannot erase verified negative epistemic state.",
                    priority="highest",
                ),
            )

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for proposal in proposals:
        proposal_id = str(proposal["proposal_id"])
        if proposal_id not in seen:
            seen.add(proposal_id)
            deduped.append(proposal)
    for rank, proposal in enumerate(deduped, start=1):
        proposal["rank"] = rank

    diagnosis_types = [str(item["diagnosis_type"]) for item in diagnoses]
    portfolio_state = (
        portfolio_target.get("portfolio_state") if portfolio_target is not None else None
    )
    if portfolio_state == "retired_falsified_within_verified_scope":
        recommendation = "preserve_falsification_and_reframe"
        rationale = (
            "The current hypothesis is already falsified within verified scope; this critic "
            "cannot reactivate it."
        )
    elif portfolio_state == "challenge_or_retirement_review":
        recommendation = "preserve_contradiction_and_review_scope"
        rationale = (
            "Verified contradiction remains active and must survive model/evidence re-analysis."
        )
    elif "numerical_invalidity" in diagnosis_types:
        recommendation = "replan_before_physical_interpretation"
        rationale = "Numerical validity is a prerequisite for physical discrepancy interpretation."
    elif "empirical_model_discrepancy" in diagnosis_types:
        recommendation = "continue_discriminating_research"
        rationale = "A fully admissible residual discrepancy remains unresolved."
    elif "agreement_within_declared_tolerance" in diagnosis_types:
        recommendation = "comparison_closeout_only_domain_review_required"
        rationale = (
            "This bounded comparison agrees, but hypothesis confirmation and scientific "
            "closeout remain outside the critic's authority."
        )
    elif diagnoses:
        recommendation = "replan_to_resolve_upstream_comparison_gates"
        rationale = (
            "One or more upstream validity, applicability, provenance, property, or evidence "
            "gates prevent a decisive comparison."
        )
    else:
        recommendation = "bounded_abstention"
        rationale = "No stronger diagnosis is justified under the supplied contracts."

    result: dict[str, Any] = {
        "schema_version": MODEL_EVIDENCE_DISCREPANCY_SCHEMA_VERSION,
        "policy_version": MODEL_EVIDENCE_DISCREPANCY_POLICY_VERSION,
        "critic_id": (
            f"model-evidence:{target['graph_id']}:{target['node_id']}:"
            f"{model['action_report']['sha256'][:12]}:{evidence_record['sha256'][:12]}"
        ),
        "iteration_index": iteration_index,
        "target": dict(target),
        "epistemic_assessment": dict(assessment),
        "hypothesis_portfolio_state": portfolio_target,
        "comparison_contract": spec,
        "empirical_evidence": evidence,
        "input_bindings": {
            "model_adapter_id": model_adapter_id,
            "model_action_report": dict(model["action_report"]),
            "execution_request": dict(model["execution_request"]),
            "solver_result": dict(model["solver_result"]),
            "empirical_evidence": dict(evidence_record),
            "evaluated_graph": {"canonical_sha256": graph_sha},
            "hypothesis_portfolio": (
                {"portfolio_sha256": portfolio_sha} if portfolio_sha is not None else None
            ),
            "previous_discrepancy_report": (
                {"report_sha256": previous_sha} if previous_sha is not None else None
            ),
        },
        "gates": {
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
            "model_domain": {
                "passed": model_domain_valid,
                "status": model_domain["status"],
                "authority": model_domain["authority"],
                "basis_binding_count": len(model_domain["bindings"]),
            },
            "property_authority": {
                "passed": property_valid,
                "authority": property_assessment["authority"],
                "sensitivity": property_assessment["sensitivity"],
                "basis_binding_count": len(property_assessment["bindings"]),
            },
            "comparability": {
                "passed": comparable,
                "reasons": compatibility_reasons,
            },
            "empirical_sufficiency": {
                "passed": empirical_sufficient,
                "independent_replicates": evidence["independent_replicates"],
                "minimum_required": minimum_replicates,
                "replication_independence_verified": evidence[
                    "replication_independence_verified"
                ],
            },
        },
        "quantitative_comparison": {
            "performed": quantitative_allowed,
            "metric": "absolute_error",
            "model_value": model_value,
            "empirical_value": (
                float(empirical_response["value"]) if quantitative_allowed else None
            ),
            "absolute_error": absolute_error,
            "tolerance": float(spec["tolerance"]["value"]),
            "unit": spec["tolerance"]["unit"],
            "tolerance_semantics": spec["tolerance"]["semantics"],
        },
        "diagnoses": diagnoses,
        "alternative_explanations": alternatives,
        "ranked_next_actions": deduped,
        "stop_recommendation": {
            "recommendation": recommendation,
            "rationale": rationale,
            "automatic_stop_authorized": False,
            "positive_scientific_closeout_granted": False,
        },
        "ancestry": {
            "previous_report_sha256": previous_sha,
            "prior_diagnosis_types": prior_diagnoses,
            "current_diagnosis_types": sorted(set(diagnosis_types)),
        },
        "autonomy_boundary": {
            "diagnostic_orchestration_only": True,
            "scientific_status_changed": False,
            "epistemic_edge_created": False,
            "confidence_probability_estimated": False,
            "automatic_execution_authorized": False,
            "physical_experiment_executed": False,
            "network_access_performed": False,
            "domain_authority_input_contract_independently_adjudicated": False,
            "model_agreement_confirms_hypothesis": False,
        },
    }
    result["report_sha256"] = _canonical_sha256(result)
    return result


def _record_matches(record: Mapping[str, Any], current: Mapping[str, Any], *, field: str) -> None:
    if (
        record.get("path") != current.get("path")
        or record.get("sha256") != current.get("sha256")
        or record.get("bytes") != current.get("bytes")
    ):
        raise ModelEvidenceDiscrepancyError(
            f"{field} current bytes differ from discrepancy-report binding"
        )


def validate_model_evidence_discrepancy_report(
    report: Mapping[str, Any],
    *,
    evaluated_graph: Mapping[str, Any],
    hypothesis_portfolio: Mapping[str, Any] | None = None,
    previous_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Revalidate report identity plus all bound model/evidence artifacts."""
    value = dict(_mapping(report, "discrepancy_report"))
    if value.get("schema_version") != MODEL_EVIDENCE_DISCREPANCY_SCHEMA_VERSION:
        raise ModelEvidenceDiscrepancyError("unsupported discrepancy report schema_version")
    if value.get("policy_version") != MODEL_EVIDENCE_DISCREPANCY_POLICY_VERSION:
        raise ModelEvidenceDiscrepancyError("unsupported discrepancy report policy_version")
    digest = _verified_report_sha(value, field="discrepancy_report")
    target = _mapping(value.get("target"), "discrepancy_report.target")
    target_id = _text(target.get("node_id"), "discrepancy_report.target.node_id")
    current_target, _assessment, graph_sha = _graph_target(
        evaluated_graph,
        target_node_id=target_id,
    )
    for field in ("node_id", "node_type", "statement", "graph_id"):
        if current_target.get(field) != target.get(field):
            raise ModelEvidenceDiscrepancyError(
                "discrepancy report target identity differs from current evaluated graph"
            )
    bindings = _mapping(value.get("input_bindings"), "discrepancy_report.input_bindings")
    graph_binding = _mapping(
        bindings.get("evaluated_graph"),
        "discrepancy_report.input_bindings.evaluated_graph",
    )
    if _sha(
        graph_binding.get("canonical_sha256"),
        "discrepancy_report.input_bindings.evaluated_graph.canonical_sha256",
    ) != graph_sha:
        raise ModelEvidenceDiscrepancyError(
            "evaluated graph canonical SHA differs from discrepancy report"
        )

    bound_portfolio = bindings.get("hypothesis_portfolio")
    portfolio_target, portfolio_sha = _portfolio_target(
        hypothesis_portfolio,
        graph_sha256=graph_sha,
        target=current_target,
    ) if bound_portfolio is not None else (None, None)
    if bound_portfolio is not None:
        if hypothesis_portfolio is None:
            raise ModelEvidenceDiscrepancyError(
                "discrepancy report requires its bound hypothesis portfolio"
            )
        expected_portfolio = _mapping(
            bound_portfolio,
            "discrepancy_report.input_bindings.hypothesis_portfolio",
        )
        if _sha(
            expected_portfolio.get("portfolio_sha256"),
            "discrepancy_report.input_bindings.hypothesis_portfolio.portfolio_sha256",
        ) != portfolio_sha:
            raise ModelEvidenceDiscrepancyError(
                "hypothesis portfolio differs from discrepancy report binding"
            )
        if value.get("hypothesis_portfolio_state") != portfolio_target:
            raise ModelEvidenceDiscrepancyError(
                "hypothesis portfolio target state differs from discrepancy report"
            )
    elif hypothesis_portfolio is not None:
        raise ModelEvidenceDiscrepancyError(
            "an unbound hypothesis portfolio cannot be injected during validation"
        )

    bound_previous = bindings.get("previous_discrepancy_report")
    if bound_previous is not None:
        if previous_report is None:
            raise ModelEvidenceDiscrepancyError(
                "discrepancy report requires its bound previous report"
            )
        previous_sha = _verified_report_sha(
            previous_report,
            field="previous_discrepancy_report",
        )
        expected_previous = _mapping(
            bound_previous,
            "discrepancy_report.input_bindings.previous_discrepancy_report",
        )
        if _sha(
            expected_previous.get("report_sha256"),
            "discrepancy_report.input_bindings.previous_discrepancy_report.report_sha256",
        ) != previous_sha:
            raise ModelEvidenceDiscrepancyError(
                "previous discrepancy report ancestry drifted"
            )
    elif previous_report is not None:
        raise ModelEvidenceDiscrepancyError(
            "an unbound previous discrepancy report cannot be injected during validation"
        )

    action_record = _mapping(
        bindings.get("model_action_report"),
        "discrepancy_report.input_bindings.model_action_report",
    )
    request_record = _mapping(
        bindings.get("execution_request"),
        "discrepancy_report.input_bindings.execution_request",
    )
    model = _verify_heat_model(
        action_report_path=_text(
            action_record.get("path"),
            "discrepancy_report.input_bindings.model_action_report.path",
        ),
        execution_request_path=_text(
            request_record.get("path"),
            "discrepancy_report.input_bindings.execution_request.path",
        ),
    )
    _record_matches(action_record, model["action_report"], field="model_action_report")
    _record_matches(request_record, model["execution_request"], field="execution_request")
    solver_record = _mapping(
        bindings.get("solver_result"),
        "discrepancy_report.input_bindings.solver_result",
    )
    _record_matches(solver_record, model["solver_result"], field="solver_result")

    evidence_record = _mapping(
        bindings.get("empirical_evidence"),
        "discrepancy_report.input_bindings.empirical_evidence",
    )
    current_evidence = _file_record(
        Path(
            _text(
                evidence_record.get("path"),
                "discrepancy_report.input_bindings.empirical_evidence.path",
            )
        ),
        field="empirical_evidence",
    )
    _record_matches(evidence_record, current_evidence, field="empirical_evidence")

    comparison = _mapping(
        value.get("comparison_contract"),
        "discrepancy_report.comparison_contract",
    )
    for section in ("model_domain", "property_assessment"):
        section_value = _mapping(
            comparison.get(section),
            f"discrepancy_report.comparison_contract.{section}",
        )
        for index, raw in enumerate(
            _sequence(
                section_value.get("bindings"),
                f"discrepancy_report.comparison_contract.{section}.bindings",
            )
        ):
            bound = _mapping(
                raw,
                f"discrepancy_report.comparison_contract.{section}.bindings[{index}]",
            )
            current = _file_record(
                Path(
                    _text(
                        bound.get("path"),
                        f"discrepancy_report.comparison_contract.{section}.bindings[{index}].path",
                    )
                ),
                field=f"{section}.binding[{index}]",
            )
            _record_matches(bound, current, field=f"{section}.binding[{index}]")

    if value.get("autonomy_boundary", {}).get("scientific_status_changed") is not False:
        raise ModelEvidenceDiscrepancyError(
            "validated discrepancy report must not change scientific status"
        )
    if value.get("autonomy_boundary", {}).get("automatic_execution_authorized") is not False:
        raise ModelEvidenceDiscrepancyError(
            "validated discrepancy report must not authorize execution"
        )
    return {
        "report_sha256": digest,
        "target_node_id": target_id,
        "iteration_index": value.get("iteration_index"),
        "diagnosis_types": list(value.get("ancestry", {}).get("current_diagnosis_types", [])),
        "artifact_bindings_reverified": True,
        "scientific_status_changed": False,
        "automatic_execution_authorized": False,
    }


__all__ = [
    "MODEL_EVIDENCE_DISCREPANCY_POLICY_VERSION",
    "MODEL_EVIDENCE_DISCREPANCY_SCHEMA_VERSION",
    "ModelEvidenceDiscrepancyError",
    "build_model_evidence_discrepancy_report",
    "validate_model_evidence_discrepancy_report",
]
