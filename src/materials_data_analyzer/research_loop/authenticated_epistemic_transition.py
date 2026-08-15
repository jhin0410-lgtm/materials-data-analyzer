"""Authenticated successor-graph production for exact directional inference identity.

This is an additive hardened producer above the legacy transition-v1 path. It requires a
v1.1 domain-verification decision that binds the exact inference edge ID and preserves
both the proposal and verifier artifacts in graph provenance so downstream consumers can
independently re-authenticate the same bytes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .authenticated_inference_binding import (
    DOMAIN_VERIFICATION_DECISION_SCHEMA_VERSION,
    AuthenticatedInferenceBindingError,
    authenticate_inference_binding,
)
from .epistemic_graph import evaluate_epistemic_graph, validate_epistemic_graph
from .epistemic_transition import (
    VERIFICATION_SCHEMA_VERSION as LEGACY_VERIFICATION_SCHEMA_VERSION,
    EpistemicTransitionError,
    _assessment_for,
    _canonical_json_bytes,
    _read_json_snapshot,
    apply_epistemic_transition_files,
    validate_transition_proposal,
    validate_verification_decision,
)

AUTHENTICATED_TRANSITION_POLICY_VERSION = "1.0"
AUTHENTICATED_TRANSITION_LINEAGE_SCHEMA_VERSION = "1.0"


class AuthenticatedEpistemicTransitionError(EpistemicTransitionError):
    """Raised when authenticated transition production cannot preserve provenance."""


def _legacy_scope_decision(value: Mapping[str, Any]) -> dict[str, Any]:
    """Project v1.1 identity into the legacy scope validator without changing bytes."""
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


def _find_exact_edge(
    graph: Mapping[str, Any], *, edge_id: str
) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    raw_edges = graph.get("edges")
    if not isinstance(raw_edges, list):
        raise AuthenticatedEpistemicTransitionError("staged graph edges must be a list")
    normalized: list[dict[str, Any]] = []
    match_index: int | None = None
    match: dict[str, Any] | None = None
    for index, raw in enumerate(raw_edges):
        if not isinstance(raw, Mapping):
            raise AuthenticatedEpistemicTransitionError(
                f"staged graph edge[{index}] must be an object"
            )
        edge = dict(raw)
        normalized.append(edge)
        if edge.get("edge_id") == edge_id:
            if match is not None:
                raise AuthenticatedEpistemicTransitionError(
                    f"duplicate staged inference edge ID: {edge_id}"
                )
            match_index = index
            match = edge
    if match_index is None or match is None:
        raise AuthenticatedEpistemicTransitionError(
            f"authenticated inference edge is absent from staged graph: {edge_id}"
        )
    return normalized, match_index, match


def apply_authenticated_epistemic_transition_files(
    *,
    base_graph_path: str | Path,
    proposal_path: str | Path,
    verification_decision_path: str | Path,
    program_state: Mapping[str, Any],
    artifact_root: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Create a successor graph carrying re-checkable exact-edge authentication.

    The legacy transition engine is used only to stage the already-validated append-only
    result/test structure without directional verification. The final directional upgrade
    is then applied to the exact authenticated edge and bound to the original v1.1
    proposal/verifier artifacts. No staging path is exposed as scientific provenance.
    """
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

    base_raw, _, base_sha = _read_json_snapshot(base_path)
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

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="mda-auth-transition-", dir=str(output.parent)
    ) as staging_root:
        staged_output = Path(staging_root) / "staged"
        staged = apply_epistemic_transition_files(
            base_graph_path=base_path,
            proposal_path=proposal_file,
            program_state=program_state,
            artifact_root=artifacts,
            output_dir=staged_output,
            verification_decision_path=None,
        )
        staged_graph_path = staged_output / "epistemic_graph.json"
        staged_graph, _, _ = _read_json_snapshot(staged_graph_path)

        edge_id = str(authenticated_binding["inference_edge_id"])
        edges, edge_index, inference_edge = _find_exact_edge(
            staged_graph, edge_id=edge_id
        )
        expected_edge = {
            "source_node_id": authenticated_binding["result_node_id"],
            "target_node_id": authenticated_binding["target_node_id"],
            "relation": authenticated_binding["relation"],
        }
        for field, expected in expected_edge.items():
            if inference_edge.get(field) != expected:
                raise AuthenticatedEpistemicTransitionError(
                    f"staged inference edge {field} does not match authenticated binding"
                )
        if inference_edge.get("assessment_level") != "proposal":
            raise AuthenticatedEpistemicTransitionError(
                "staged inference edge must remain proposal-level before authenticated upgrade"
            )

        inference_edge["assessment_level"] = "domain_verified"
        inference_edge["verification_artifact"] = {
            "role": "domain_verification_decision",
            "path": str(verification_file),
            "sha256": verification_sha,
        }
        edges[edge_index] = inference_edge

        metadata = dict(staged_graph.get("metadata", {}))
        authenticated_lineage = metadata.get("authenticated_transition_lineage", [])
        if not isinstance(authenticated_lineage, list):
            raise AuthenticatedEpistemicTransitionError(
                "graph metadata.authenticated_transition_lineage must be a list"
            )
        lineage_record = {
            "schema_version": AUTHENTICATED_TRANSITION_LINEAGE_SCHEMA_VERSION,
            "transition_id": proposal["transition_id"],
            "proposal_artifact": {
                "path": str(proposal_file),
                "sha256": proposal_sha,
            },
            "verification_decision_artifact": {
                "path": str(verification_file),
                "sha256": verification_sha,
            },
            "authenticated_inference_binding": dict(authenticated_binding),
        }
        metadata["authenticated_transition_lineage"] = [
            *authenticated_lineage,
            lineage_record,
        ]

        successor = {
            **staged_graph,
            "edges": edges,
            "metadata": metadata,
        }
        after_eval = evaluate_epistemic_graph(
            successor,
            program_state=program_state,
            artifact_root=artifacts,
        )
        target_id = str(proposal["target_node_id"])
        target_after = _target_assessment(after_eval, target_id)
        if edge_id not in {
            *target_after.get("verified_support_edges", []),
            *target_after.get("verified_contradiction_edges", []),
            *target_after.get("verified_falsification_edges", []),
        }:
            raise AuthenticatedEpistemicTransitionError(
                "authenticated inference edge did not become a usable verified relation"
            )

        graph_bytes = _canonical_json_bytes(successor)
        graph_sha = __import__("hashlib").sha256(graph_bytes).hexdigest()
        manifest = {
            **{
                key: value
                for key, value in staged.items()
                if key != "successor_graph_evaluation"
            },
            "authenticated_transition_policy_version": AUTHENTICATED_TRANSITION_POLICY_VERSION,
            "proposal_binding": {"path": str(proposal_file), "sha256": proposal_sha},
            "verification_decision_binding": {
                "path": str(verification_file),
                "sha256": verification_sha,
            },
            "authenticated_inference_binding": dict(authenticated_binding),
            "successor_graph": {
                "graph_id": successor["graph_id"],
                "path": str(output / "epistemic_graph.json"),
                "sha256": graph_sha,
            },
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
                **dict(staged.get("autonomy_boundary", {})),
                "exact_inference_edge_identity_authenticated": True,
                "opaque_graph_metadata_used_as_authority": False,
                "legacy_v10_verifier_used_as_authenticated_authority": False,
                "execution_authorized_by_authentication": False,
                "positive_closeout_granted_by_authentication": False,
            },
        }
        manifest_bytes = _canonical_json_bytes(manifest)

        output.mkdir(parents=True, exist_ok=False)
        (output / "epistemic_graph.json").write_bytes(graph_bytes)
        (output / "epistemic_transition_manifest.json").write_bytes(manifest_bytes)

    return {
        **manifest,
        "successor_graph_evaluation": after_eval,
    }


__all__ = [
    "AUTHENTICATED_TRANSITION_LINEAGE_SCHEMA_VERSION",
    "AUTHENTICATED_TRANSITION_POLICY_VERSION",
    "AuthenticatedEpistemicTransitionError",
    "apply_authenticated_epistemic_transition_files",
]
