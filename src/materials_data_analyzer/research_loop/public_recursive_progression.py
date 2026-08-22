"""Public execution/progression boundary for the real-evidence recursive replay.

The public validator does not trust a re-signed progression as execution truth.  Every
published progression carries only the file locations needed to reconstruct the same typed
execution and authenticated transition.  Validation re-runs the existing authorization,
ledger, domain-verifier and transition-consumer chain and compares the resulting progression
byte-for-byte with the supplied object.

The facade creates no scientific authority.  Re-diagnosis is additionally pinned to the
exact authenticated successor evaluated graph and to the exact request/result/report that
produced the progression being diagnosed.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .kernel import ResearchLoopError
from .public_recursive_discrepancy import validate_public_recursive_discrepancy_report
from .public_recursive_planning import (
    build_public_recursive_discrepancy_planning_handoff,
    validate_public_recursive_planning_context,
)
from .recursive_authorized_execution_evidence import (
    build_authenticated_recursive_execution_record,
)
from .recursive_research_cycle_evidence import (
    _advance_recursive_cycle_after_verified_transition,
)
from .recursive_resource_budget import normalize_recursive_limits

PUBLIC_RECURSIVE_REDIAGNOSIS_SCHEMA_VERSION = "1.0"
PUBLIC_RECURSIVE_REDIAGNOSIS_POLICY_VERSION = "1.1"
PUBLIC_RECURSIVE_REPLAY_MANIFEST_SCHEMA_VERSION = "1.0"
PUBLIC_RECURSIVE_REPLAY_MANIFEST_POLICY_VERSION = "1.1"
PUBLIC_RECURSIVE_PROGRESSION_BINDING_POLICY_VERSION = "1.1"


class PublicRecursiveProgressionError(ResearchLoopError):
    """Raised when public recursive progression ancestry cannot be reconstructed."""


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
            "public recursive progression state must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PublicRecursiveProgressionError(f"{field} must be an object")
    return value


def _optional_mapping(value: object, field: str) -> Mapping[str, Any] | None:
    if value is None:
        return None
    return _mapping(value, field)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise PublicRecursiveProgressionError(f"{field} must be non-empty trimmed text")
    return value


def _sha(value: object, field: str) -> str:
    text = _text(value, field)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise PublicRecursiveProgressionError(f"{field} must be lowercase SHA-256")
    return text


def _verified_sha(
    value: Mapping[str, Any],
    *,
    sha_field: str,
    field: str,
) -> str:
    snapshot = dict(_mapping(value, field))
    digest = _sha(snapshot.pop(sha_field, None), f"{field}.{sha_field}")
    if _canonical_sha256(snapshot) != digest:
        raise PublicRecursiveProgressionError(
            f"{field}.{sha_field} does not match canonical content"
        )
    return digest


def _same_limits(
    supplied: Mapping[str, Any] | None,
    expected: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = normalize_recursive_limits(supplied)
    if normalized != dict(expected):
        raise PublicRecursiveProgressionError(
            "recursive_limits differ from the validated planning ancestry"
        )
    return normalized


def _resolved_path(value: str | Path, *, field: str, directory: bool = False) -> str:
    try:
        path = Path(value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise PublicRecursiveProgressionError(f"{field} does not resolve") from exc
    if directory and not path.is_dir():
        raise PublicRecursiveProgressionError(f"{field} must be a directory")
    if not directory and not path.is_file():
        raise PublicRecursiveProgressionError(f"{field} must be a file")
    return str(path)


def _file_sha256(path: str | Path, *, field: str) -> str:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError as exc:
        raise PublicRecursiveProgressionError(f"{field} cannot be read") from exc


def _execution_projection(record: Mapping[str, Any]) -> dict[str, Any]:
    concrete = _mapping(record.get("concrete_execution"), "execution_record.concrete_execution")
    authorization = _mapping(
        concrete.get("preexecution_authorization"),
        "execution_record.concrete_execution.preexecution_authorization",
    )
    return {
        "action_id": _text(record.get("action_id"), "execution_record.action_id"),
        "action_type": _text(record.get("action_type"), "execution_record.action_type"),
        "action_version": _text(record.get("action_version"), "execution_record.action_version"),
        "request_sha256": _sha(record.get("request_sha256"), "execution_record.request_sha256"),
        "registry_sha256": _sha(record.get("registry_sha256"), "execution_record.registry_sha256"),
        "result_sha256": _sha(record.get("result_sha256"), "execution_record.result_sha256"),
        "execution_outcome": _text(record.get("execution_outcome"), "execution_record.execution_outcome"),
        "execution_success": record.get("execution_success"),
        "preexecution_authorization_verification_sha256": _sha(
            authorization.get("verification_sha256"),
            "preexecution_authorization.verification_sha256",
        ),
    }


def _planner_execution_pins(planning: Mapping[str, Any]) -> tuple[str, str]:
    inputs = _mapping(planning.get("validation_inputs"), "validation_inputs")
    state = _mapping(inputs.get("planner_program_state"), "validation_inputs.planner_program_state")
    binding = _mapping(
        state.get("public_recursive_planner_binding"),
        "planner_program_state.public_recursive_planner_binding",
    )
    request = _mapping(binding.get("execution_request"), "planner_binding.execution_request")
    return (
        _sha(request.get("sha256"), "planner_binding.execution_request.sha256"),
        _sha(binding.get("registry_sha256"), "planner_binding.registry_sha256"),
    )


def _reconstruct_execution(
    *,
    planning: Mapping[str, Any],
    reconstruction: Mapping[str, Any],
) -> dict[str, Any]:
    checkpoint = _mapping(planning.get("recursive_checkpoint"), "recursive_checkpoint")
    match = _mapping(checkpoint.get("candidate_match"), "checkpoint.candidate_match")
    checkpoint_sha = _sha(checkpoint.get("checkpoint_sha256"), "checkpoint.checkpoint_sha256")
    action_id = _text(match.get("candidate_action_id"), "candidate_match.candidate_action_id")
    action_class = _text(match.get("candidate_action_class"), "candidate_match.candidate_action_class")
    try:
        record = build_authenticated_recursive_execution_record(
            source_checkpoint_sha256=checkpoint_sha,
            expected_candidate_action_id=action_id,
            expected_candidate_action_class=action_class,
            adapter_id=_text(reconstruction.get("execution_adapter_id"), "execution_adapter_id"),
            repository_root=_text(reconstruction.get("repository_root"), "repository_root"),
            research_run=_text(reconstruction.get("research_run"), "research_run"),
            action_registry_path=_text(reconstruction.get("action_registry_path"), "action_registry_path"),
            request_path=_text(reconstruction.get("request_path"), "request_path"),
            action_report_path=_text(reconstruction.get("action_report_path"), "action_report_path"),
        )
    except ResearchLoopError as exc:
        raise PublicRecursiveProgressionError(
            "typed execution/authorization could not be reconstructed from immutable state"
        ) from exc
    planned_request_sha, planned_registry_sha = _planner_execution_pins(planning)
    if record.get("request_sha256") != planned_request_sha:
        raise PublicRecursiveProgressionError(
            "reconstructed execution request differs from the exact planning request"
        )
    if record.get("registry_sha256") != planned_registry_sha:
        raise PublicRecursiveProgressionError(
            "reconstructed execution registry differs from the exact planning registry"
        )
    expected_report_sha = _sha(
        reconstruction.get("action_report_sha256"),
        "reconstruction.action_report_sha256",
    )
    actual_report_sha = _file_sha256(
        _text(reconstruction.get("action_report_path"), "action_report_path"),
        field="action_report_path",
    )
    if actual_report_sha != expected_report_sha:
        raise PublicRecursiveProgressionError(
            "action report bytes changed after public progression publication"
        )
    return record


def _public_binding(
    *,
    planning: Mapping[str, Any],
    expected_limits: Mapping[str, Any],
    execution_record: Mapping[str, Any],
    execution_adapter_id: str,
    repository_root: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    request_path: str | Path,
    action_report_path: str | Path,
    transition_bundle_root: str | Path,
    program_state: Mapping[str, Any],
    previous_progression: Mapping[str, Any] | None,
) -> dict[str, Any]:
    report_path = _resolved_path(action_report_path, field="action_report_path")
    return {
        "policy_version": PUBLIC_RECURSIVE_PROGRESSION_BINDING_POLICY_VERSION,
        "validated_planning_context_sha256": planning["context_sha256"],
        "validated_planning_artifact_sha256": planning[
            "validated_planning_artifact"
        ]["validated_checkpoint_sha256"],
        "recursive_limits": dict(expected_limits),
        "execution_reconstruction": {
            "execution_adapter_id": _text(execution_adapter_id, "execution_adapter_id"),
            "repository_root": _resolved_path(repository_root, field="repository_root", directory=True),
            "research_run": _resolved_path(research_run, field="research_run", directory=True),
            "action_registry_path": _resolved_path(action_registry_path, field="action_registry_path"),
            "request_path": _resolved_path(request_path, field="request_path"),
            "action_report_path": report_path,
            "action_report_sha256": _file_sha256(report_path, field="action_report_path"),
            "transition_bundle_root": _resolved_path(
                transition_bundle_root,
                field="transition_bundle_root",
                directory=True,
            ),
            "program_state": copy.deepcopy(dict(program_state)),
            "previous_progression": (
                None
                if previous_progression is None
                else copy.deepcopy(dict(previous_progression))
            ),
            "verified_execution_record_sha256": _sha(
                execution_record.get("verification_record_sha256"),
                "execution_record.verification_record_sha256",
            ),
        },
        "caller_authored_execution_record_accepted": False,
        "execution_record_reconstructed_from_immutable_state": True,
        "progression_validation_reconstructs_execution_and_transition": True,
        "transition_bundle_independently_consumed": True,
        "scientific_authority_created_by_public_facade": False,
    }


def advance_public_recursive_cycle_after_verified_transition(
    *,
    validated_planning_context: Mapping[str, Any],
    recursive_limits: Mapping[str, Any],
    execution_adapter_id: str,
    repository_root: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    request_path: str | Path,
    action_report_path: str | Path,
    transition_bundle_root: str | Path,
    program_state: Mapping[str, Any],
    previous_progression: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Advance a cycle without any caller-authored execution-evidence parameter."""
    planning = validate_public_recursive_planning_context(validated_planning_context)
    checkpoint = _mapping(planning.get("recursive_checkpoint"), "recursive_checkpoint")
    expected_limits = _mapping(planning.get("recursive_limits"), "recursive_limits")
    _same_limits(recursive_limits, expected_limits)
    if checkpoint.get("checkpoint_status") != "explicit_authorization_required":
        raise PublicRecursiveProgressionError(
            "execution requires an authorization-open validated checkpoint"
        )

    reconstruction_seed = {
        "execution_adapter_id": execution_adapter_id,
        "repository_root": _resolved_path(repository_root, field="repository_root", directory=True),
        "research_run": _resolved_path(research_run, field="research_run", directory=True),
        "action_registry_path": _resolved_path(action_registry_path, field="action_registry_path"),
        "request_path": _resolved_path(request_path, field="request_path"),
        "action_report_path": _resolved_path(action_report_path, field="action_report_path"),
        "action_report_sha256": _file_sha256(action_report_path, field="action_report_path"),
    }
    execution_record = _reconstruct_execution(
        planning=planning,
        reconstruction=reconstruction_seed,
    )

    inputs = _mapping(planning.get("validation_inputs"), "validation_inputs")
    fresh_plan = _mapping(inputs.get("fresh_plan"), "validation_inputs.fresh_plan")
    source_graph = _mapping(
        inputs.get("source_evaluated_graph"),
        "validation_inputs.source_evaluated_graph",
    )
    try:
        progression = _advance_recursive_cycle_after_verified_transition(
            authorization_checkpoint=checkpoint,
            verified_execution_record=execution_record,
            transition_bundle_root=transition_bundle_root,
            fresh_plan=fresh_plan,
            program_state=program_state,
            previous_progression=previous_progression,
            source_evaluated_graph=source_graph,
            require_authorization_provenance=True,
        )
    except ResearchLoopError as exc:
        raise PublicRecursiveProgressionError(
            "authenticated transition progression failed planning/execution/graph ancestry"
        ) from exc

    value = dict(progression)
    value["public_progression_binding"] = _public_binding(
        planning=planning,
        expected_limits=expected_limits,
        execution_record=execution_record,
        execution_adapter_id=execution_adapter_id,
        repository_root=repository_root,
        research_run=research_run,
        action_registry_path=action_registry_path,
        request_path=request_path,
        action_report_path=action_report_path,
        transition_bundle_root=transition_bundle_root,
        program_state=program_state,
        previous_progression=previous_progression,
    )
    value.pop("progression_sha256", None)
    value["progression_sha256"] = _canonical_sha256(value)
    return value


