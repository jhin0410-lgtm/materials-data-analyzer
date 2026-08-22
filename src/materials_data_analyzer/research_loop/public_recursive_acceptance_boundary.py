"""Acceptance hardening for the public two-cycle real-evidence replay.

A caller-authored empty frontier is not evidence that no authorized acquisition action
exists.  Both planning-state construction and final manifest publication independently
reload the exact request-pinned registry.  The manifest also reconstructs cycle-1
progression/completion and exact cycle-2 ancestry.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .action_registry import load_action_registry
from .kernel import ResearchLoopError
from .public_recursive_planning import (
    PublicRecursivePlanningError,
    build_external_evidence_waiting_program_state as _build_waiting_state,
    validate_public_recursive_planning_context,
)
from .public_recursive_progression import (
    PublicRecursiveProgressionError,
    build_public_recursive_replay_manifest as _build_replay_manifest,
    complete_public_recursive_cycle_with_rediagnosis,
    validate_public_recursive_progression,
)

EXTERNAL_CANDIDATE_RESOLUTION_SCHEMA_VERSION = "1.0"
EXTERNAL_CANDIDATE_RESOLUTION_POLICY_VERSION = "1.1"
CROSS_CYCLE_ANCESTRY_POLICY_VERSION = "1.1"


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
        raise PublicRecursiveProgressionError(
            "acceptance state must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PublicRecursivePlanningError(f"{field} must be an object")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise PublicRecursivePlanningError(f"{field} must be non-empty trimmed text")
    return value


def _embedded_sha(
    value: Mapping[str, Any],
    *,
    sha_field: str,
    field: str,
) -> str:
    snapshot = dict(_mapping(value, field))
    digest = snapshot.pop(sha_field, None)
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(ch not in "0123456789abcdef" for ch in digest)
    ):
        raise PublicRecursiveProgressionError(
            f"{field}.{sha_field} must be lowercase SHA-256"
        )
    if _canonical_sha256(snapshot) != digest:
        raise PublicRecursiveProgressionError(
            f"{field}.{sha_field} does not match canonical content"
        )
    return digest


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PublicRecursivePlanningError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _request_snapshot(
    discrepancy_report: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    bindings = _mapping(
        discrepancy_report.get("input_bindings"),
        "discrepancy_report.input_bindings",
    )
    request_binding = _mapping(
        bindings.get("execution_request"),
        "discrepancy_report.input_bindings.execution_request",
    )
    try:
        request_path = Path(
            _text(request_binding.get("path"), "execution_request.path")
        ).expanduser().resolve(strict=True)
    except OSError as exc:
        raise PublicRecursivePlanningError(
            "execution_request.path no longer resolves"
        ) from exc
    if not request_path.is_file():
        raise PublicRecursivePlanningError("execution_request.path must be a file")
    raw = request_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if request_binding.get("sha256") != digest or request_binding.get("bytes") != len(raw):
        raise PublicRecursivePlanningError(
            "execution request bytes changed after discrepancy validation"
        )
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublicRecursivePlanningError(
            "execution request must remain valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise PublicRecursivePlanningError("execution request root must be an object")
    return value, {
        "path": str(request_path),
        "sha256": digest,
        "bytes": len(raw),
    }


def _resolve_request_path(request_file: Path, value: object, *, field: str) -> Path:
    text = _text(value, field)
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = request_file.parent / path
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        raise PublicRecursivePlanningError(f"{field} no longer resolves") from exc


def _resolve_registry_state(
    discrepancy_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Independently reload the exact request-pinned registry and classify candidates."""
    request, request_record = _request_snapshot(discrepancy_report)
    request_file = Path(request_record["path"])
    repository_root = _resolve_request_path(
        request_file,
        request.get("repository_root"),
        field="execution_request.repository_root",
    )
    if not repository_root.is_dir():
        raise PublicRecursivePlanningError(
            "execution_request.repository_root must resolve to a directory"
        )
    registry_path = _resolve_request_path(
        request_file,
        request.get("registry"),
        field="execution_request.registry",
    )
    if not registry_path.is_file():
        raise PublicRecursivePlanningError(
            "execution_request.registry must resolve to a file"
        )
    try:
        registry = load_action_registry(
            registry_path,
            repository_root=repository_root,
        )
    except (ResearchLoopError, OSError) as exc:
        raise PublicRecursivePlanningError(
            "exact replay registry could not be independently reconstructed"
        ) from exc
    if request.get("expected_registry_sha256") != registry.get("registry_sha256"):
        raise PublicRecursivePlanningError(
            "execution request is not pinned to the current replay registry"
        )
    actions = registry.get("actions")
    if not isinstance(actions, list):
        raise PublicRecursivePlanningError("validated action registry omitted actions")
    available = sorted(
        str(action.get("action_type"))
        for action in actions
        if isinstance(action, Mapping)
        and action.get("category") == "external_evidence_search"
        and action.get("availability") == "available"
    )
    planned = sorted(
        str(action.get("action_type"))
        for action in actions
        if isinstance(action, Mapping)
        and action.get("category") == "external_evidence_search"
        and action.get("availability") == "planned"
    )
    return {
        "schema_version": EXTERNAL_CANDIDATE_RESOLUTION_SCHEMA_VERSION,
        "policy_version": EXTERNAL_CANDIDATE_RESOLUTION_POLICY_VERSION,
        "scope": "exact_replay_action_registry_only",
        "execution_request": request_record,
        "registry_path": str(registry_path),
        "registry_id": registry.get("registry_id"),
        "registry_sha256": registry.get("registry_sha256"),
        "available_external_evidence_action_types": available,
        "planned_external_evidence_action_types": planned,
        "available_external_evidence_action_count": len(available),
        "planned_external_evidence_action_count": len(planned),
        "bounded_stop_justified_by_no_available_registry_candidate": not available,
        "global_external_evidence_unavailability_claimed": False,
        "network_search_performed": False,
        "synthetic_candidate_created": False,
    }


