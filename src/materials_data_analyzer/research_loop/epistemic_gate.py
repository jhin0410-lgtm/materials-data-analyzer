"""Checksum-bound epistemic gate for repeated research execution.

The gate reconstructs the current mission program state, revalidates an epistemic graph
against that exact state and its verifier artifacts, scopes selected targets to the
selected workstream's provenance, and derives one fail-closed execution directive. It
performs no research action itself.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .epistemic_control import derive_epistemic_directive
from .epistemic_graph import evaluate_epistemic_graph
from .kernel import ResearchLoopError
from .research_program import build_research_program

EPISTEMIC_GATE_SCHEMA_VERSION = "1.0"

_INFERENCE_RELATIONS = {"supports", "contradicts", "falsifies"}
_PROVENANCE_RELATIONS = {
    "supports",
    "contradicts",
    "falsifies",
    "tests",
    "depends_on",
    "produced_by",
    "addresses",
}
_PROVENANCE_NODE_TYPES = {"evidence", "analysis", "simulation", "experiment"}


class EpistemicGateError(ResearchLoopError):
    """Raised when the graph-to-execution gate cannot be revalidated."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EpistemicGateError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _parse_json_bytes(raw_bytes: bytes, path: Path) -> dict[str, Any]:
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EpistemicGateError(f"invalid UTF-8 in {path}: {exc}") from exc
    try:
        value = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise EpistemicGateError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EpistemicGateError(f"JSON root must be an object: {path}")
    return value


def _load_json_snapshot(path: Path) -> tuple[dict[str, Any], str]:
    """Read once, then parse and hash the exact same immutable byte snapshot."""
    raw_bytes = path.read_bytes()
    return _parse_json_bytes(raw_bytes, path), hashlib.sha256(raw_bytes).hexdigest()


def _nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EpistemicGateError(f"{field} must be a non-empty string")
    return value.strip()


def _target_ids(values: Sequence[object]) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise EpistemicGateError("target_node_ids must be a sequence of node IDs")
    result: list[str] = []
    for index, value in enumerate(values):
        node_id = _nonempty_text(value, f"target_node_ids[{index}]")
        if node_id in result:
            raise EpistemicGateError(f"duplicate target node ID is not allowed: {node_id}")
        result.append(node_id)
    if not result:
        raise EpistemicGateError("target_node_ids must not be empty")
    return result