def validate_public_recursive_progression(
    progression: Mapping[str, Any],
    *,
    validated_planning_context: Mapping[str, Any],
    recursive_limits: Mapping[str, Any],
) -> dict[str, Any]:
    """Reconstruct execution and transition before accepting a persisted progression."""
    digest = _verified_sha(
        progression,
        sha_field="progression_sha256",
        field="progression",
    )
    planning = validate_public_recursive_planning_context(validated_planning_context)
    expected_limits = _mapping(planning.get("recursive_limits"), "recursive_limits")
    _same_limits(recursive_limits, expected_limits)
    binding = _mapping(
        progression.get("public_progression_binding"),
        "progression.public_progression_binding",
    )
    if binding.get("policy_version") != PUBLIC_RECURSIVE_PROGRESSION_BINDING_POLICY_VERSION:
        raise PublicRecursiveProgressionError("progression public binding policy_version drifted")
    if binding.get("validated_planning_context_sha256") != planning["context_sha256"]:
        raise PublicRecursiveProgressionError(
            "progression is bound to a different validated planning context"
        )
    if binding.get("recursive_limits") != dict(expected_limits):
        raise PublicRecursiveProgressionError(
            "progression recursive limits differ from validated planning context"
        )
    if binding.get("caller_authored_execution_record_accepted") is not False:
        raise PublicRecursiveProgressionError(
            "public progression cannot accept caller-authored execution evidence"
        )
    if binding.get("execution_record_reconstructed_from_immutable_state") is not True:
        raise PublicRecursiveProgressionError(
            "progression lacks immutable execution reconstruction provenance"
        )
    if binding.get("progression_validation_reconstructs_execution_and_transition") is not True:
        raise PublicRecursiveProgressionError(
            "progression validation does not promise full execution/transition reconstruction"
        )

    checkpoint = _mapping(planning.get("recursive_checkpoint"), "recursive_checkpoint")
    ancestry = _mapping(progression.get("ancestry"), "progression.ancestry")
    if ancestry.get("authorization_checkpoint_sha256") != checkpoint.get("checkpoint_sha256"):
        raise PublicRecursiveProgressionError(
            "progression is bound to a different authorization checkpoint"
        )
    reconstruction = _mapping(
        binding.get("execution_reconstruction"),
        "public_progression_binding.execution_reconstruction",
    )
    execution_record = _reconstruct_execution(
        planning=planning,
        reconstruction=reconstruction,
    )
    execution_record_sha = _sha(
        execution_record.get("verification_record_sha256"),
        "reconstructed_execution.verification_record_sha256",
    )
    if reconstruction.get("verified_execution_record_sha256") != execution_record_sha:
        raise PublicRecursiveProgressionError(
            "published execution reconstruction SHA differs from immutable reconstruction"
        )
    if ancestry.get("verified_execution_record_sha256") != execution_record_sha:
        raise PublicRecursiveProgressionError(
            "progression ancestry does not bind the reconstructed execution record"
        )
    supplied_projection = _mapping(
        progression.get("verified_execution"),
        "progression.verified_execution",
    )
    if dict(supplied_projection) != _execution_projection(execution_record):
        raise PublicRecursiveProgressionError(
            "published verified_execution differs from immutable execution reconstruction"
        )

    inputs = _mapping(planning.get("validation_inputs"), "validation_inputs")
    source_graph = _mapping(inputs.get("source_evaluated_graph"), "source_evaluated_graph")
    fresh_plan = _mapping(inputs.get("fresh_plan"), "fresh_plan")
    program_state = _mapping(reconstruction.get("program_state"), "reconstruction.program_state")
    previous_progression = _optional_mapping(
        reconstruction.get("previous_progression"),
        "reconstruction.previous_progression",
    )
    try:
        inner = _advance_recursive_cycle_after_verified_transition(
            authorization_checkpoint=checkpoint,
            verified_execution_record=execution_record,
            transition_bundle_root=_text(
                reconstruction.get("transition_bundle_root"),
                "reconstruction.transition_bundle_root",
            ),
            fresh_plan=fresh_plan,
            program_state=program_state,
            previous_progression=previous_progression,
            source_evaluated_graph=source_graph,
            require_authorization_provenance=True,
        )
    except ResearchLoopError as exc:
        raise PublicRecursiveProgressionError(
            "persisted progression failed deterministic execution/transition reconstruction"
        ) from exc
    rebuilt = dict(inner)
    rebuilt["public_progression_binding"] = copy.deepcopy(dict(binding))
    rebuilt.pop("progression_sha256", None)
    rebuilt["progression_sha256"] = _canonical_sha256(rebuilt)
    if rebuilt != dict(progression):
        raise PublicRecursiveProgressionError(
            "persisted progression differs from deterministic public reconstruction"
        )

    return {
        "progression_sha256": digest,
        "progression_status": progression.get("progression_status"),
        "cycle_index": progression.get("cycle_index"),
        "validated_planning_context_sha256": planning["context_sha256"],
        "recursive_limits": dict(expected_limits),
        "verified_execution_record_sha256": execution_record_sha,
        "execution_and_transition_deterministically_reconstructed": True,
        "caller_authored_execution_record_accepted": False,
    }