def _require_no_available_registry_candidate(resolution: Mapping[str, Any]) -> None:
    if resolution.get("available_external_evidence_action_count") != 0:
        raise PublicRecursivePlanningError(
            "bounded evidence-waiting stop is invalid because the exact replay registry "
            "contains an available external_evidence_search action"
        )
    if resolution.get("available_external_evidence_action_types") != []:
        raise PublicRecursivePlanningError(
            "bounded evidence-waiting stop has inconsistent available-action evidence"
        )
    if resolution.get("bounded_stop_justified_by_no_available_registry_candidate") is not True:
        raise PublicRecursivePlanningError(
            "exact replay registry does not justify a bounded no-candidate stop"
        )


def build_registry_verified_external_evidence_waiting_program_state(
    *,
    planning_handoff: Mapping[str, Any],
    discrepancy_report: Mapping[str, Any],
    evaluated_graph: Mapping[str, Any],
    previous_discrepancy_report: Mapping[str, Any],
) -> dict[str, Any]:
    state = _build_waiting_state(
        planning_handoff=planning_handoff,
        discrepancy_report=discrepancy_report,
        evaluated_graph=evaluated_graph,
        previous_discrepancy_report=previous_discrepancy_report,
    )
    resolution = _resolve_registry_state(discrepancy_report)
    _require_no_available_registry_candidate(resolution)
    hardened = copy.deepcopy(state)
    binding = dict(
        _mapping(
            hardened.get("public_recursive_planner_binding"),
            "public_recursive_planner_binding",
        )
    )
    binding["repository_authorized_external_candidate_available"] = False
    binding["external_candidate_resolution"] = resolution
    hardened["public_recursive_planner_binding"] = binding
    return hardened


