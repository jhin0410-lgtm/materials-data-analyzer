"""Append-only epistemic graph transitions for verified research results.

A completed action result may be recorded in the epistemic graph without gaining
scientific authority.  Only a separate, checksum-bound domain-verification decision
may promote the proposed inference edge to ``domain_verified``.  The transition also
prevents simulations or computational analyses from silently validating empirical
claims.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .epistemic_graph import evaluate_epistemic_graph, validate_epistemic_graph
from .kernel import ResearchLoopError

TRANSITION_SCHEMA_VERSION = "1.0"
VERIFICATION_SCHEMA_VERSION = "1.0"
TRANSITION_POLICY_VERSION = "1.0"

_RESULT_NODE_TYPES = {"analysis", "simulation", "experiment"}
_INFERENCE_RELATIONS = {"supports", "contradicts", "falsifies"}
_ACTION_CLASSES = {
    "existing_data_reanalysis",
    "computational_experiment",
    "sensitivity_analysis",
    "simulation",
    "replication",
    "physical_experiment",
}
_EXECUTION_MODES = {"typed_local_action", "external_result_ingest"}
_RESULT_ORIGINS = {
    "authorized_local_analysis",
    "authorized_local_simulation",
    "data_experiment",
    "external_physical_experiment",
    "external_analysis",
}
_INFERENCE_SCOPES = {
    "structural",
    "computational",
    "empirical_derived",
    "empirical_direct",
}
_TARGET_CLAIM_SCOPES = {"structural", "computational", "empirical", "mixed"}


class EpistemicTransitionError(ResearchLoopError):
    """Raised when a graph transition violates provenance or scientific boundaries."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EpistemicTransitionError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _read_json_snapshot(path: Path) -> tuple[dict[str, Any], bytes, str]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EpistemicTransitionError(f"invalid UTF-8 in {path}: {exc}") from exc
    try:
        value = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise EpistemicTransitionError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EpistemicTransitionError(f"JSON root must be an object: {path}")
    return value, raw, hashlib.sha256(raw).hexdigest()


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EpistemicTransitionError(f"{field} must be a non-empty string")
    return value.strip()


def _exact_object(
    value: object,
    *,
    required: set[str],
    allowed: set[str],
    field: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EpistemicTransitionError(f"{field} must be an object")
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - allowed)
    if missing:
        raise EpistemicTransitionError(f"{field} is missing required keys: {', '.join(missing)}")
    if unknown:
        raise EpistemicTransitionError(f"{field} has unknown keys: {', '.join(unknown)}")
    return value


def _enum(value: object, allowed: set[str], field: str) -> str:
    text = _nonempty_text(value, field)
    if text not in allowed:
        raise EpistemicTransitionError(f"{field} must be one of: {', '.join(sorted(allowed))}")
    return text


def _string_list(value: object, field: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list):
        raise EpistemicTransitionError(f"{field} must be a list")
    if not allow_empty and not value:
        raise EpistemicTransitionError(f"{field} must not be empty")
    result: list[str] = []
    for index, item in enumerate(value):
        text = _nonempty_text(item, f"{field}[{index}]")
        if text in result:
            raise EpistemicTransitionError(f"{field} must not contain duplicates")
        result.append(text)
    return result


def _known_program_evidence(program_state: Mapping[str, Any]) -> set[tuple[str, str, str]]:
    workstreams = program_state.get("workstreams")
    if not isinstance(workstreams, list):
        raise EpistemicTransitionError("program_state.workstreams must be a list")
    known: set[tuple[str, str, str]] = set()
    for item in workstreams:
        if not isinstance(item, Mapping):
            continue
        workstream_id = item.get("workstream_id")
        planning_state = item.get("planning_state")
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


