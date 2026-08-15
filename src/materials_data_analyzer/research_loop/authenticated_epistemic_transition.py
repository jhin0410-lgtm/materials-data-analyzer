"""Authenticated successor-graph production for exact directional inference identity.

This additive producer validates the existing transition contract but constructs the
successor directly from exact base/proposal/verifier/result snapshots. It does not re-read
proposal bytes through a staging transition, eliminating that TOCTOU boundary.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any, Mapping

from .authenticated_inference_binding import (
    DOMAIN_VERIFICATION_DECISION_SCHEMA_VERSION,
    AuthenticatedInferenceBindingError,
    authenticate_inference_binding,
)
from .epistemic_graph import evaluate_epistemic_graph, validate_epistemic_graph
from .epistemic_transition import (
    TRANSITION_POLICY_VERSION,
    TRANSITION_SCHEMA_VERSION,
    VERIFICATION_SCHEMA_VERSION as LEGACY_VERIFICATION_SCHEMA_VERSION,
    EpistemicTransitionError,
    _assessment_for,
    _canonical_json_bytes,
    _read_json_snapshot,
    validate_transition_proposal,
    validate_verification_decision,
)

AUTHENTICATED_TRANSITION_POLICY_VERSION = "1.4"
AUTHENTICATED_TRANSITION_LINEAGE_SCHEMA_VERSION = "1.0"
AUTHENTICATED_VERIFICATION_ARTIFACT_ROLE = "authenticated_domain_verification_decision"


class AuthenticatedEpistemicTransitionError(EpistemicTransitionError):
    """Raised when authenticated transition production cannot preserve provenance."""


def _legacy_scope_decision(value: Mapping[str, Any]) -> dict[str, Any]:
    """Project v1.1 identity into the legacy scientific-scope validator."""
    legacy = dict(value)
    legacy.pop("inference_edge_id", None)
    legacy["schema_version"] = LEGACY_VERIFICATION_SCHEMA_VERSION
    return legacy


def _target_assessment(result: Mapping[str, Any], node_id: str) -> dict[str, Any]:
    assessment = _assessment_for(result, node_id)
    if assessment is None:
        raise AuthenticatedEpistemicTransitionError(
            "target assessment could not be reconstructed"
        )
    return assessment


def _verified_directional_edge_ids(assessment: Mapping[str, Any]) -> set[str]:
    result: set[str] = set()
    for field in (
        "verified_support_edges",
        "verified_contradiction_edges",
        "verified_falsification_edges",
    ):
        values = assessment.get(field)
        if not isinstance(values, list):
            raise AuthenticatedEpistemicTransitionError(
                f"target assessment {field} must be a list"
            )
        for value in values:
            if not isinstance(value, str) or not value:
                raise AuthenticatedEpistemicTransitionError(
                    f"target assessment {field} must contain non-empty edge IDs"
                )
            result.add(value)
    return result


def _snapshot_binding(
    *,
    source: Path,
    snapshot: Path,
    sha256: str,
) -> dict[str, Any]:
    return {
        "path": str(snapshot),
        "source_path": str(source),
        "source_path_authoritative": False,
        "sha256": sha256,
    }


def _lineage_records(
    metadata: Mapping[str, Any], *, field: str
) -> list[Mapping[str, Any]]:
    raw = metadata.get(field, [])
    if not isinstance(raw, list):
        raise AuthenticatedEpistemicTransitionError(
            f"base graph metadata.{field} must be a list"
        )
    result: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise AuthenticatedEpistemicTransitionError(
                f"base graph metadata.{field}[{index}] must be an object"
            )
        raw_transition_id = item.get("transition_id")
        if not isinstance(raw_transition_id, str) or not raw_transition_id.strip():
            raise AuthenticatedEpistemicTransitionError(
                f"base graph metadata.{field}[{index}].transition_id must be non-empty text"
            )
        transition_id = raw_transition_id.strip()
        if transition_id in seen:
            raise AuthenticatedEpistemicTransitionError(
                f"base graph metadata.{field} contains duplicate transition_id: {transition_id}"
            )
        seen.add(transition_id)
        result.append(item)
    return result


def _reject_transition_id_reuse(
    metadata: Mapping[str, Any], *, transition_id: str
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    legacy = _lineage_records(metadata, field="transition_lineage")
    authenticated = _lineage_records(
        metadata, field="authenticated_transition_lineage"
    )
    if any(str(item.get("transition_id")).strip() == transition_id for item in legacy):
        raise AuthenticatedEpistemicTransitionError(
            f"transition_id already exists in base transition_lineage: {transition_id}"
        )
    if any(
        str(item.get("transition_id")).strip() == transition_id
        for item in authenticated
    ):
        raise AuthenticatedEpistemicTransitionError(
            f"transition_id already exists in base authenticated_transition_lineage: {transition_id}"
        )
    return legacy, authenticated


def _safe_result_suffix(path: Path) -> str:
    suffix = path.suffix.lower()
    if (
        suffix.startswith(".")
        and len(suffix) <= 16
        and suffix[1:]
        and suffix[1:].isalnum()
    ):
        return suffix
    return ""


def _prepare_result_artifact_snapshots(
    proposal: Mapping[str, Any], *, result_dir: Path
) -> tuple[list[dict[str, str]], list[dict[str, Any]], list[tuple[Path, bytes]]]:
    raw_result = proposal.get("result_node")
    if not isinstance(raw_result, Mapping):
        raise AuthenticatedEpistemicTransitionError(
            "validated proposal result_node is malformed"
        )
    raw_bindings = raw_result.get("artifact_bindings")
    if not isinstance(raw_bindings, list) or not raw_bindings:
        raise AuthenticatedEpistemicTransitionError(
            "validated proposal result artifact bindings are malformed"
        )

    graph_bindings: list[dict[str, str]] = []
    provenance: list[dict[str, Any]] = []
    payloads: list[tuple[Path, bytes]] = []
    for index, raw in enumerate(raw_bindings):
        if not isinstance(raw, Mapping):
            raise AuthenticatedEpistemicTransitionError(
                f"validated result artifact binding[{index}] must be an object"
            )
        role = raw.get("role")
        path_value = raw.get("path")
        expected_sha = raw.get("sha256")
        if not isinstance(role, str) or not role:
            raise AuthenticatedEpistemicTransitionError(
                f"validated result artifact binding[{index}].role is malformed"
            )
        if not isinstance(path_value, str) or not path_value:
            raise AuthenticatedEpistemicTransitionError(
                f"validated result artifact binding[{index}].path is malformed"
            )
        if not isinstance(expected_sha, str) or not expected_sha:
            raise AuthenticatedEpistemicTransitionError(
                f"validated result artifact binding[{index}].sha256 is malformed"
            )
        try:
            source = Path(path_value).expanduser().resolve(strict=True)
            data = source.read_bytes()
        except OSError as exc:
            raise AuthenticatedEpistemicTransitionError(
                f"result artifact became unreadable after proposal validation: {role}"
            ) from exc
        actual_sha = hashlib.sha256(data).hexdigest()
        if actual_sha != expected_sha:
            raise AuthenticatedEpistemicTransitionError(
                "result artifact changed after transition proposal validation: "
                f"{role}; expected {expected_sha}, got {actual_sha}"
            )
        snapshot = result_dir / f"result-{index:03d}{_safe_result_suffix(source)}"
        graph_bindings.append(
            {"role": role, "path": str(snapshot), "sha256": actual_sha}
        )
        provenance.append(
            {
                "role": role,
                "path": str(snapshot),
                "source_path": str(source),
                "source_path_authoritative": False,
                "sha256": actual_sha,
                "size_bytes": len(data),
            }
        )
        payloads.append((snapshot, data))
    return graph_bindings, provenance, payloads


def _proposal_result_and_edges(
    proposal: Mapping[str, Any],
    *,
    verifier_snapshot: Path,
    verification_sha256: str,
    result_artifact_bindings: list[dict[str, str]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    inference = proposal.get("proposed_inference")
    if not isinstance(inference, Mapping):
        raise AuthenticatedEpistemicTransitionError(
            "validated proposal proposed_inference is malformed"
        )
    raw_result = proposal.get("result_node")
    if not isinstance(raw_result, Mapping):
        raise AuthenticatedEpistemicTransitionError(
            "validated proposal result_node is malformed"
        )
    source_action = proposal.get("source_action")
    input_evidence = proposal.get("input_evidence_bindings")
    limitations = proposal.get("limitations")
    if not isinstance(source_action, Mapping):
        raise AuthenticatedEpistemicTransitionError(
            "validated proposal source_action is malformed"
        )
    if not isinstance(input_evidence, list) or not isinstance(limitations, list):
        raise AuthenticatedEpistemicTransitionError(
            "validated proposal evidence/limitations are malformed"
        )

    result_node = dict(raw_result)
    result_node["artifact_bindings"] = [dict(item) for item in result_artifact_bindings]
    result_metadata = dict(result_node.get("metadata", {}))
    result_metadata["source_action"] = dict(source_action)
    result_metadata["input_evidence_bindings"] = list(input_evidence)
    result_metadata["transition_id"] = proposal["transition_id"]
    result_metadata["limitations"] = list(limitations)
    result_node["metadata"] = result_metadata

    tests_edge = {
        "edge_id": inference["tests_edge_id"],
        "source_node_id": result_node["node_id"],
        "target_node_id": proposal["target_node_id"],
        "relation": "tests",
        "assessment_level": "proposal",
        "rationale": (
            "The completed result was introduced to test this target; execution success alone "
            "does not establish scientific support, contradiction, or falsification."
        ),
        "active": True,
    }
    inference_edge = {
        "edge_id": inference["inference_edge_id"],
        "source_node_id": result_node["node_id"],
        "target_node_id": proposal["target_node_id"],
        "relation": inference["relation"],
        "assessment_level": "domain_verified",
        "rationale": inference["rationale"],
        "active": True,
        "verification_artifact": {
            "role": AUTHENTICATED_VERIFICATION_ARTIFACT_ROLE,
            "path": str(verifier_snapshot),
            "sha256": verification_sha256,
        },
    }
    return result_node, tests_edge, inference_edge


def apply_authenticated_epistemic_transition_files(
    *,
    base_graph_path: str | Path,
    proposal_path: str | Path,
    verification_decision_path: str | Path,
    program_state: Mapping[str, Any],
    artifact_root: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Create a successor graph with re-checkable exact-edge authentication."""
    base_path = Path(base_graph_path).expanduser().resolve(strict=True)
    proposal_file = Path(proposal_path).expanduser().resolve(strict=True)
    verification_file = Path(verification_decision_path).expanduser().resolve(strict=True)
    artifacts = Path(artifact_root).expanduser().resolve(strict=True)
    output = Path(output_dir).expanduser().resolve()
    if output.exists():
        raise AuthenticatedEpistemicTransitionError(
            f"output_dir must not already exist: {output}"
        )
    if not artifacts.is_dir():
        raise AuthenticatedEpistemicTransitionError(
            f"artifact_root must be a directory: {artifacts}"
        )

    base_raw, base_bytes, base_sha = _read_json_snapshot(base_path)
    proposal_raw, proposal_bytes, proposal_sha = _read_json_snapshot(proposal_file)
    verification_raw, verification_bytes, verification_sha = _read_json_snapshot(
        verification_file
    )
    if verification_raw.get("schema_version") != DOMAIN_VERIFICATION_DECISION_SCHEMA_VERSION:
        raise AuthenticatedEpistemicTransitionError(
            "authenticated transition requires verification decision schema v1.1"
        )

    try:
        authenticated_binding = authenticate_inference_binding(
            proposal_bytes=proposal_bytes,
            verification_decision_bytes=verification_bytes,
            expected_base_graph_sha256=base_sha,
        )
    except AuthenticatedInferenceBindingError as exc:
        raise AuthenticatedEpistemicTransitionError(str(exc)) from exc

    base_validated = validate_epistemic_graph(
        base_raw,
        program_state=program_state,
        artifact_root=artifacts,
    )
    before_eval = evaluate_epistemic_graph(
        base_raw,
        program_state=program_state,
        artifact_root=artifacts,
    )
    proposal = validate_transition_proposal(
        proposal_raw,
        base_graph=base_validated,
        base_graph_sha256=base_sha,
        program_state=program_state,
        artifact_root=artifacts,
    )
    if authenticated_binding["transition_id"] != proposal["transition_id"]:
        raise AuthenticatedEpistemicTransitionError(
            "authenticated verifier transition_id does not match validated proposal"
        )

    scope_validation = validate_verification_decision(
        _legacy_scope_decision(verification_raw),
        proposal=proposal,
        proposal_sha256=proposal_sha,
        verification_sha256=verification_sha,
    )
    if scope_validation["inference_scope"] != authenticated_binding["inference_scope"]:
        raise AuthenticatedEpistemicTransitionError(
            "authenticated verifier scope diverged from transition scope validation"
        )

    metadata = dict(base_raw.get("metadata", {}))
    transition_id = str(proposal["transition_id"])
    legacy_lineage, authenticated_lineage = _reject_transition_id_reuse(
        metadata, transition_id=transition_id
    )

    provenance_dir = output / "provenance"
    result_dir = provenance_dir / "result_artifacts"
    base_snapshot = provenance_dir / "base_graph.json"
    proposal_snapshot = provenance_dir / "proposal.json"
    verification_snapshot = provenance_dir / "verification_decision.json"
    base_binding = _snapshot_binding(
        source=base_path, snapshot=base_snapshot, sha256=base_sha
    )
    proposal_binding = _snapshot_binding(
        source=proposal_file, snapshot=proposal_snapshot, sha256=proposal_sha
    )
    verification_binding = _snapshot_binding(
        source=verification_file,
        snapshot=verification_snapshot,
        sha256=verification_sha,
    )
    (
        result_artifact_bindings,
        result_artifact_provenance,
        result_artifact_payloads,
    ) = _prepare_result_artifact_snapshots(proposal, result_dir=result_dir)

    result_node, tests_edge, inference_edge = _proposal_result_and_edges(
        proposal,
        verifier_snapshot=verification_snapshot,
        verification_sha256=verification_sha,
        result_artifact_bindings=result_artifact_bindings,
    )
    edge_id = str(authenticated_binding["inference_edge_id"])
    if inference_edge["edge_id"] != edge_id:
        raise AuthenticatedEpistemicTransitionError(
            "constructed inference edge does not match authenticated inference edge ID"
        )

    metadata["transition_lineage"] = [
        *legacy_lineage,
        {
            "transition_id": transition_id,
            "parent_graph_id": base_validated["graph_id"],
            "parent_graph_sha256": base_sha,
            "proposal_sha256": proposal_sha,
            "verification_decision_sha256": verification_sha,
            "result_node_id": result_node["node_id"],
        },
    ]
    metadata["authenticated_transition_lineage"] = [
        *authenticated_lineage,
        {
            "schema_version": AUTHENTICATED_TRANSITION_LINEAGE_SCHEMA_VERSION,
            "transition_id": transition_id,
            "base_graph_artifact": base_binding,
            "proposal_artifact": proposal_binding,
            "verification_decision_artifact": verification_binding,
            "result_artifact_snapshots": result_artifact_provenance,
            "authenticated_inference_binding": dict(authenticated_binding),
        },
    ]

    successor = {
        "schema_version": base_raw["schema_version"],
        "graph_id": proposal["new_graph_id"],
        "research_scope": base_raw["research_scope"],
        "nodes": [*base_raw["nodes"], result_node],
        "edges": [*base_raw["edges"], tests_edge, inference_edge],
        "metadata": metadata,
    }
    before_target = _target_assessment(before_eval, str(proposal["target_node_id"]))

    output_created = False
    try:
        output.mkdir(parents=True, exist_ok=False)
        output_created = True
        provenance_dir.mkdir(parents=False, exist_ok=False)
        result_dir.mkdir(parents=False, exist_ok=False)
        base_snapshot.write_bytes(base_bytes)
        proposal_snapshot.write_bytes(proposal_bytes)
        verification_snapshot.write_bytes(verification_bytes)
        for snapshot, data in result_artifact_payloads:
            snapshot.write_bytes(data)

        after_eval = evaluate_epistemic_graph(
            successor,
            program_state=program_state,
            artifact_root=artifacts,
        )
        target_id = str(proposal["target_node_id"])
        target_after = _target_assessment(after_eval, target_id)
        if edge_id not in _verified_directional_edge_ids(target_after):
            raise AuthenticatedEpistemicTransitionError(
                "authenticated inference edge did not become a usable verified relation"
            )

        graph_bytes = _canonical_json_bytes(successor)
        graph_sha = hashlib.sha256(graph_bytes).hexdigest()
        manifest = {
            "schema_version": TRANSITION_SCHEMA_VERSION,
            "transition_policy_version": TRANSITION_POLICY_VERSION,
            "authenticated_transition_policy_version": AUTHENTICATED_TRANSITION_POLICY_VERSION,
            "transition_id": transition_id,
            "base_graph_binding": base_binding,
            "proposal_binding": proposal_binding,
            "verification_decision_binding": verification_binding,
            "authenticated_inference_binding": dict(authenticated_binding),
            "result_artifact_bindings": result_artifact_bindings,
            "result_artifact_provenance": result_artifact_provenance,
            "successor_graph": {
                "graph_id": successor["graph_id"],
                "path": str(output / "epistemic_graph.json"),
                "sha256": graph_sha,
            },
            "target_node_id": target_id,
            "target_before": before_target,
            "target_after": target_after,
            "inference_assessment_level": "domain_verified",
            "domain_verification_applied": True,
            "verification": {
                **scope_validation,
                "schema_version": DOMAIN_VERIFICATION_DECISION_SCHEMA_VERSION,
                "inference_edge_id": edge_id,
                "verification_sha256": verification_sha,
            },
            "autonomy_boundary": {
                "action_execution_performed": False,
                "network_access_performed": False,
                "physical_experiment_execution_performed": False,
                "base_graph_mutated": False,
                "result_execution_success_treated_as_scientific_verification": False,
                "simulation_may_directly_verify_empirical_claim": False,
                "positive_support_grants_final_truth": False,
                "exact_inference_edge_identity_authenticated": True,
                "transition_id_reuse_allowed": False,
                "duplicate_transition_lineage_allowed": False,
                "source_file_toctou_changes_transition_bytes": False,
                "provenance_snapshots_self_contained": True,
                "result_artifact_snapshots_self_contained": True,
                "result_artifact_source_drift_changes_published_evidence": False,
                "temporary_transition_staging_used": False,
                "opaque_graph_metadata_used_as_authority": False,
                "legacy_v10_verifier_used_as_authenticated_authority": False,
                "authenticated_v11_verifier_consumed_by_legacy_critic": False,
                "verifier_identity_or_credential_authenticated": False,
                "execution_authorized_by_authentication": False,
                "positive_closeout_granted_by_authentication": False,
            },
        }
        manifest_bytes = _canonical_json_bytes(manifest)
        (output / "epistemic_graph.json").write_bytes(graph_bytes)
        (output / "epistemic_transition_manifest.json").write_bytes(manifest_bytes)
    except Exception:
        if output_created:
            shutil.rmtree(output, ignore_errors=True)
        raise

    return {
        **manifest,
        "successor_graph_evaluation": after_eval,
    }


__all__ = [
    "AUTHENTICATED_TRANSITION_LINEAGE_SCHEMA_VERSION",
    "AUTHENTICATED_TRANSITION_POLICY_VERSION",
    "AUTHENTICATED_VERIFICATION_ARTIFACT_ROLE",
    "AuthenticatedEpistemicTransitionError",
    "apply_authenticated_epistemic_transition_files",
]