def _bind_rediagnosis_to_progression_execution(
    *,
    current_discrepancy_report: Mapping[str, Any],
    progression: Mapping[str, Any],
) -> None:
    bindings = _mapping(
        current_discrepancy_report.get("input_bindings"),
        "current_discrepancy_report.input_bindings",
    )
    request = _mapping(bindings.get("execution_request"), "current.input_bindings.execution_request")
    result = _mapping(bindings.get("solver_result"), "current.input_bindings.solver_result")
    action_report = _mapping(
        bindings.get("model_action_report"),
        "current.input_bindings.model_action_report",
    )
    execution = _mapping(progression.get("verified_execution"), "progression.verified_execution")
    if request.get("sha256") != execution.get("request_sha256"):
        raise PublicRecursiveProgressionError(
            "re-diagnosis request differs from the execution completed by this progression"
        )
    if result.get("sha256") != execution.get("result_sha256"):
        raise PublicRecursiveProgressionError(
            "re-diagnosis result differs from the execution completed by this progression"
        )
    public_binding = _mapping(
        progression.get("public_progression_binding"),
        "progression.public_progression_binding",
    )
    reconstruction = _mapping(
        public_binding.get("execution_reconstruction"),
        "public_progression_binding.execution_reconstruction",
    )
    if action_report.get("sha256") != reconstruction.get("action_report_sha256"):
        raise PublicRecursiveProgressionError(
            "re-diagnosis action report differs from the exact progression execution report"
        )