def _verify_cross_cycle_completion_ancestry(
    *,
    cycle1_planning_context: Mapping[str, Any],
    cycle1_progression: Mapping[str, Any],
    cycle1_completion: Mapping[str, Any],
    cycle2_planning_context: Mapping[str, Any],
    recursive_limits: Mapping[str, Any],
) -> dict[str, Any]:
    cycle1 = validate_public_recursive_planning_context(cycle1_planning_context)
    cycle2 = validate_public_recursive_planning_context(cycle2_planning_context)
    inputs1 = _mapping(cycle1.get("validation_inputs"), "cycle1.validation_inputs")
    inputs2 = _mapping(cycle2.get("validation_inputs"), "cycle2.validation_inputs")
    report1 = _mapping(inputs1.get("source_discrepancy_report"), "cycle1.source_discrepancy_report")
    report2 = _mapping(inputs2.get("source_discrepancy_report"), "cycle2.source_discrepancy_report")
    graph2 = _mapping(inputs2.get("source_evaluated_graph"), "cycle2.source_evaluated_graph")
    previous_context = _mapping(
        inputs2.get("previous_validated_planning_context"),
        "cycle2.previous_validated_planning_context",
    )
    if dict(previous_context) != dict(cycle1_planning_context):
        raise PublicRecursiveProgressionError(
            "cycle2 predecessor context differs from the exact cycle1 planning context"
        )
    progression_check = validate_public_recursive_progression(
        cycle1_progression,
        validated_planning_context=cycle1_planning_context,
        recursive_limits=recursive_limits,
    )
    progression_sha = _embedded_sha(
        cycle1_progression,
        sha_field="progression_sha256",
        field="cycle1_progression",
    )
    if progression_check.get("progression_sha256") != progression_sha:
        raise PublicRecursiveProgressionError(
            "cycle1 progression validator and canonical progression SHA differ"
        )
    rebuilt_completion = complete_public_recursive_cycle_with_rediagnosis(
        validated_planning_context=cycle1_planning_context,
        progression=cycle1_progression,
        current_discrepancy_report=report2,
        previous_discrepancy_report=report1,
        evaluated_graph=graph2,
        recursive_limits=recursive_limits,
    )
    completion_sha = _embedded_sha(
        cycle1_completion,
        sha_field="completion_sha256",
        field="cycle1_completion",
    )
    if rebuilt_completion != dict(cycle1_completion):
        raise PublicRecursiveProgressionError(
            "cycle1 completion differs from deterministic public re-diagnosis reconstruction"
        )
    if rebuilt_completion.get("completion_sha256") != completion_sha:
        raise PublicRecursiveProgressionError(
            "rebuilt completion SHA differs from supplied completion"
        )
    ancestry = _mapping(rebuilt_completion.get("ancestry"), "cycle1_completion.ancestry")
    if ancestry.get("progression_sha256") != progression_sha:
        raise PublicRecursiveProgressionError(
            "cycle1 completion is not bound to the exact cycle1 progression SHA"
        )
    handoff2 = _mapping(inputs2.get("planning_handoff"), "cycle2.planning_handoff")
    next_handoff = _mapping(rebuilt_completion.get("next_planning_handoff"), "cycle1.next_handoff")
    if dict(next_handoff) != dict(handoff2):
        raise PublicRecursiveProgressionError(
            "cycle2 planning handoff differs from the exact cycle1 completion output"
        )
    if ancestry.get("next_planning_handoff_sha256") != handoff2.get("handoff_sha256"):
        raise PublicRecursiveProgressionError(
            "cycle2 handoff SHA is not the exact cycle1 completion handoff SHA"
        )
    if ancestry.get("previous_discrepancy_report_sha256") != report1.get("report_sha256"):
        raise PublicRecursiveProgressionError(
            "cycle1 completion previous discrepancy ancestry drifted"
        )
    if ancestry.get("current_discrepancy_report_sha256") != report2.get("report_sha256"):
        raise PublicRecursiveProgressionError(
            "cycle1 completion current discrepancy ancestry drifted"
        )
    return {
        "policy_version": CROSS_CYCLE_ANCESTRY_POLICY_VERSION,
        "cycle1_planning_context_sha256": cycle1["context_sha256"],
        "cycle1_progression_sha256": progression_sha,
        "cycle1_completion_sha256": completion_sha,
        "cycle2_planning_context_sha256": cycle2["context_sha256"],
        "cycle2_previous_context_exact_match": True,
        "cycle1_progression_exact_sha_verified": True,
        "cycle1_execution_and_transition_reconstructed": progression_check.get(
            "execution_and_transition_deterministically_reconstructed"
        ) is True,
        "cycle1_completion_deterministically_reconstructed": True,
        "cycle2_handoff_is_exact_cycle1_completion_output": True,
        "previous_discrepancy_ancestry_exact": True,
        "current_discrepancy_ancestry_exact": True,
    }