def _source_workstreams(
    node_id: str,
    *,
    nodes_by_id: Mapping[str, Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    memo: dict[str, frozenset[str]],
    visiting: set[str] | None = None,
) -> frozenset[str]:
    """Resolve evidence workstreams upstream of one evidence/computational source node.

    Only provenance-bearing evidence/computational nodes are traversed. Hypotheses,
    claims, conclusions, and research questions are deliberate traversal barriers so a
    shared conceptual node cannot make otherwise unrelated workstreams appear bound.
    """
    if node_id in memo:
        return memo[node_id]
    node = nodes_by_id.get(node_id)
    if node is None:
        return frozenset()
    if visiting is None:
        visiting = set()
    if node_id in visiting:
        return frozenset()
    visiting.add(node_id)

    workstreams: set[str] = set()
    binding = node.get("evidence_binding")
    if isinstance(binding, Mapping):
        workstream_id = binding.get("workstream_id")
        if isinstance(workstream_id, str) and workstream_id:
            workstreams.add(workstream_id)

    for edge in edges:
        if edge.get("active") is not True or edge.get("relation") not in _PROVENANCE_RELATIONS:
            continue
        source_id = edge.get("source_node_id")
        target_id = edge.get("target_node_id")
        other_id: str | None = None
        if source_id == node_id and isinstance(target_id, str):
            other_id = target_id
        elif target_id == node_id and isinstance(source_id, str):
            other_id = source_id
        if other_id is None or other_id in visiting:
            continue
        other = nodes_by_id.get(other_id)
        if not isinstance(other, Mapping) or other.get("node_type") not in _PROVENANCE_NODE_TYPES:
            continue
        workstreams.update(
            _source_workstreams(
                other_id,
                nodes_by_id=nodes_by_id,
                edges=edges,
                memo=memo,
                visiting=visiting,
            )
        )

    visiting.remove(node_id)
    resolved = frozenset(workstreams)
    memo[node_id] = resolved
    return resolved


def _status_from_edges(
    supports: Sequence[str], contradicts: Sequence[str], falsifies: Sequence[str]
) -> str:
    if falsifies:
        return "falsified_within_verified_scope"
    if supports and contradicts:
        return "contested"
    if contradicts:
        return "contradicted_within_verified_scope"
    if supports:
        return "provisionally_supported"
    return "inconclusive"


def _scope_evaluation_to_workstream(
    evaluation: Mapping[str, Any],
    *,
    workstream_id: str,
    target_node_ids: Sequence[str],
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    raw_nodes = evaluation.get("nodes")
    raw_edges = evaluation.get("edges")
    raw_assessments = evaluation.get("assessments")
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        raise EpistemicGateError("epistemic evaluation omitted normalized nodes/edges")
    if not isinstance(raw_assessments, list):
        raise EpistemicGateError("epistemic evaluation assessments must be a list")

    nodes_by_id = {
        str(node["node_id"]): node
        for node in raw_nodes
        if isinstance(node, Mapping) and isinstance(node.get("node_id"), str)
    }
    edges = [edge for edge in raw_edges if isinstance(edge, Mapping)]
    edges_by_id = {
        str(edge["edge_id"]): edge
        for edge in edges
        if isinstance(edge.get("edge_id"), str)
    }
    assessments_by_id = {
        str(item["node_id"]): item
        for item in raw_assessments
        if isinstance(item, Mapping) and isinstance(item.get("node_id"), str)
    }
    memo: dict[str, frozenset[str]] = {}
    provenance_report: dict[str, list[str]] = {}
    scoped_assessments: list[dict[str, Any]] = []

    for target_id in target_node_ids:
        if target_id not in assessments_by_id:
            raise EpistemicGateError(
                f"selected target is not an assessed hypothesis/claim/conclusion: {target_id}"
            )
        target_sources = [
            edge
            for edge in edges
            if edge.get("active") is True
            and edge.get("target_node_id") == target_id
            and edge.get("relation") in _PROVENANCE_RELATIONS
            and isinstance(edge.get("source_node_id"), str)
        ]
        target_workstreams: set[str] = set()
        for edge in target_sources:
            target_workstreams.update(
                _source_workstreams(
                    str(edge["source_node_id"]),
                    nodes_by_id=nodes_by_id,
                    edges=edges,
                    memo=memo,
                )
            )
        provenance_report[target_id] = sorted(target_workstreams)
        if workstream_id not in target_workstreams:
            raise EpistemicGateError(
                "selected epistemic target is not provenance-bound to the selected workstream: "
                f"target={target_id}, workstream={workstream_id}, "
                f"observed_workstreams={sorted(target_workstreams)}"
            )

        original = assessments_by_id[target_id]

        def relevant(edge_id: object) -> bool:
            if not isinstance(edge_id, str):
                return False
            edge = edges_by_id.get(edge_id)
            if not isinstance(edge, Mapping):
                return False
            source_id = edge.get("source_node_id")
            if not isinstance(source_id, str):
                return False
            return workstream_id in _source_workstreams(
                source_id,
                nodes_by_id=nodes_by_id,
                edges=edges,
                memo=memo,
            )

        supports = [
            edge_id
            for edge_id in original.get("verified_support_edges", [])
            if relevant(edge_id)
        ]
        contradicts = [
            edge_id
            for edge_id in original.get("verified_contradiction_edges", [])
            if relevant(edge_id)
        ]
        falsifies = [
            edge_id
            for edge_id in original.get("verified_falsification_edges", [])
            if relevant(edge_id)
        ]
        diagnostic = [
            edge_id
            for edge_id in original.get("diagnostic_relation_edges", [])
            if relevant(edge_id)
        ]
        status = _status_from_edges(supports, contradicts, falsifies)
        scoped_assessments.append(
            {
                **dict(original),
                "status": status,
                "verified_support_edges": supports,
                "verified_contradiction_edges": contradicts,
                "verified_falsification_edges": falsifies,
                "diagnostic_relation_edges": diagnostic,
                "domain_closeout_required_for_positive_conclusion": status
                == "provisionally_supported",
                "final_positive_support_granted": False,
                "confidence_score": None,
            }
        )

    scoped_evaluation = {
        "graph_id": evaluation.get("graph_id"),
        "assessments": scoped_assessments,
    }
    return scoped_evaluation, provenance_report


def evaluate_epistemic_gate(
    *,
    adapter_id: str,
    workstream_id: str,
    target_node_ids: Sequence[object],
    mission_path: str | Path,
    graph_path: str | Path,
    repository_root: str | Path,
    runtime_context_path: str | Path | None = None,
    artifact_root: str | Path | None = None,
) -> dict[str, Any]:
    """Rebuild program+graph state and return one fail-closed execution directive."""
    adapter = _nonempty_text(adapter_id, "adapter_id")
    workstream = _nonempty_text(workstream_id, "workstream_id")
    targets = _target_ids(target_node_ids)
    root = Path(repository_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise EpistemicGateError(f"repository_root must be a directory: {root}")
    mission = Path(mission_path).expanduser().resolve(strict=True)
    graph_file = Path(graph_path).expanduser().resolve(strict=True)
    artifacts = (
        Path(artifact_root).expanduser().resolve(strict=True)
        if artifact_root is not None
        else root
    )
    if not artifacts.is_dir():
        raise EpistemicGateError(f"artifact_root must be a directory: {artifacts}")

    program = build_research_program(
        mission,
        repository_root=root,
        runtime_context_path=runtime_context_path,
    )
    workstreams = program.get("workstreams")
    if not isinstance(workstreams, list):
        raise EpistemicGateError("research program workstreams must be a list")
    matches = [
        item
        for item in workstreams
        if isinstance(item, Mapping) and item.get("workstream_id") == workstream
    ]
    if len(matches) != 1:
        raise EpistemicGateError(
            f"mission must contain exactly one selected workstream_id: {workstream}"
        )
    if matches[0].get("adapter_id") != adapter:
        raise EpistemicGateError(
            "selected epistemic workstream adapter_id does not match execution adapter_id"
        )
    if matches[0].get("status") != "verified":
        raise EpistemicGateError(
            "selected epistemic workstream does not currently have verified planning state"
        )

    graph, graph_sha256 = _load_json_snapshot(graph_file)
    evaluation = evaluate_epistemic_graph(
        graph,
        program_state=program,
        artifact_root=artifacts,
    )
    scoped_evaluation, target_provenance = _scope_evaluation_to_workstream(
        evaluation,
        workstream_id=workstream,
        target_node_ids=targets,
    )
    directive = derive_epistemic_directive(
        scoped_evaluation,
        target_node_ids=targets,
    )
    return {
        "schema_version": EPISTEMIC_GATE_SCHEMA_VERSION,
        "adapter_id": adapter,
        "workstream_id": workstream,
        "mission_binding": program.get("mission_binding"),
        "runtime_context_binding": program.get("runtime_context_binding"),
        "graph_binding": {
            "path": str(graph_file),
            "sha256": graph_sha256,
        },
        "graph_policy_version": evaluation.get("graph_policy_version"),
        "target_workstream_provenance": target_provenance,
        "directive": directive,
        "autonomy_boundary": {
            "program_state_rebuilt_before_gate": True,
            "graph_revalidated_against_current_program_state": True,
            "graph_parse_and_hash_share_one_byte_snapshot": True,
            "selected_targets_require_selected_workstream_provenance": True,
            "cross_workstream_inference_edges_affect_directive": False,
            "verifier_artifacts_rechecked": True,
            "gate_executes_research_actions": False,
            "gate_upgrades_scientific_evidence": False,
        },
    }


__all__ = [
    "EPISTEMIC_GATE_SCHEMA_VERSION",
    "EpistemicGateError",
    "evaluate_epistemic_gate",
]
