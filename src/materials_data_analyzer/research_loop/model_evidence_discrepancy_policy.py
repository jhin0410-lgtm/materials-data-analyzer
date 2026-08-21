"""Fail-closed public policy for model/evidence discrepancy diagnosis.

The structural discrepancy engine intentionally accepts externally supplied domain-review
claims so it can diagnose a wide range of evidence states.  This policy layer is the
stable public boundary.  It adds three invariants that must not be delegated to a
self-authored comparison manifest:

* recursive reports must remain on the same epistemic graph identity;
* multi-replicate empirical sufficiency requires checksum-bound, provenance-disjoint
  replicate records plus a separately bound domain-verification artifact;
* a stored report is valid only if deterministic reconstruction from its currently bound
  inputs reproduces the complete report byte-for-byte at the canonical-JSON level.

The policy still does not adjudicate the *scientific correctness* of a domain verifier.
It proves only that a declared authority decision and its evidence were explicitly bound
and remained unchanged.  No epistemic edge or execution authorization is created here.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .kernel import ResearchLoopError
from .model_evidence_discrepancy import (
    MODEL_EVIDENCE_DISCREPANCY_POLICY_VERSION,
    MODEL_EVIDENCE_DISCREPANCY_SCHEMA_VERSION,
    ModelEvidenceDiscrepancyError,
    build_model_evidence_discrepancy_report as _build_structural_report,
)

MODEL_EVIDENCE_DISCREPANCY_HARDENING_POLICY_VERSION = "1.0"
REPLICATION_VERIFICATION_SCHEMA_VERSION = "1.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PRIORITY_ORDER = {"highest": 0, "high": 1, "medium": 2, "low": 3}
_PRESERVATION_CLASSES = {"hypothesis_reframe", "hypothesis_review"}
_STRONG_COMPARISON_DIAGNOSES = {
    "empirical_model_discrepancy",
    "agreement_within_declared_tolerance",
}
_STRONG_ONLY_PROPOSAL_SUFFIXES = {
    "bounded-domain-closeout-review",
    "discriminate-model-vs-hypothesis",
    "independent-matched-replication",
}


class ModelEvidenceDiscrepancyPolicyError(ResearchLoopError):
    """Raised when public discrepancy policy cannot preserve provenance."""


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
        raise ModelEvidenceDiscrepancyPolicyError(
            "hardened discrepancy state must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(payload).hexdigest()


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ModelEvidenceDiscrepancyPolicyError(f"{field} must be an object")
    return value


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ModelEvidenceDiscrepancyPolicyError(f"{field} must be a sequence")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ModelEvidenceDiscrepancyPolicyError(f"{field} must be non-empty trimmed text")
    return value


def _sha(value: object, field: str) -> str:
    text = _text(value, field)
    if _SHA256.fullmatch(text) is None:
        raise ModelEvidenceDiscrepancyPolicyError(f"{field} must be lowercase SHA-256")
    return text


def _exact_keys(value: Mapping[str, Any], *, field: str, keys: set[str]) -> None:
    missing = sorted(keys - set(value))
    unknown = sorted(set(value) - keys)
    if missing:
        raise ModelEvidenceDiscrepancyPolicyError(
            f"{field} is missing required keys: {', '.join(missing)}"
        )
    if unknown:
        raise ModelEvidenceDiscrepancyPolicyError(
            f"{field} has unknown keys: {', '.join(unknown)}"
        )


def _resolve_bound_file(
    value: object,
    *,
    artifact_root: Path,
    field: str,
) -> dict[str, Any]:
    binding = _mapping(value, field)
    _exact_keys(binding, field=field, keys={"path", "sha256"})
    raw = Path(_text(binding.get("path"), f"{field}.path")).expanduser()
    path = raw if raw.is_absolute() else artifact_root / raw
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ModelEvidenceDiscrepancyPolicyError(
            f"{field} does not resolve to an existing file"
        ) from exc
    try:
        resolved.relative_to(artifact_root)
    except ValueError as exc:
        raise ModelEvidenceDiscrepancyPolicyError(f"{field} escapes artifact_root") from exc
    if not resolved.is_file():
        raise ModelEvidenceDiscrepancyPolicyError(f"{field} must resolve to a file")
    data = resolved.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    expected = _sha(binding.get("sha256"), f"{field}.sha256")
    if actual != expected:
        raise ModelEvidenceDiscrepancyPolicyError(
            f"{field} checksum differs from the declared SHA-256"
        )
    return {"path": str(resolved), "sha256": actual, "bytes": len(data)}


def _read_json(path: Path, *, field: str) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ModelEvidenceDiscrepancyPolicyError(f"could not read {field}") from exc

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ModelEvidenceDiscrepancyPolicyError(
                    f"duplicate JSON key is not allowed in {field}: {key}"
                )
            result[key] = item
        return result

    try:
        value = json.loads(raw, object_pairs_hook=reject_duplicates)
    except json.JSONDecodeError as exc:
        raise ModelEvidenceDiscrepancyPolicyError(f"invalid {field} JSON") from exc
    if not isinstance(value, dict):
        raise ModelEvidenceDiscrepancyPolicyError(f"{field} root must be an object")
    return value


def _same_graph_ancestry(
    previous_report: Mapping[str, Any] | None,
    *,
    evaluated_graph: Mapping[str, Any],
    target_node_id: str,
) -> None:
    if previous_report is None:
        return
    graph_id = _text(evaluated_graph.get("graph_id"), "evaluated_graph.graph_id")
    target = _mapping(previous_report.get("target"), "previous_discrepancy_report.target")
    if target.get("graph_id") != graph_id or target.get("node_id") != target_node_id:
        raise ModelEvidenceDiscrepancyPolicyError(
            "previous discrepancy report graph/target ancestry differs from current graph"
        )


def _replication_manifest(
    path: str | Path,
    *,
    artifact_root: Path,
    evidence_id: str,
    target_node_id: str,
) -> dict[str, Any]:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = artifact_root / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ModelEvidenceDiscrepancyPolicyError(
            "replication_verification_path does not resolve"
        ) from exc
    try:
        resolved.relative_to(artifact_root)
    except ValueError as exc:
        raise ModelEvidenceDiscrepancyPolicyError(
            "replication_verification_path escapes artifact_root"
        ) from exc
    data = resolved.read_bytes()
    manifest = _read_json(resolved, field="replication_verification")
    _exact_keys(
        manifest,
        field="replication_verification",
        keys={
            "schema_version",
            "evidence_id",
            "target_node_id",
            "replicates",
            "independence_assessment",
        },
    )
    if manifest.get("schema_version") != REPLICATION_VERIFICATION_SCHEMA_VERSION:
        raise ModelEvidenceDiscrepancyPolicyError(
            "unsupported replication verification schema_version"
        )
    if manifest.get("evidence_id") != evidence_id:
        raise ModelEvidenceDiscrepancyPolicyError(
            "replication verification evidence_id differs from empirical evidence"
        )
    if manifest.get("target_node_id") != target_node_id:
        raise ModelEvidenceDiscrepancyPolicyError(
            "replication verification target differs from discrepancy target"
        )
    replicates = _sequence(manifest.get("replicates"), "replication_verification.replicates")
    normalized: list[dict[str, Any]] = []
    replicate_ids: set[str] = set()
    lineages: set[str] = set()
    artifact_paths: set[str] = set()
    for index, raw in enumerate(replicates):
        item = _mapping(raw, f"replication_verification.replicates[{index}]")
        _exact_keys(
            item,
            field=f"replication_verification.replicates[{index}]",
            keys={"replicate_id", "source_lineage_id", "artifact_binding"},
        )
        replicate_id = _text(
            item.get("replicate_id"),
            f"replication_verification.replicates[{index}].replicate_id",
        )
        lineage = _text(
            item.get("source_lineage_id"),
            f"replication_verification.replicates[{index}].source_lineage_id",
        )
        if replicate_id in replicate_ids:
            raise ModelEvidenceDiscrepancyPolicyError(
                "replication verification contains duplicate replicate_id"
            )
        if lineage in lineages:
            raise ModelEvidenceDiscrepancyPolicyError(
                "replication verification source lineages are not provenance-disjoint"
            )
        binding = _resolve_bound_file(
            item.get("artifact_binding"),
            artifact_root=artifact_root,
            field=f"replication_verification.replicates[{index}].artifact_binding",
        )
        if binding["path"] in artifact_paths:
            raise ModelEvidenceDiscrepancyPolicyError(
                "replication verification reuses the same artifact path"
            )
        replicate_ids.add(replicate_id)
        lineages.add(lineage)
        artifact_paths.add(str(binding["path"]))
        normalized.append(
            {
                "replicate_id": replicate_id,
                "source_lineage_id": lineage,
                "artifact_binding": binding,
            }
        )
    assessment = _mapping(
        manifest.get("independence_assessment"),
        "replication_verification.independence_assessment",
    )
    _exact_keys(
        assessment,
        field="replication_verification.independence_assessment",
        keys={"assessment_level", "verification_artifact"},
    )
    if assessment.get("assessment_level") != "domain_verified":
        raise ModelEvidenceDiscrepancyPolicyError(
            "replication independence requires a domain_verified assessment"
        )
    verification_artifact = _resolve_bound_file(
        assessment.get("verification_artifact"),
        artifact_root=artifact_root,
        field="replication_verification.independence_assessment.verification_artifact",
    )
    return {
        "manifest_binding": {
            "path": str(resolved),
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        },
        "replicates": normalized,
        "replicate_count": len(normalized),
        "source_lineage_count": len(lineages),
        "independence_assessment": {
            "assessment_level": "domain_verified",
            "verification_artifact": verification_artifact,
        },
        "independence_semantics_independently_adjudicated_by_policy": False,
    }


def _priority_sort(actions: Sequence[object]) -> list[dict[str, Any]]:
    normalized: list[tuple[int, int, int, str, dict[str, Any]]] = []
    for index, raw in enumerate(actions):
        item = dict(_mapping(raw, f"ranked_next_actions[{index}]"))
        priority = _text(
            item.get("information_gain_priority"),
            f"ranked_next_actions[{index}].information_gain_priority",
        )
        if priority not in _PRIORITY_ORDER:
            raise ModelEvidenceDiscrepancyPolicyError(
                "unsupported information_gain_priority in discrepancy proposal"
            )
        preservation = 0 if item.get("action_class") in _PRESERVATION_CLASSES else 1
        prior_rank = item.get("rank")
        stable_rank = prior_rank if isinstance(prior_rank, int) and not isinstance(prior_rank, bool) else index + 1
        normalized.append(
            (
                preservation,
                _PRIORITY_ORDER[priority],
                stable_rank,
                str(item.get("proposal_id", "")),
                item,
            )
        )
    result: list[dict[str, Any]] = []
    for rank, (_preservation, _priority, _stable, _proposal_id, item) in enumerate(
        sorted(normalized, key=lambda row: row[:4]),
        start=1,
    ):
        item["rank"] = rank
        result.append(item)
    return result


def _downgrade_unverified_replication(
    report: dict[str, Any],
    *,
    reason: str,
) -> None:
    gates = dict(_mapping(report.get("gates"), "report.gates"))
    sufficiency = dict(
        _mapping(gates.get("empirical_sufficiency"), "report.gates.empirical_sufficiency")
    )
    sufficiency["passed"] = False
    sufficiency["replication_provenance_verified"] = False
    sufficiency["replication_provenance_reason"] = reason
    gates["empirical_sufficiency"] = sufficiency
    report["gates"] = gates

    quantitative = dict(
        _mapping(report.get("quantitative_comparison"), "report.quantitative_comparison")
    )
    quantitative["performed"] = False
    quantitative["model_value"] = None
    quantitative["empirical_value"] = None
    quantitative["absolute_error"] = None
    report["quantitative_comparison"] = quantitative

    diagnoses = [
        dict(_mapping(item, "report.diagnosis"))
        for item in _sequence(report.get("diagnoses", []), "report.diagnoses")
        if isinstance(item, Mapping)
        and item.get("diagnosis_type") not in _STRONG_COMPARISON_DIAGNOSES
    ]
    if not any(item.get("diagnosis_type") == "insufficient_empirical_evidence" for item in diagnoses):
        diagnoses.append(
            {
                "diagnosis_id": "model-evidence:insufficient_empirical_evidence",
                "diagnosis_type": "insufficient_empirical_evidence",
                "severity": "high",
                "statement": (
                    "Empirical replication count is not backed by the required checksum-bound, "
                    "provenance-disjoint replication verification contract."
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
        if isinstance(item, Mapping)
        and str(item.get("proposal_id", "")).split("model-evidence:")[-1]
        not in _STRONG_ONLY_PROPOSAL_SUFFIXES
    ]
    if not any(item.get("proposal_id") == "model-evidence:verify-replication-provenance" for item in proposals):
        proposals.append(
            {
                "proposal_id": "model-evidence:verify-replication-provenance",
                "action_class": "replication_provenance_verification",
                "description": (
                    "Bind provenance-disjoint replicate artifacts and a separate domain verification "
                    "of their independence before a strong model/evidence comparison."
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
    current_types = sorted({str(item.get("diagnosis_type")) for item in diagnoses})
    ancestry = dict(_mapping(report.get("ancestry"), "report.ancestry"))
    ancestry["current_diagnosis_types"] = current_types
    report["ancestry"] = ancestry
    report["stop_recommendation"] = {
        "recommendation": "replan_to_resolve_upstream_comparison_gates",
        "rationale": (
            "Strong model/evidence interpretation is blocked until empirical replication "
            "provenance is explicitly verified."
        ),
        "automatic_stop_authorized": False,
        "positive_scientific_closeout_granted": False,
    }


def build_policy_hardened_model_evidence_discrepancy_report(
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
) -> dict[str, Any]:
    """Build the stable public discrepancy report with provenance hardening."""
    root = Path(artifact_root).expanduser().resolve(strict=True)
    _same_graph_ancestry(
        previous_report,
        evaluated_graph=evaluated_graph,
        target_node_id=target_node_id,
    )
    report = _build_structural_report(
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
    )
    evidence = _mapping(report.get("empirical_evidence"), "report.empirical_evidence")
    evidence_id = _text(evidence.get("evidence_id"), "report.empirical_evidence.evidence_id")
    declared_count = evidence.get("independent_replicates")
    if isinstance(declared_count, bool) or not isinstance(declared_count, int) or declared_count < 1:
        raise ModelEvidenceDiscrepancyPolicyError(
            "report empirical independent_replicates is malformed"
        )
    comparison = _mapping(report.get("comparison_contract"), "report.comparison_contract")
    sufficiency_contract = _mapping(
        comparison.get("empirical_sufficiency"),
        "report.comparison_contract.empirical_sufficiency",
    )
    minimum = sufficiency_contract.get("minimum_independent_replicates")
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 1:
        raise ModelEvidenceDiscrepancyPolicyError(
            "minimum_independent_replicates is malformed"
        )

    replication = None
    replication_verified = minimum <= 1 and declared_count == 1
    replication_reason = "single-replicate contract requires no independence claim"
    if replication_verification_path is not None:
        replication = _replication_manifest(
            replication_verification_path,
            artifact_root=root,
            evidence_id=evidence_id,
            target_node_id=target_node_id,
        )
        replication_verified = (
            replication["replicate_count"] == declared_count
            and replication["source_lineage_count"] == declared_count
            and replication["replicate_count"] >= minimum
            and evidence.get("replication_independence_verified") is True
        )
        replication_reason = (
            "replication manifest count/lineage/independence contract verified"
            if replication_verified
            else "replication manifest does not satisfy declared count and minimum requirements"
        )

    report["ranked_next_actions"] = _priority_sort(
        _sequence(report.get("ranked_next_actions", []), "report.ranked_next_actions")
    )
    if not replication_verified:
        _downgrade_unverified_replication(report, reason=replication_reason)
    else:
        gates = dict(_mapping(report.get("gates"), "report.gates"))
        sufficiency = dict(
            _mapping(gates.get("empirical_sufficiency"), "report.gates.empirical_sufficiency")
        )
        sufficiency["replication_provenance_verified"] = True
        sufficiency["replication_provenance_reason"] = replication_reason
        gates["empirical_sufficiency"] = sufficiency
        report["gates"] = gates

    report["provenance_hardening"] = {
        "policy_version": MODEL_EVIDENCE_DISCREPANCY_HARDENING_POLICY_VERSION,
        "replication_verification": replication,
        "strong_comparison_requires_bound_replication_provenance": True,
        "graph_identity_continuity_required": True,
        "complete_report_deterministic_rebuild_required": True,
        "domain_authority_semantics_independently_adjudicated_by_policy": False,
    }
    report.pop("report_sha256", None)
    report["report_sha256"] = _canonical_sha256(report)
    return report


def _strip_binding_bytes(value: object, *, field: str) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for index, raw in enumerate(_sequence(value, field)):
        item = _mapping(raw, f"{field}[{index}]")
        result.append(
            {
                "path": _text(item.get("path"), f"{field}[{index}].path"),
                "sha256": _sha(item.get("sha256"), f"{field}[{index}].sha256"),
            }
        )
    return result


def _comparison_input_from_report(report: Mapping[str, Any]) -> dict[str, Any]:
    comparison = json.loads(json.dumps(_mapping(report.get("comparison_contract"), "report.comparison_contract")))
    for section in ("model_domain", "property_assessment"):
        item = _mapping(comparison.get(section), f"report.comparison_contract.{section}")
        item["bindings"] = _strip_binding_bytes(
            item.get("bindings", []),
            field=f"report.comparison_contract.{section}.bindings",
        )
    return comparison


def _repository_root_from_request(path: str | Path) -> Path:
    request_path = Path(path).expanduser().resolve(strict=True)
    value = _read_json(request_path, field="execution_request")
    raw = value.get("repository_root")
    root = Path(_text(raw, "execution_request.repository_root")).expanduser()
    if not root.is_absolute():
        root = request_path.parent / root
    resolved = root.resolve(strict=True)
    if not resolved.is_dir():
        raise ModelEvidenceDiscrepancyPolicyError(
            "execution_request.repository_root must resolve to a directory"
        )
    return resolved


def validate_policy_hardened_model_evidence_discrepancy_report(
    report: Mapping[str, Any],
    *,
    evaluated_graph: Mapping[str, Any],
    hypothesis_portfolio: Mapping[str, Any] | None = None,
    previous_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Rebuild the complete public report and reject any self-recertified mutation."""
    value = dict(_mapping(report, "discrepancy_report"))
    embedded = _sha(value.pop("report_sha256", None), "discrepancy_report.report_sha256")
    if _canonical_sha256(value) != embedded:
        raise ModelEvidenceDiscrepancyPolicyError(
            "discrepancy report canonical SHA-256 does not match its content"
        )
    value["report_sha256"] = embedded
    hardening = _mapping(value.get("provenance_hardening"), "discrepancy_report.provenance_hardening")
    if hardening.get("policy_version") != MODEL_EVIDENCE_DISCREPANCY_HARDENING_POLICY_VERSION:
        raise ModelEvidenceDiscrepancyPolicyError(
            "unsupported discrepancy hardening policy_version"
        )
    target = _mapping(value.get("target"), "discrepancy_report.target")
    target_id = _text(target.get("node_id"), "discrepancy_report.target.node_id")
    _same_graph_ancestry(
        previous_report,
        evaluated_graph=evaluated_graph,
        target_node_id=target_id,
    )
    bindings = _mapping(value.get("input_bindings"), "discrepancy_report.input_bindings")
    action = _mapping(bindings.get("model_action_report"), "input_bindings.model_action_report")
    request = _mapping(bindings.get("execution_request"), "input_bindings.execution_request")
    evidence = _mapping(bindings.get("empirical_evidence"), "input_bindings.empirical_evidence")
    artifact_root = _repository_root_from_request(
        _text(request.get("path"), "input_bindings.execution_request.path")
    )
    replication = hardening.get("replication_verification")
    replication_path = None
    if replication is not None:
        replication_map = _mapping(replication, "provenance_hardening.replication_verification")
        manifest_binding = _mapping(
            replication_map.get("manifest_binding"),
            "provenance_hardening.replication_verification.manifest_binding",
        )
        replication_path = _text(
            manifest_binding.get("path"),
            "provenance_hardening.replication_verification.manifest_binding.path",
        )

    rebuilt = build_policy_hardened_model_evidence_discrepancy_report(
        model_adapter_id=_text(bindings.get("model_adapter_id"), "input_bindings.model_adapter_id"),
        action_report_path=_text(action.get("path"), "input_bindings.model_action_report.path"),
        execution_request_path=_text(request.get("path"), "input_bindings.execution_request.path"),
        empirical_evidence_path=_text(evidence.get("path"), "input_bindings.empirical_evidence.path"),
        comparison_spec=_comparison_input_from_report(value),
        evaluated_graph=evaluated_graph,
        target_node_id=target_id,
        artifact_root=artifact_root,
        hypothesis_portfolio=hypothesis_portfolio,
        previous_report=previous_report,
        replication_verification_path=replication_path,
    )
    if rebuilt != value:
        raise ModelEvidenceDiscrepancyPolicyError(
            "discrepancy report differs from deterministic reconstruction of current bound inputs"
        )
    diagnoses = _sequence(value.get("diagnoses", []), "discrepancy_report.diagnoses")
    diagnosis_types = [
        str(item.get("diagnosis_type"))
        for item in diagnoses
        if isinstance(item, Mapping)
    ]
    return {
        "report_sha256": embedded,
        "target_node_id": target_id,
        "iteration_index": value.get("iteration_index"),
        "diagnosis_types": diagnosis_types,
        "artifact_bindings_reverified": True,
        "complete_report_deterministic_rebuild_verified": True,
        "replication_provenance_verified": bool(
            value.get("gates", {}).get("empirical_sufficiency", {}).get(
                "replication_provenance_verified"
            )
        ),
        "scientific_status_changed": False,
        "automatic_execution_authorized": False,
    }


# Stable names mirror the public package API while leaving the structural engine
# available for focused internal tests and diagnostics.
build_model_evidence_discrepancy_report = (
    build_policy_hardened_model_evidence_discrepancy_report
)
validate_model_evidence_discrepancy_report = (
    validate_policy_hardened_model_evidence_discrepancy_report
)


__all__ = [
    "MODEL_EVIDENCE_DISCREPANCY_HARDENING_POLICY_VERSION",
    "MODEL_EVIDENCE_DISCREPANCY_POLICY_VERSION",
    "MODEL_EVIDENCE_DISCREPANCY_SCHEMA_VERSION",
    "REPLICATION_VERIFICATION_SCHEMA_VERSION",
    "ModelEvidenceDiscrepancyError",
    "ModelEvidenceDiscrepancyPolicyError",
    "build_model_evidence_discrepancy_report",
    "build_policy_hardened_model_evidence_discrepancy_report",
    "validate_model_evidence_discrepancy_report",
    "validate_policy_hardened_model_evidence_discrepancy_report",
]