def _validate_input_evidence(
    value: object,
    *,
    program_state: Mapping[str, Any],
) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise EpistemicTransitionError("input_evidence_bindings must be a list")
    known = _known_program_evidence(program_state)
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(value):
        item = _exact_object(
            raw,
            required={"workstream_id", "role", "sha256"},
            allowed={"workstream_id", "role", "sha256"},
            field=f"input_evidence_bindings[{index}]",
        )
        key = (
            _nonempty_text(item["workstream_id"], f"input_evidence_bindings[{index}].workstream_id"),
            _nonempty_text(item["role"], f"input_evidence_bindings[{index}].role"),
            _nonempty_text(item["sha256"], f"input_evidence_bindings[{index}].sha256"),
        )
        if key in seen:
            raise EpistemicTransitionError("input_evidence_bindings must not contain duplicates")
        if key not in known:
            raise EpistemicTransitionError(
                "transition references input evidence that is not bound by the verified program state"
            )
        seen.add(key)
        normalized.append({"workstream_id": key[0], "role": key[1], "sha256": key[2]})
    return normalized


def _resolve_artifact(path_value: object, artifact_root: Path, field: str) -> Path:
    text = _nonempty_text(path_value, field)
    candidate = Path(text).expanduser()
    if not candidate.is_absolute():
        candidate = artifact_root / candidate
    resolved = candidate.resolve(strict=True)
    if not resolved.is_file():
        raise EpistemicTransitionError(f"{field} must resolve to a regular file: {resolved}")
    return resolved


