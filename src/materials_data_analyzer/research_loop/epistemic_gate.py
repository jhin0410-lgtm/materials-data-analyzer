"""Checksum-bound epistemic gate for repeated research execution.

The gate reconstructs the current mission program state, revalidates an epistemic graph
against that exact state and its verifier artifacts, and derives an execution directive
for explicitly selected target nodes. It performs no research action itself.
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


class EpistemicGateError(ResearchLoopError):
    """Raised when the graph-to-execution gate cannot be revalidated."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EpistemicGateError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise EpistemicGateError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EpistemicGateError(f"JSON root must be an object: {path}")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EpistemicGateError(f"{field} must be a non-empty string")
    return value.strip()


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

    graph = _load_json(graph_file)
    evaluation = evaluate_epistemic_graph(
        graph,
        program_state=program,
        artifact_root=artifacts,
    )
    directive = derive_epistemic_directive(
        evaluation,
        target_node_ids=target_node_ids,
    )
    return {
        "schema_version": EPISTEMIC_GATE_SCHEMA_VERSION,
        "adapter_id": adapter,
        "workstream_id": workstream,
        "mission_binding": program.get("mission_binding"),
        "runtime_context_binding": program.get("runtime_context_binding"),
        "graph_binding": {
            "path": str(graph_file),
            "sha256": _sha256_file(graph_file),
        },
        "graph_policy_version": evaluation.get("graph_policy_version"),
        "directive": directive,
        "autonomy_boundary": {
            "program_state_rebuilt_before_gate": True,
            "graph_revalidated_against_current_program_state": True,
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