def build_registry_hardened_public_recursive_replay_manifest(
    *,
    cycle1_planning_context: Mapping[str, Any],
    cycle1_progression: Mapping[str, Any],
    cycle1_completion: Mapping[str, Any],
    cycle2_planning_context: Mapping[str, Any],
    recursive_limits: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        cross_cycle = _verify_cross_cycle_completion_ancestry(
            cycle1_planning_context=cycle1_planning_context,
            cycle1_progression=cycle1_progression,
            cycle1_completion=cycle1_completion,
            cycle2_planning_context=cycle2_planning_context,
            recursive_limits=recursive_limits,
        )
        cycle2 = validate_public_recursive_planning_context(cycle2_planning_context)
    except ResearchLoopError as exc:
        raise PublicRecursiveProgressionError(
            "replay manifest source artifacts failed public reconstruction"
        ) from exc

    inputs = _mapping(cycle2.get("validation_inputs"), "cycle2.validation_inputs")
    planner_state = _mapping(inputs.get("planner_program_state"), "cycle2.planner_program_state")
    binding = _mapping(
        planner_state.get("public_recursive_planner_binding"),
        "cycle2.public_recursive_planner_binding",
    )
    embedded_resolution = _mapping(
        binding.get("external_candidate_resolution"),
        "cycle2.external_candidate_resolution",
    )
    report2 = _mapping(inputs.get("source_discrepancy_report"), "cycle2.source_discrepancy_report")
    independent_resolution = _resolve_registry_state(report2)
    _require_no_available_registry_candidate(independent_resolution)
    if dict(embedded_resolution) != independent_resolution:
        raise PublicRecursiveProgressionError(
            "cycle2 bounded-stop registry evidence differs from independent request/registry reconstruction"
        )
    if (
        independent_resolution.get("global_external_evidence_unavailability_claimed") is not False
        or independent_resolution.get("network_search_performed") is not False
        or independent_resolution.get("synthetic_candidate_created") is not False
    ):
        raise PublicRecursiveProgressionError(
            "cycle2 bounded-stop evidence overclaims or fabricates external evidence state"
        )

    manifest = _build_replay_manifest(
        cycle1_planning_context=cycle1_planning_context,
        cycle1_progression=cycle1_progression,
        cycle1_completion=cycle1_completion,
        cycle2_planning_context=cycle2_planning_context,
        recursive_limits=recursive_limits,
    )
    result = copy.deepcopy(manifest)
    result["cross_cycle_ancestry"] = cross_cycle
    result["bounded_stop_evidence"] = copy.deepcopy(independent_resolution)
    result.pop("manifest_sha256", None)
    result["manifest_sha256"] = _canonical_sha256(result)
    return result


build_external_evidence_waiting_program_state = (
    build_registry_verified_external_evidence_waiting_program_state
)
build_public_recursive_replay_manifest = (
    build_registry_hardened_public_recursive_replay_manifest
)


__all__ = [
    "CROSS_CYCLE_ANCESTRY_POLICY_VERSION",
    "EXTERNAL_CANDIDATE_RESOLUTION_POLICY_VERSION",
    "EXTERNAL_CANDIDATE_RESOLUTION_SCHEMA_VERSION",
    "build_external_evidence_waiting_program_state",
    "build_public_recursive_replay_manifest",
    "build_registry_hardened_public_recursive_replay_manifest",
    "build_registry_verified_external_evidence_waiting_program_state",
]