def _validate_result_artifacts(
    value: object,
    *,
    artifact_root: Path,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise EpistemicTransitionError("result_node.artifact_bindings must be a non-empty list")
    normalized: list[dict[str, Any]] = []
    roles: set[str] = set()
    for index, raw in enumerate(value):
        item = _exact_object(
            raw,
            required={"role", "path", "sha256"},
            allowed={"role", "path", "sha256"},
            field=f"result_node.artifact_bindings[{index}]",
        )
        role = _nonempty_text(item["role"], f"result_node.artifact_bindings[{index}].role")
        if role in roles:
            raise EpistemicTransitionError("result artifact roles must be unique")
        roles.add(role)
        path = _resolve_artifact(
            item["path"], artifact_root, f"result_node.artifact_bindings[{index}].path"
        )
        expected = _nonempty_text(
            item["sha256"], f"result_node.artifact_bindings[{index}].sha256"
        )
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise EpistemicTransitionError(
                f"result artifact checksum mismatch for {role}: expected {expected}, got {actual}"
            )
        normalized.append(
            {"role": role, "path": str(path), "sha256": actual, "bytes": path.stat().st_size}
        )
    return normalized


def _target_claim_scope(target: Mapping[str, Any]) -> str | None:
    metadata = target.get("metadata")
    if not isinstance(metadata, Mapping):
        return None
    scope = metadata.get("claim_scope")
    if not isinstance(scope, str):
        return None
    return scope if scope in _TARGET_CLAIM_SCOPES else None


def _validate_verified_scope(
    *,
    result_node_type: str,
    result_origin: str,
    inference_scope: str,
    target_scope: str | None,
    input_evidence_bindings: list[Mapping[str, str]],
) -> None:
    if target_scope is None:
        raise EpistemicTransitionError(
            "domain verification requires target metadata.claim_scope to be one of structural, computational, empirical, mixed"
        )
    if result_node_type == "simulation":
        if inference_scope not in {"structural", "computational"}:
            raise EpistemicTransitionError("simulation results cannot receive empirical inference scope")
    elif result_node_type == "analysis":
        if inference_scope == "empirical_direct":
            raise EpistemicTransitionError("analysis results cannot receive empirical_direct scope")
        if inference_scope == "empirical_derived" and not input_evidence_bindings:
            raise EpistemicTransitionError(
                "empirical_derived analysis requires bound empirical input evidence"
            )
    elif result_node_type == "experiment":
        if result_origin == "external_physical_experiment":
            if inference_scope != "empirical_direct":
                raise EpistemicTransitionError(
                    "external physical experiment results require empirical_direct inference scope"
                )
        elif result_origin == "data_experiment":
            if inference_scope != "empirical_derived" or not input_evidence_bindings:
                raise EpistemicTransitionError(
                    "data experiments require empirical_derived scope and bound input evidence"
                )
        else:
            raise EpistemicTransitionError(
                "experiment result nodes must originate from external_physical_experiment or data_experiment"
            )

    compatible = {
        "structural": {"structural", "mixed"},
        "computational": {"computational", "mixed"},
        "empirical_derived": {"empirical", "mixed"},
        "empirical_direct": {"empirical", "mixed"},
    }[inference_scope]
    if target_scope not in compatible:
        raise EpistemicTransitionError(
            f"inference scope {inference_scope!r} is incompatible with target claim_scope {target_scope!r}"
        )


def validate_transition_proposal(
    value: object,
    *,
    base_graph: Mapping[str, Any],
    base_graph_sha256: str,
    program_state: Mapping[str, Any],
    artifact_root: str | Path,
) -> dict[str, Any]:
    """Validate one append-only result-to-graph transition proposal."""
    root = _exact_object(
        value,
        required={
            "schema_version",
            "transition_id",
            "base_graph_id",
            "base_graph_sha256",
            "new_graph_id",
            "target_node_id",
            "source_action",
            "result_node",
            "input_evidence_bindings",
            "proposed_inference",
            "limitations",
        },
        allowed={
            "schema_version",
            "transition_id",
            "base_graph_id",
            "base_graph_sha256",
            "new_graph_id",
            "target_node_id",
            "source_action",
            "result_node",
            "input_evidence_bindings",
            "proposed_inference",
            "limitations",
        },
        field="epistemic transition proposal",
    )
    if root["schema_version"] != TRANSITION_SCHEMA_VERSION:
        raise EpistemicTransitionError("unsupported epistemic transition schema_version")
    if root["base_graph_id"] != base_graph.get("graph_id"):
        raise EpistemicTransitionError("proposal base_graph_id does not match the validated base graph")
    if root["base_graph_sha256"] != base_graph_sha256:
        raise EpistemicTransitionError("proposal base_graph_sha256 does not match the exact base graph bytes")
    new_graph_id = _nonempty_text(root["new_graph_id"], "new_graph_id")
    if new_graph_id == base_graph.get("graph_id"):
        raise EpistemicTransitionError("new_graph_id must differ from base_graph_id")

    nodes = base_graph.get("nodes")
    if not isinstance(nodes, list):
        raise EpistemicTransitionError("base graph nodes must be a list")
    nodes_by_id = {
        item.get("node_id"): item
        for item in nodes
        if isinstance(item, Mapping) and isinstance(item.get("node_id"), str)
    }
    target_id = _nonempty_text(root["target_node_id"], "target_node_id")
    target = nodes_by_id.get(target_id)
    if not isinstance(target, Mapping) or target.get("node_type") not in {
        "hypothesis",
        "claim",
        "conclusion",
    }:
        raise EpistemicTransitionError(
            "target_node_id must reference an existing hypothesis, claim, or conclusion"
        )

    source_action = _exact_object(
        root["source_action"],
        required={"action_id", "action_class", "action_version", "execution_mode"},
        allowed={"action_id", "action_class", "action_version", "execution_mode"},
        field="source_action",
    )
    action_class = _enum(source_action["action_class"], _ACTION_CLASSES, "source_action.action_class")
    execution_mode = _enum(
        source_action["execution_mode"], _EXECUTION_MODES, "source_action.execution_mode"
    )

    artifact_root_path = Path(artifact_root).expanduser().resolve(strict=True)
    if not artifact_root_path.is_dir():
        raise EpistemicTransitionError(f"artifact_root must be a directory: {artifact_root_path}")
    result_node = _exact_object(
        root["result_node"],
        required={"node_id", "node_type", "statement", "artifact_bindings", "metadata"},
        allowed={"node_id", "node_type", "statement", "artifact_bindings", "metadata"},
        field="result_node",
    )
    result_node_id = _nonempty_text(result_node["node_id"], "result_node.node_id")
    if result_node_id in nodes_by_id:
        raise EpistemicTransitionError("result_node.node_id already exists in the base graph")
    result_node_type = _enum(result_node["node_type"], _RESULT_NODE_TYPES, "result_node.node_type")
    metadata = _exact_object(
        result_node["metadata"],
        required={"result_origin"},
        allowed={"result_origin", "claim_scope", "notes"},
        field="result_node.metadata",
    )
    result_origin = _enum(metadata["result_origin"], _RESULT_ORIGINS, "result_node.metadata.result_origin")
    if execution_mode == "typed_local_action" and result_origin in {
        "external_physical_experiment",
        "external_analysis",
    }:
        raise EpistemicTransitionError(
            "external physical/analysis results must use execution_mode=external_result_ingest"
        )
    if execution_mode == "external_result_ingest" and result_origin in {
        "authorized_local_analysis",
        "authorized_local_simulation",
    }:
        raise EpistemicTransitionError(
            "authorized local results must use execution_mode=typed_local_action"
        )
    if result_node_type == "simulation" and result_origin != "authorized_local_simulation":
        raise EpistemicTransitionError("simulation nodes require authorized_local_simulation origin")
    if result_node_type == "analysis" and result_origin not in {
        "authorized_local_analysis",
        "external_analysis",
    }:
        raise EpistemicTransitionError("analysis nodes require an analysis result origin")

    artifacts = _validate_result_artifacts(
        result_node["artifact_bindings"], artifact_root=artifact_root_path
    )
    input_evidence = _validate_input_evidence(
        root["input_evidence_bindings"], program_state=program_state
    )

    inference = _exact_object(
        root["proposed_inference"],
        required={"tests_edge_id", "inference_edge_id", "relation", "rationale"},
        allowed={"tests_edge_id", "inference_edge_id", "relation", "rationale"},
        field="proposed_inference",
    )
    tests_edge_id = _nonempty_text(inference["tests_edge_id"], "proposed_inference.tests_edge_id")
    inference_edge_id = _nonempty_text(
        inference["inference_edge_id"], "proposed_inference.inference_edge_id"
    )
    existing_edge_ids = {
        item.get("edge_id")
        for item in base_graph.get("edges", [])
        if isinstance(item, Mapping)
    }
    if tests_edge_id == inference_edge_id or tests_edge_id in existing_edge_ids or inference_edge_id in existing_edge_ids:
        raise EpistemicTransitionError("new transition edge IDs must be distinct and absent from the base graph")

    return {
        "schema_version": TRANSITION_SCHEMA_VERSION,
        "transition_id": _nonempty_text(root["transition_id"], "transition_id"),
        "base_graph_id": str(base_graph["graph_id"]),
        "base_graph_sha256": base_graph_sha256,
        "new_graph_id": new_graph_id,
        "target_node_id": target_id,
        "target_claim_scope": _target_claim_scope(target),
        "source_action": {
            "action_id": _nonempty_text(source_action["action_id"], "source_action.action_id"),
            "action_class": action_class,
            "action_version": _nonempty_text(source_action["action_version"], "source_action.action_version"),
            "execution_mode": execution_mode,
        },
        "result_node": {
            "node_id": result_node_id,
            "node_type": result_node_type,
            "statement": _nonempty_text(result_node["statement"], "result_node.statement"),
            "execution_status": "completed",
            "artifact_bindings": artifacts,
            "metadata": dict(metadata),
        },
        "result_origin": result_origin,
        "input_evidence_bindings": input_evidence,
        "proposed_inference": {
            "tests_edge_id": tests_edge_id,
            "inference_edge_id": inference_edge_id,
            "relation": _enum(inference["relation"], _INFERENCE_RELATIONS, "proposed_inference.relation"),
            "rationale": _nonempty_text(inference["rationale"], "proposed_inference.rationale"),
        },
        "limitations": _string_list(root["limitations"], "limitations"),
    }


def validate_verification_decision(
    value: object,
    *,
    proposal: Mapping[str, Any],
    proposal_sha256: str,
    verification_sha256: str,
) -> dict[str, Any]:
    """Validate the separate decision that may grant one inference domain-verified status."""
    root = _exact_object(
        value,
        required={
            "schema_version",
            "decision_id",
            "transition_id",
            "proposal_sha256",
            "base_graph_sha256",
            "result_node_id",
            "target_node_id",
            "relation",
            "inference_scope",
            "verifier_id",
            "rationale",
            "limitations",
            "domain_verified",
        },
        allowed={
            "schema_version",
            "decision_id",
            "transition_id",
            "proposal_sha256",
            "base_graph_sha256",
            "result_node_id",
            "target_node_id",
            "relation",
            "inference_scope",
            "verifier_id",
            "rationale",
            "limitations",
            "domain_verified",
        },
        field="verification decision",
    )
    if root["schema_version"] != VERIFICATION_SCHEMA_VERSION:
        raise EpistemicTransitionError("unsupported verification decision schema_version")
    expected_pairs = {
        "transition_id": proposal["transition_id"],
        "proposal_sha256": proposal_sha256,
        "base_graph_sha256": proposal["base_graph_sha256"],
        "result_node_id": proposal["result_node"]["node_id"],
        "target_node_id": proposal["target_node_id"],
        "relation": proposal["proposed_inference"]["relation"],
    }
    for field, expected in expected_pairs.items():
        if root[field] != expected:
            raise EpistemicTransitionError(
                f"verification decision {field} does not match the exact transition proposal"
            )
    if root["domain_verified"] is not True:
        raise EpistemicTransitionError("verification decision must explicitly set domain_verified=true")
    inference_scope = _enum(root["inference_scope"], _INFERENCE_SCOPES, "inference_scope")
    _validate_verified_scope(
        result_node_type=str(proposal["result_node"]["node_type"]),
        result_origin=str(proposal["result_origin"]),
        inference_scope=inference_scope,
        target_scope=proposal.get("target_claim_scope"),
        input_evidence_bindings=list(proposal["input_evidence_bindings"]),
    )
    return {
        "schema_version": VERIFICATION_SCHEMA_VERSION,
        "decision_id": _nonempty_text(root["decision_id"], "decision_id"),
        "transition_id": proposal["transition_id"],
        "proposal_sha256": proposal_sha256,
        "verification_sha256": verification_sha256,
        "base_graph_sha256": proposal["base_graph_sha256"],
        "result_node_id": proposal["result_node"]["node_id"],
        "target_node_id": proposal["target_node_id"],
        "relation": proposal["proposed_inference"]["relation"],
        "inference_scope": inference_scope,
        "verifier_id": _nonempty_text(root["verifier_id"], "verifier_id"),
        "rationale": _nonempty_text(root["rationale"], "verification rationale"),
        "limitations": _string_list(root["limitations"], "verification limitations", allow_empty=True),
        "domain_verified": True,
    }


def _assessment_for(result: Mapping[str, Any], node_id: str) -> dict[str, Any] | None:
    assessments = result.get("assessments")
    if not isinstance(assessments, list):
        return None
    matches = [
        item for item in assessments if isinstance(item, Mapping) and item.get("node_id") == node_id
    ]
    if len(matches) != 1:
        return None
    return dict(matches[0])


def apply_epistemic_transition_files(
    *,
    base_graph_path: str | Path,
    proposal_path: str | Path,
    program_state: Mapping[str, Any],
    artifact_root: str | Path,
    output_dir: str | Path,
    verification_decision_path: str | Path | None = None,
) -> dict[str, Any]:
    """Create one immutable successor graph after all proposal/verifier checks pass."""
    base_path = Path(base_graph_path).expanduser().resolve(strict=True)
    proposal_file = Path(proposal_path).expanduser().resolve(strict=True)
    artifacts = Path(artifact_root).expanduser().resolve(strict=True)
    output = Path(output_dir).expanduser().resolve()
    if output.exists():
        raise EpistemicTransitionError(f"output_dir must not already exist: {output}")

    base_raw, _, base_sha = _read_json_snapshot(base_path)
    proposal_raw, _, proposal_sha = _read_json_snapshot(proposal_file)
    base_validated = validate_epistemic_graph(
        base_raw,
        program_state=program_state,
        artifact_root=artifacts,
    )
    before_eval = evaluate_epistemic_graph(
        base_validated,
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

    verification = None
    verification_file: Path | None = None
    verification_sha: str | None = None
    if verification_decision_path is not None:
        verification_file = Path(verification_decision_path).expanduser().resolve(strict=True)
        verification_raw, _, verification_sha = _read_json_snapshot(verification_file)
        verification = validate_verification_decision(
            verification_raw,
            proposal=proposal,
            proposal_sha256=proposal_sha,
            verification_sha256=verification_sha,
        )

    inference = proposal["proposed_inference"]
    result_node = dict(proposal["result_node"])
    result_metadata = dict(result_node.get("metadata", {}))
    result_metadata["source_action"] = dict(proposal["source_action"])
    result_metadata["input_evidence_bindings"] = list(proposal["input_evidence_bindings"])
    result_metadata["transition_id"] = proposal["transition_id"]
    result_metadata["limitations"] = list(proposal["limitations"])
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
    inference_edge: dict[str, Any] = {
        "edge_id": inference["inference_edge_id"],
        "source_node_id": result_node["node_id"],
        "target_node_id": proposal["target_node_id"],
        "relation": inference["relation"],
        "assessment_level": "proposal" if verification is None else "domain_verified",
        "rationale": inference["rationale"],
        "active": True,
    }
    if verification is not None and verification_file is not None and verification_sha is not None:
        inference_edge["verification_artifact"] = {
            "role": "domain_verification_decision",
            "path": str(verification_file),
            "sha256": verification_sha,
        }

    metadata = dict(base_validated.get("metadata", {}))
    lineage = metadata.get("transition_lineage", [])
    if not isinstance(lineage, list):
        raise EpistemicTransitionError("base graph metadata.transition_lineage must be a list")
    metadata["transition_lineage"] = [
        *lineage,
        {
            "transition_id": proposal["transition_id"],
            "parent_graph_id": base_validated["graph_id"],
            "parent_graph_sha256": base_sha,
            "proposal_sha256": proposal_sha,
            "verification_decision_sha256": verification_sha,
            "result_node_id": result_node["node_id"],
        },
    ]

    successor = {
        "schema_version": base_validated["schema_version"],
        "graph_id": proposal["new_graph_id"],
        "research_scope": base_validated["research_scope"],
        "nodes": [*base_validated["nodes"], result_node],
        "edges": [*base_validated["edges"], tests_edge, inference_edge],
        "metadata": metadata,
    }
    after_eval = evaluate_epistemic_graph(
        successor,
        program_state=program_state,
        artifact_root=artifacts,
    )
    before_target = _assessment_for(before_eval, proposal["target_node_id"])
    after_target = _assessment_for(after_eval, proposal["target_node_id"])
    if before_target is None or after_target is None:
        raise EpistemicTransitionError("target assessment could not be reconstructed before/after transition")

    graph_bytes = _canonical_json_bytes(successor)
    graph_sha = hashlib.sha256(graph_bytes).hexdigest()
    manifest = {
        "schema_version": TRANSITION_SCHEMA_VERSION,
        "transition_policy_version": TRANSITION_POLICY_VERSION,
        "transition_id": proposal["transition_id"],
        "base_graph_binding": {"path": str(base_path), "sha256": base_sha},
        "proposal_binding": {"path": str(proposal_file), "sha256": proposal_sha},
        "verification_decision_binding": (
            None
            if verification_file is None or verification_sha is None
            else {"path": str(verification_file), "sha256": verification_sha}
        ),
        "result_artifact_bindings": list(proposal["result_node"]["artifact_bindings"]),
        "successor_graph": {
            "graph_id": successor["graph_id"],
            "path": str(output / "epistemic_graph.json"),
            "sha256": graph_sha,
        },
        "target_node_id": proposal["target_node_id"],
        "target_before": before_target,
        "target_after": after_target,
        "inference_assessment_level": inference_edge["assessment_level"],
        "domain_verification_applied": verification is not None,
        "verification": verification,
        "autonomy_boundary": {
            "action_execution_performed": False,
            "network_access_performed": False,
            "physical_experiment_execution_performed": False,
            "base_graph_mutated": False,
            "result_execution_success_treated_as_scientific_verification": False,
            "simulation_may_directly_verify_empirical_claim": False,
            "positive_support_grants_final_truth": False,
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
    "TRANSITION_POLICY_VERSION",
    "TRANSITION_SCHEMA_VERSION",
    "VERIFICATION_SCHEMA_VERSION",
    "EpistemicTransitionError",
    "apply_epistemic_transition_files",
    "validate_transition_proposal",
    "validate_verification_decision",
]
