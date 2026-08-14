"""Provenance-aware epistemic graph for autonomous materials research.

The graph is deliberately asymmetric about positive conclusions: verified support can
make a hypothesis or claim *provisionally supported*, but never silently upgrades it
to final scientific truth. Contradiction and falsification are first-class relations.
A relation may affect derived scientific status only when it is marked
``domain_verified`` and is bound to an exact verifier artifact.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
from pathlib import Path
from typing import Any, Mapping

from .kernel import ResearchLoopError

GRAPH_SCHEMA_VERSION = "1.0"
GRAPH_POLICY_VERSION = "1.0"

_NODE_TYPES = {
    "research_question",
    "hypothesis",
    "evidence",
    "analysis",
    "simulation",
    "experiment",
    "claim",
    "conclusion",
}
_RELATIONS = {
    "motivates",
    "tests",
    "supports",
    "contradicts",
    "falsifies",
    "depends_on",
    "produced_by",
    "addresses",
}
_ASSESSMENT_LEVELS = {"proposal", "diagnostic", "domain_verified"}
_EVIDENCE_QUALITY = {"supported", "diagnostic", "inconclusive", "unsupported"}
_EXECUTION_STATUSES = {"planned", "completed", "failed"}
_INFERENCE_TARGET_TYPES = {"hypothesis", "claim", "conclusion"}
_INFERENCE_SOURCE_TYPES = {"evidence", "analysis", "simulation", "experiment"}
_EXECUTABLE_NODE_TYPES = {"analysis", "simulation", "experiment"}


class EpistemicGraphError(ResearchLoopError):
    """Raised when an epistemic graph violates provenance or inference contracts."""


def _nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EpistemicGraphError(f"{field} must be a non-empty string")
    return value.strip()


def _exact_object(
    value: object,
    *,
    required: set[str],
    allowed: set[str],
    field: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EpistemicGraphError(f"{field} must be an object")
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - allowed)
    if missing:
        raise EpistemicGraphError(f"{field} is missing required keys: {', '.join(missing)}")
    if unknown:
        raise EpistemicGraphError(f"{field} has unknown keys: {', '.join(unknown)}")
    return value


def _enum(value: object, allowed: set[str], field: str) -> str:
    text = _nonempty_text(value, field)
    if text not in allowed:
        raise EpistemicGraphError(f"{field} must be one of: {', '.join(sorted(allowed))}")
    return text


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _known_program_evidence(program_state: Mapping[str, Any]) -> set[tuple[str, str, str]]:
    workstreams = program_state.get("workstreams")
    if not isinstance(workstreams, list):
        raise EpistemicGraphError("program_state.workstreams must be a list")
    known: set[tuple[str, str, str]] = set()
    for workstream in workstreams:
        if not isinstance(workstream, Mapping):
            continue
        workstream_id = workstream.get("workstream_id")
        planning_state = workstream.get("planning_state")
        if not isinstance(workstream_id, str) or not isinstance(planning_state, Mapping):
            continue
        bindings = planning_state.get("evidence_bindings")
        if not isinstance(bindings, list):
            continue
        for binding in bindings:
            if not isinstance(binding, Mapping):
                continue
            role = binding.get("role")
            sha256 = binding.get("sha256")
            if isinstance(role, str) and isinstance(sha256, str):
                known.add((workstream_id, role, sha256))
    return known


def _validate_program_evidence_binding(
    value: object,
    *,
    known: set[tuple[str, str, str]],
    field: str,
) -> dict[str, str]:
    item = _exact_object(
        value,
        required={"workstream_id", "role", "sha256"},
        allowed={"workstream_id", "role", "sha256"},
        field=field,
    )
    binding = {
        "workstream_id": _nonempty_text(item["workstream_id"], f"{field}.workstream_id"),
        "role": _nonempty_text(item["role"], f"{field}.role"),
        "sha256": _nonempty_text(item["sha256"], f"{field}.sha256"),
    }
    if (binding["workstream_id"], binding["role"], binding["sha256"]) not in known:
        raise EpistemicGraphError(
            f"{field} is not present in the verified mission program state"
        )
    return binding


def _resolve_artifact(path_value: object, artifact_root: Path, field: str) -> Path:
    text = _nonempty_text(path_value, field)
    candidate = Path(text).expanduser()
    if not candidate.is_absolute():
        candidate = artifact_root / candidate
    resolved = candidate.resolve(strict=True)
    if not resolved.is_file():
        raise EpistemicGraphError(f"{field} must resolve to a regular file: {resolved}")
    return resolved


def _validate_artifact_binding(
    value: object,
    *,
    artifact_root: Path,
    field: str,
) -> dict[str, Any]:
    item = _exact_object(
        value,
        required={"role", "path", "sha256"},
        allowed={"role", "path", "sha256"},
        field=field,
    )
    role = _nonempty_text(item["role"], f"{field}.role")
    path = _resolve_artifact(item["path"], artifact_root, f"{field}.path")
    expected_sha = _nonempty_text(item["sha256"], f"{field}.sha256")
    actual_sha = _sha256_file(path)
    if actual_sha != expected_sha:
        raise EpistemicGraphError(
            f"{field} checksum mismatch: expected {expected_sha}, got {actual_sha}"
        )
    return {
        "role": role,
        "path": str(path),
        "sha256": actual_sha,
        "bytes": path.stat().st_size,
    }


def _validate_failed_action_report_snapshot(value: object, *, field: str) -> dict[str, Any]:
    """Validate self-contained failed-result bytes without making them evidence artifacts."""
    item = _exact_object(
        value,
        required={"encoding", "sha256", "size_bytes", "data"},
        allowed={"encoding", "sha256", "size_bytes", "data"},
        field=field,
    )
    if item["encoding"] != "base64":
        raise EpistemicGraphError(f"{field}.encoding must be 'base64'")
    digest = _nonempty_text(item["sha256"], f"{field}.sha256")
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise EpistemicGraphError(f"{field}.sha256 must be a lowercase SHA-256 hex digest")
    size = item["size_bytes"]
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise EpistemicGraphError(f"{field}.size_bytes must be a non-negative integer")
    data_text = _nonempty_text(item["data"], f"{field}.data")
    try:
        raw = base64.b64decode(data_text, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise EpistemicGraphError(f"{field}.data must be valid base64") from exc
    if len(raw) != size:
        raise EpistemicGraphError(
            f"{field} byte count mismatch: expected {size}, got {len(raw)}"
        )
    actual = hashlib.sha256(raw).hexdigest()
    if actual != digest:
        raise EpistemicGraphError(
            f"{field} checksum mismatch: expected {digest}, got {actual}"
        )
    return {
        "encoding": "base64",
        "sha256": digest,
        "size_bytes": size,
        "data": data_text,
    }


def _validate_node(
    value: object,
    *,
    index: int,
    known_evidence: set[tuple[str, str, str]],
    artifact_root: Path,
) -> dict[str, Any]:
    field = f"nodes[{index}]"
    node = _exact_object(
        value,
        required={"node_id", "node_type", "statement"},
        allowed={
            "node_id",
            "node_type",
            "statement",
            "evidence_binding",
            "evidence_quality",
            "execution_status",
            "artifact_bindings",
            "metadata",
        },
        field=field,
    )
    node_id = _nonempty_text(node["node_id"], f"{field}.node_id")
    node_type = _enum(node["node_type"], _NODE_TYPES, f"{field}.node_type")
    normalized: dict[str, Any] = {
        "node_id": node_id,
        "node_type": node_type,
        "statement": _nonempty_text(node["statement"], f"{field}.statement"),
    }

    if node_type == "evidence":
        if "evidence_binding" not in node or "evidence_quality" not in node:
            raise EpistemicGraphError(
                f"{field} evidence nodes require evidence_binding and evidence_quality"
            )
        normalized["evidence_binding"] = _validate_program_evidence_binding(
            node["evidence_binding"], known=known_evidence, field=f"{field}.evidence_binding"
        )
        normalized["evidence_quality"] = _enum(
            node["evidence_quality"], _EVIDENCE_QUALITY, f"{field}.evidence_quality"
        )
    elif "evidence_binding" in node or "evidence_quality" in node:
        raise EpistemicGraphError(
            f"{field} evidence_binding/evidence_quality are valid only for evidence nodes"
        )

    if node_type in _EXECUTABLE_NODE_TYPES:
        if "execution_status" not in node:
            raise EpistemicGraphError(f"{field} requires execution_status")
        execution_status = _enum(
            node["execution_status"], _EXECUTION_STATUSES, f"{field}.execution_status"
        )
        raw_artifacts = node.get("artifact_bindings", [])
        if not isinstance(raw_artifacts, list):
            raise EpistemicGraphError(f"{field}.artifact_bindings must be a list")
        artifacts = [
            _validate_artifact_binding(
                item,
                artifact_root=artifact_root,
                field=f"{field}.artifact_bindings[{artifact_index}]",
            )
            for artifact_index, item in enumerate(raw_artifacts)
        ]
        if execution_status == "completed" and not artifacts:
            raise EpistemicGraphError(
                f"{field} completed computational/experimental nodes require artifact_bindings"
            )
        if execution_status != "completed" and artifacts:
            raise EpistemicGraphError(
                f"{field} may bind result artifacts only after execution_status=completed"
            )
        normalized["execution_status"] = execution_status
        normalized["artifact_bindings"] = artifacts
    elif "execution_status" in node or "artifact_bindings" in node:
        raise EpistemicGraphError(
            f"{field} execution_status/artifact_bindings are valid only for analysis, simulation, or experiment nodes"
        )

    if "metadata" in node:
        if not isinstance(node["metadata"], dict):
            raise EpistemicGraphError(f"{field}.metadata must be an object")
        metadata = dict(node["metadata"])
        failed_snapshot = metadata.get("failed_action_report_snapshot")
        if failed_snapshot is not None:
            if node_type not in _EXECUTABLE_NODE_TYPES or normalized.get("execution_status") != "failed":
                raise EpistemicGraphError(
                    f"{field}.metadata.failed_action_report_snapshot is valid only for failed executable nodes"
                )
            metadata["failed_action_report_snapshot"] = _validate_failed_action_report_snapshot(
                failed_snapshot,
                field=f"{field}.metadata.failed_action_report_snapshot",
            )
        normalized["metadata"] = metadata
    return normalized


def _validate_edge(
    value: object,
    *,
    index: int,
    nodes_by_id: Mapping[str, Mapping[str, Any]],
    artifact_root: Path,
) -> dict[str, Any]:
    field = f"edges[{index}]"
    edge = _exact_object(
        value,
        required={
            "edge_id",
            "source_node_id",
            "target_node_id",
            "relation",
            "assessment_level",
            "rationale",
            "active",
        },
        allowed={
            "edge_id",
            "source_node_id",
            "target_node_id",
            "relation",
            "assessment_level",
            "rationale",
            "active",
            "verification_artifact",
        },
        field=field,
    )
    source_id = _nonempty_text(edge["source_node_id"], f"{field}.source_node_id")
    target_id = _nonempty_text(edge["target_node_id"], f"{field}.target_node_id")
    if source_id == target_id:
        raise EpistemicGraphError(f"{field} self-edges are not allowed")
    if source_id not in nodes_by_id:
        raise EpistemicGraphError(f"{field} references unknown source node: {source_id}")
    if target_id not in nodes_by_id:
        raise EpistemicGraphError(f"{field} references unknown target node: {target_id}")
    relation = _enum(edge["relation"], _RELATIONS, f"{field}.relation")
    assessment_level = _enum(
        edge["assessment_level"], _ASSESSMENT_LEVELS, f"{field}.assessment_level"
    )
    active = edge["active"]
    if not isinstance(active, bool):
        raise EpistemicGraphError(f"{field}.active must be boolean")

    source_type = nodes_by_id[source_id]["node_type"]
    target_type = nodes_by_id[target_id]["node_type"]
    if relation in {"supports", "contradicts", "falsifies"}:
        if source_type not in _INFERENCE_SOURCE_TYPES:
            raise EpistemicGraphError(
                f"{field} {relation} source must be evidence, analysis, simulation, or experiment"
            )
        if target_type not in _INFERENCE_TARGET_TYPES:
            raise EpistemicGraphError(
                f"{field} {relation} target must be hypothesis, claim, or conclusion"
            )
    if relation == "tests" and source_type not in _EXECUTABLE_NODE_TYPES:
        raise EpistemicGraphError(f"{field} tests source must be analysis, simulation, or experiment")

    verification_artifact = None
    if assessment_level == "domain_verified":
        if "verification_artifact" not in edge:
            raise EpistemicGraphError(
                f"{field} domain_verified relations require verification_artifact"
            )
        verification_artifact = _validate_artifact_binding(
            edge["verification_artifact"],
            artifact_root=artifact_root,
            field=f"{field}.verification_artifact",
        )
    elif "verification_artifact" in edge:
        raise EpistemicGraphError(
            f"{field} verification_artifact is allowed only for domain_verified relations"
        )

    return {
        "edge_id": _nonempty_text(edge["edge_id"], f"{field}.edge_id"),
        "source_node_id": source_id,
        "target_node_id": target_id,
        "relation": relation,
        "assessment_level": assessment_level,
        "rationale": _nonempty_text(edge["rationale"], f"{field}.rationale"),
        "active": active,
        "verification_artifact": verification_artifact,
    }


def validate_epistemic_graph(
    value: object,
    *,
    program_state: Mapping[str, Any],
    artifact_root: str | Path,
) -> dict[str, Any]:
    """Validate graph structure, program evidence bindings, and verifier artifacts."""
    graph = _exact_object(
        value,
        required={"schema_version", "graph_id", "research_scope", "nodes", "edges"},
        allowed={"schema_version", "graph_id", "research_scope", "nodes", "edges", "metadata"},
        field="epistemic graph",
    )
    if graph["schema_version"] != GRAPH_SCHEMA_VERSION:
        raise EpistemicGraphError(
            f"unsupported graph schema_version: {graph['schema_version']!r}"
        )
    root = Path(artifact_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise EpistemicGraphError(f"artifact_root must be a directory: {root}")
    known_evidence = _known_program_evidence(program_state)

    raw_nodes = graph["nodes"]
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise EpistemicGraphError("nodes must be a non-empty list")
    nodes: list[dict[str, Any]] = []
    node_ids: set[str] = set()
    for index, raw_node in enumerate(raw_nodes):
        node = _validate_node(
            raw_node,
            index=index,
            known_evidence=known_evidence,
            artifact_root=root,
        )
        if node["node_id"] in node_ids:
            raise EpistemicGraphError(f"duplicate node_id: {node['node_id']}")
        node_ids.add(node["node_id"])
        nodes.append(node)
    nodes_by_id = {node["node_id"]: node for node in nodes}

    raw_edges = graph["edges"]
    if not isinstance(raw_edges, list):
        raise EpistemicGraphError("edges must be a list")
    edges: list[dict[str, Any]] = []
    edge_ids: set[str] = set()
    for index, raw_edge in enumerate(raw_edges):
        edge = _validate_edge(
            raw_edge,
            index=index,
            nodes_by_id=nodes_by_id,
            artifact_root=root,
        )
        if edge["edge_id"] in edge_ids:
            raise EpistemicGraphError(f"duplicate edge_id: {edge['edge_id']}")
        edge_ids.add(edge["edge_id"])
        edges.append(edge)

    normalized: dict[str, Any] = {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "graph_id": _nonempty_text(graph["graph_id"], "graph_id"),
        "research_scope": _nonempty_text(graph["research_scope"], "research_scope"),
        "nodes": nodes,
        "edges": edges,
    }
    if "metadata" in graph:
        if not isinstance(graph["metadata"], dict):
            raise EpistemicGraphError("metadata must be an object")
        normalized["metadata"] = graph["metadata"]
    return normalized


def _source_is_usable_for_verified_relation(node: Mapping[str, Any]) -> bool:
    if node["node_type"] == "evidence":
        return node.get("evidence_quality") in {"supported", "diagnostic"}
    if node["node_type"] in _EXECUTABLE_NODE_TYPES:
        return node.get("execution_status") == "completed"
    return False


def evaluate_epistemic_graph(
    value: object,
    *,
    program_state: Mapping[str, Any],
    artifact_root: str | Path,
) -> dict[str, Any]:
    """Derive bounded epistemic statuses without auto-granting final positive truth."""
    graph = validate_epistemic_graph(
        value,
        program_state=program_state,
        artifact_root=artifact_root,
    )
    nodes_by_id = {node["node_id"]: node for node in graph["nodes"]}
    assessments: list[dict[str, Any]] = []
    for node in graph["nodes"]:
        if node["node_type"] not in _INFERENCE_TARGET_TYPES:
            continue
        verified = [
            edge
            for edge in graph["edges"]
            if edge["active"]
            and edge["target_node_id"] == node["node_id"]
            and edge["relation"] in {"supports", "contradicts", "falsifies"}
            and edge["assessment_level"] == "domain_verified"
            and _source_is_usable_for_verified_relation(nodes_by_id[edge["source_node_id"]])
        ]
        diagnostic = [
            edge
            for edge in graph["edges"]
            if edge["active"]
            and edge["target_node_id"] == node["node_id"]
            and edge["relation"] in {"supports", "contradicts", "falsifies"}
            and edge["assessment_level"] == "diagnostic"
        ]
        supports = [edge["edge_id"] for edge in verified if edge["relation"] == "supports"]
        contradicts = [
            edge["edge_id"] for edge in verified if edge["relation"] == "contradicts"
        ]
        falsifies = [edge["edge_id"] for edge in verified if edge["relation"] == "falsifies"]
        if falsifies:
            status = "falsified_within_verified_scope"
        elif supports and contradicts:
            status = "contested"
        elif contradicts:
            status = "contradicted_within_verified_scope"
        elif supports:
            status = "provisionally_supported"
        else:
            status = "inconclusive"
        assessments.append(
            {
                "node_id": node["node_id"],
                "node_type": node["node_type"],
                "status": status,
                "verified_support_edges": supports,
                "verified_contradiction_edges": contradicts,
                "verified_falsification_edges": falsifies,
                "diagnostic_relation_edges": [edge["edge_id"] for edge in diagnostic],
                "final_positive_support_granted": False,
                "domain_closeout_required_for_positive_conclusion": status
                == "provisionally_supported",
                "confidence_score": None,
            }
        )
    return {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "graph_policy_version": GRAPH_POLICY_VERSION,
        "graph_id": graph["graph_id"],
        "research_scope": graph["research_scope"],
        "nodes": graph["nodes"],
        "edges": graph["edges"],
        "assessments": assessments,
        "conflict_count": sum(item["status"] == "contested" for item in assessments),
        "falsified_count": sum(
            item["status"] == "falsified_within_verified_scope" for item in assessments
        ),
        "autonomy_boundary": {
            "proposal_relations_affect_status": False,
            "diagnostic_relations_affect_verified_status": False,
            "domain_verified_relations_require_checksum_bound_verifier_artifacts": True,
            "final_positive_support_is_automatic": False,
            "numeric_confidence_invented": False,
        },
    }


__all__ = [
    "GRAPH_POLICY_VERSION",
    "GRAPH_SCHEMA_VERSION",
    "EpistemicGraphError",
    "evaluate_epistemic_graph",
    "validate_epistemic_graph",
]
