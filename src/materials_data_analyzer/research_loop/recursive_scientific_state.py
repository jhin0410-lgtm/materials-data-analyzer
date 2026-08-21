"""Portable scientific-state identities for bounded recursive research cycles.

Graph IDs, local artifact paths, transition-lineage bookkeeping and diagnostic-only
relations are not themselves new scientific information. Exact planning-source binding
uses a path-insensitive identity of the whole evaluated graph, while recursive stopping
uses only the target's status-affecting verified directional evidence.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from .kernel import ResearchLoopError

RECURSIVE_SCIENTIFIC_STATE_SCHEMA_VERSION = "1.0"
RECURSIVE_SCIENTIFIC_STATE_POLICY_VERSION = "1.0"
_DIRECTIONAL = {"supports", "contradicts", "falsifies"}


class RecursiveScientificStateError(ResearchLoopError):
    """Raised when an evaluated graph cannot yield a stable scientific identity."""


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RecursiveScientificStateError(f"{field} must be an object")
    return value


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise RecursiveScientificStateError(f"{field} must be a sequence")
    return value


def _portable(value: object) -> object:
    """Normalize verifier/artifact paths while preserving all non-path semantics."""
    if isinstance(value, Mapping):
        omit = {"path", "bytes", "source_path"} if "sha256" in value else set()
        return {
            str(key): _portable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if key not in omit
        }
    if isinstance(value, list):
        return [_portable(item) for item in value]
    if isinstance(value, tuple):
        return [_portable(item) for item in value]
    return value


def evaluated_graph_scientific_identity_sha256(
    evaluated_graph: Mapping[str, Any],
) -> str:
    """Bind the entire evaluated graph while excluding only local path resolution."""
    graph = _mapping(evaluated_graph, "evaluated_graph")
    return _sha(_portable(graph))


def _source_scientific_identity(node: Mapping[str, Any]) -> dict[str, Any]:
    portable = dict(_mapping(_portable(node), "portable source node"))
    portable.pop("node_id", None)
    return portable


def target_scientific_state_fingerprint(
    evaluated_graph: Mapping[str, Any],
    *,
    target_node_id: str,
) -> dict[str, Any]:
    """Fingerprint target status plus active domain-verified directional evidence."""
    graph = _mapping(evaluated_graph, "evaluated_graph")
    nodes = [
        _mapping(item, f"evaluated_graph.nodes[{index}]")
        for index, item in enumerate(_sequence(graph.get("nodes"), "evaluated_graph.nodes"))
    ]
    by_id = {str(item.get("node_id")): item for item in nodes}
    if target_node_id not in by_id:
        raise RecursiveScientificStateError("target node is absent from evaluated graph")

    assessment_matches = [
        _mapping(item, f"evaluated_graph.assessments[{index}]")
        for index, item in enumerate(
            _sequence(graph.get("assessments"), "evaluated_graph.assessments")
        )
        if isinstance(item, Mapping) and item.get("node_id") == target_node_id
    ]
    if len(assessment_matches) != 1:
        raise RecursiveScientificStateError(
            "target must resolve to exactly one evaluated assessment"
        )
    assessment = assessment_matches[0]

    verified: list[dict[str, Any]] = []
    for index, raw in enumerate(_sequence(graph.get("edges"), "evaluated_graph.edges")):
        edge = _mapping(raw, f"evaluated_graph.edges[{index}]")
        if not (
            edge.get("active") is True
            and edge.get("target_node_id") == target_node_id
            and edge.get("relation") in _DIRECTIONAL
            and edge.get("assessment_level") == "domain_verified"
        ):
            continue
        source_id = edge.get("source_node_id")
        source = by_id.get(str(source_id))
        if source is None:
            raise RecursiveScientificStateError(
                "verified directional edge source is absent from evaluated graph"
            )
        verifier = edge.get("verification_artifact")
        if not isinstance(verifier, Mapping):
            raise RecursiveScientificStateError(
                "domain-verified directional edge omitted verification artifact"
            )
        verified.append(
            {
                "relation": edge.get("relation"),
                "source": _source_scientific_identity(source),
                "verification_artifact": _portable(verifier),
            }
        )
    verified.sort(key=_sha)

    target = dict(_mapping(_portable(by_id[target_node_id]), "portable target"))
    payload: dict[str, Any] = {
        "schema_version": RECURSIVE_SCIENTIFIC_STATE_SCHEMA_VERSION,
        "policy_version": RECURSIVE_SCIENTIFIC_STATE_POLICY_VERSION,
        "target": target,
        "assessment_status": assessment.get("status"),
        "verified_directional_evidence": verified,
        "diagnostic_edges_included": False,
        "graph_version_included": False,
        "local_artifact_paths_included": False,
    }
    payload["fingerprint_sha256"] = _sha(payload)
    return payload


__all__ = [
    "RECURSIVE_SCIENTIFIC_STATE_POLICY_VERSION",
    "RECURSIVE_SCIENTIFIC_STATE_SCHEMA_VERSION",
    "RecursiveScientificStateError",
    "evaluated_graph_scientific_identity_sha256",
    "target_scientific_state_fingerprint",
]