def complete_public_recursive_cycle_with_rediagnosis(
    *,
    validated_planning_context: Mapping[str, Any],
    progression: Mapping[str, Any],
    current_discrepancy_report: Mapping[str, Any],
    previous_discrepancy_report: Mapping[str, Any],
    evaluated_graph: Mapping[str, Any],
    recursive_limits: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate fresh re-diagnosis against the exact authenticated successor state."""
    planning = validate_public_recursive_planning_context(validated_planning_context)
    progression_check = validate_public_recursive_progression(
        progression,
        validated_planning_context=validated_planning_context,
        recursive_limits=recursive_limits,
    )
    if progression.get("progression_status") != "re_diagnosis_required":
        raise PublicRecursiveProgressionError(
            "progression does not require a fresh discrepancy diagnosis"
        )
    progression_ancestry = _mapping(progression.get("ancestry"), "progression.ancestry")
    graph_sha = _canonical_sha256(evaluated_graph)
    if progression_ancestry.get("evaluated_graph_canonical_sha256") != graph_sha:
        raise PublicRecursiveProgressionError(
            "re-diagnosis evaluated graph differs from the authenticated successor graph"
        )

    inputs = _mapping(planning.get("validation_inputs"), "validation_inputs")
    source_report = _mapping(
        inputs.get("source_discrepancy_report"),
        "validation_inputs.source_discrepancy_report",
    )
    previous_sha = _verified_sha(
        previous_discrepancy_report,
        sha_field="report_sha256",
        field="previous_discrepancy_report",
    )
    if (
        previous_sha != source_report.get("report_sha256")
        or dict(previous_discrepancy_report) != dict(source_report)
    ):
        raise PublicRecursiveProgressionError(
            "re-diagnosis previous report differs from validated planning source"
        )
    try:
        current_check = validate_public_recursive_discrepancy_report(
            current_discrepancy_report,
            evaluated_graph=evaluated_graph,
            previous_report=previous_discrepancy_report,
        )
    except ResearchLoopError as exc:
        raise PublicRecursiveProgressionError(
            "current discrepancy failed public physics/provenance reconstruction"
        ) from exc
    _bind_rediagnosis_to_progression_execution(
        current_discrepancy_report=current_discrepancy_report,
        progression=progression,
    )
    current_sha = _sha(
        current_check.get("report_sha256"),
        "validated_current_discrepancy_report.report_sha256",
    )
    if current_sha == previous_sha:
        raise PublicRecursiveProgressionError(
            "re-diagnosis cannot reuse the previous discrepancy report"
        )
    progression_target = _mapping(progression.get("target"), "progression.target")
    current_target = _mapping(current_discrepancy_report.get("target"), "current.target")
    previous_target = _mapping(previous_discrepancy_report.get("target"), "previous.target")
    for field in ("graph_id", "node_id", "node_type", "statement"):
        if current_target.get(field) != progression_target.get(field):
            raise PublicRecursiveProgressionError(
                f"current re-diagnosis target differs from authenticated progression: {field}"
            )
    for field in ("node_id", "node_type", "statement"):
        if current_target.get(field) != previous_target.get(field):
            raise PublicRecursiveProgressionError(
                f"stable recursive target identity changed: {field}"
            )
    next_handoff = build_public_recursive_discrepancy_planning_handoff(
        current_discrepancy_report,
        evaluated_graph=evaluated_graph,
        previous_discrepancy_report=previous_discrepancy_report,
    )
    result: dict[str, Any] = {
        "schema_version": PUBLIC_RECURSIVE_REDIAGNOSIS_SCHEMA_VERSION,
        "policy_version": PUBLIC_RECURSIVE_REDIAGNOSIS_POLICY_VERSION,
        "cycle_id": progression.get("cycle_id"),
        "cycle_index": progression.get("cycle_index"),
        "completion_status": "next_planning_handoff_ready",
        "target": dict(current_target),
        "ancestry": {
            "validated_planning_context_sha256": planning["context_sha256"],
            "progression_sha256": progression_check["progression_sha256"],
            "previous_discrepancy_report_sha256": previous_sha,
            "current_discrepancy_report_sha256": current_sha,
            "evaluated_graph_canonical_sha256": graph_sha,
            "verified_execution_record_sha256": progression_check[
                "verified_execution_record_sha256"
            ],
            "next_planning_handoff_sha256": next_handoff["handoff_sha256"],
        },
        "validated_rediagnosis": {
            "report_sha256": current_sha,
            "iteration_index": current_check.get("iteration_index"),
            "diagnosis_types": list(current_check.get("diagnosis_types", [])),
            "physics_hardening_verified": True,
            "provenance_hardening_verified": True,
            "authenticated_successor_graph_binding_verified": True,
            "completed_execution_binding_verified": True,
            "scientific_status_changed": False,
            "automatic_execution_authorized": False,
        },
        "next_planning_handoff": next_handoff,
        "recursive_limits": dict(planning["recursive_limits"]),
        "autonomy_boundary": {
            "scientific_evidence_created": False,
            "epistemic_edge_created": False,
            "planner_candidate_created": False,
            "authorization_granted": False,
            "request_compiled": False,
            "execution_performed": False,
            "automatic_execution_authorized": False,
            "synthetic_empirical_measurement_created": False,
            "scientific_status_changed": False,
        },
    }
    result["completion_sha256"] = _canonical_sha256(result)
    return result


def build_public_recursive_replay_manifest(
    *,
    cycle1_planning_context: Mapping[str, Any],
    cycle1_progression: Mapping[str, Any],
    cycle1_completion: Mapping[str, Any],
    cycle2_planning_context: Mapping[str, Any],
    recursive_limits: Mapping[str, Any],
) -> dict[str, Any]:
    """Build machine-readable evidence for one two-cycle public composition replay."""
    c1 = validate_public_recursive_planning_context(cycle1_planning_context)
    c2 = validate_public_recursive_planning_context(cycle2_planning_context)
    limits = _same_limits(
        recursive_limits,
        _mapping(c1["recursive_limits"], "cycle1 limits"),
    )
    if dict(c2["recursive_limits"]) != limits:
        raise PublicRecursiveProgressionError(
            "cycle2 recursive limits differ from cycle1 ancestry"
        )
    progression_check = validate_public_recursive_progression(
        cycle1_progression,
        validated_planning_context=cycle1_planning_context,
        recursive_limits=recursive_limits,
    )
    progression_sha = progression_check["progression_sha256"]
    completion_sha = _verified_sha(
        cycle1_completion,
        sha_field="completion_sha256",
        field="cycle1_completion",
    )
    cp1 = _mapping(c1["recursive_checkpoint"], "cycle1 checkpoint")
    cp2 = _mapping(c2["recursive_checkpoint"], "cycle2 checkpoint")
    if cp1.get("cycle_index") != 1 or cp2.get("cycle_index") != 2:
        raise PublicRecursiveProgressionError(
            "public replay requires exact cycle indexes one then two"
        )
    if cp2.get("ancestry", {}).get("previous_checkpoint_sha256") != cp1.get("checkpoint_sha256"):
        raise PublicRecursiveProgressionError(
            "cycle2 checkpoint does not descend from exact cycle1 checkpoint"
        )
    p1 = _mapping(c1["validation_inputs"], "cycle1 inputs")
    p2 = _mapping(c2["validation_inputs"], "cycle2 inputs")
    plan1 = _mapping(p1.get("fresh_plan"), "cycle1 fresh_plan")
    plan2 = _mapping(p2.get("fresh_plan"), "cycle2 fresh_plan")
    plan1_sha = _sha(plan1.get("plan_sha256"), "cycle1 plan_sha256")
    plan2_sha = _sha(plan2.get("plan_sha256"), "cycle2 plan_sha256")
    if plan1_sha == plan2_sha:
        raise PublicRecursiveProgressionError("cycle2 stale-plan reuse detected")
    science = _mapping(
        cycle1_progression.get("scientific_state_comparison"),
        "scientific_state_comparison",
    )
    base = _mapping(science.get("base"), "scientific_state_comparison.base")
    successor = _mapping(science.get("successor"), "scientific_state_comparison.successor")
    if base.get("fingerprint_sha256") != successor.get("fingerprint_sha256"):
        raise PublicRecursiveProgressionError(
            "diagnostic transition unexpectedly changed verified target scientific state"
        )
    if science.get("graph_version_bookkeeping_counts_as_new_information") is not False:
        raise PublicRecursiveProgressionError(
            "graph-version churn was incorrectly counted as scientific information"
        )
    result: dict[str, Any] = {
        "schema_version": PUBLIC_RECURSIVE_REPLAY_MANIFEST_SCHEMA_VERSION,
        "policy_version": PUBLIC_RECURSIVE_REPLAY_MANIFEST_POLICY_VERSION,
        "acceptance_status": "public_api_two_cycle_replay_reached_bounded_second_cycle",
        "cycle1": {
            "planning_context_sha256": c1["context_sha256"],
            "validated_planning_artifact_sha256": c1["validated_planning_artifact"]["validated_checkpoint_sha256"],
            "recursive_checkpoint_sha256": cp1["checkpoint_sha256"],
            "fresh_plan_sha256": plan1_sha,
            "progression_sha256": progression_sha,
            "completion_sha256": completion_sha,
            "progression_status": cycle1_progression.get("progression_status"),
        },
        "cycle2": {
            "planning_context_sha256": c2["context_sha256"],
            "validated_planning_artifact_sha256": c2["validated_planning_artifact"]["validated_checkpoint_sha256"],
            "recursive_checkpoint_sha256": cp2["checkpoint_sha256"],
            "fresh_plan_sha256": plan2_sha,
            "checkpoint_status": cp2.get("checkpoint_status"),
            "predecessor_checkpoint_sha256": cp2.get("ancestry", {}).get("previous_checkpoint_sha256"),
        },
        "recursive_limits": limits,
        "scientific_state": {
            "cycle1_target_base_fingerprint_sha256": base.get("fingerprint_sha256"),
            "cycle1_target_successor_fingerprint_sha256": successor.get("fingerprint_sha256"),
            "diagnostic_transition_changed_verified_target_state": False,
            "graph_version_churn_counted_as_scientific_information": False,
        },
        "scientific_boundary": {
            "repository_owned_audited_heat_solver_used": True,
            "immutable_heat_execution_ledger_replayed": True,
            "pinned_heat_domain_verifier_used": True,
            "synthetic_empirical_measurement_used": False,
            "caller_authored_execution_record_used": False,
            "empirical_material_or_process_validation_established": False,
            "hypothesis_truth_established": False,
            "positive_scientific_closeout_granted": False,
            "physical_experiment_executed": False,
        },
    }
    result["manifest_sha256"] = _canonical_sha256(result)
    return result


advance_recursive_cycle_after_verified_transition = advance_public_recursive_cycle_after_verified_transition
complete_recursive_cycle_with_rediagnosis = complete_public_recursive_cycle_with_rediagnosis


__all__ = [
    "PUBLIC_RECURSIVE_PROGRESSION_BINDING_POLICY_VERSION",
    "PUBLIC_RECURSIVE_REDIAGNOSIS_POLICY_VERSION",
    "PUBLIC_RECURSIVE_REDIAGNOSIS_SCHEMA_VERSION",
    "PUBLIC_RECURSIVE_REPLAY_MANIFEST_POLICY_VERSION",
    "PUBLIC_RECURSIVE_REPLAY_MANIFEST_SCHEMA_VERSION",
    "PublicRecursiveProgressionError",
    "advance_public_recursive_cycle_after_verified_transition",
    "advance_recursive_cycle_after_verified_transition",
    "build_public_recursive_replay_manifest",
    "complete_public_recursive_cycle_with_rediagnosis",
    "complete_recursive_cycle_with_rediagnosis",
    "validate_public_recursive_progression",
]
