from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, text: str) -> None:
    (ROOT / rel).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


controller_path = "src/materials_data_analyzer/research_loop/recursive_research_cycle_controller.py"
controller = read(controller_path)
controller = replace_once(
    controller,
    "def build_recursive_research_cycle_checkpoint(\n",
    "def _build_recursive_research_cycle_checkpoint(\n",
    label="controller builder",
)
controller = replace_once(
    controller,
    "def validate_recursive_research_cycle_checkpoint(\n",
    "def _validate_recursive_research_cycle_checkpoint(\n",
    label="controller validator",
)
controller = replace_once(
    controller,
    "    rebuilt = build_recursive_research_cycle_checkpoint(\n",
    "    rebuilt = _build_recursive_research_cycle_checkpoint(\n",
    label="controller validator rebuild",
)
controller = controller.replace('    "build_recursive_research_cycle_checkpoint",\n', "")
controller = controller.replace('    "validate_recursive_research_cycle_checkpoint",\n', "")
write(controller_path, controller)

planning_path = "src/materials_data_analyzer/research_loop/validated_recursive_cycle_planning.py"
planning = read(planning_path)
planning = replace_once(
    planning,
    "from .recursive_research_cycle_controller import (\n    build_recursive_research_cycle_checkpoint,\n)\n",
    "from .recursive_research_cycle_controller import (\n    _build_recursive_research_cycle_checkpoint,\n)\n",
    label="validated planning private import",
)
planning = replace_once(
    planning,
    "    checkpoint = build_recursive_research_cycle_checkpoint(\n",
    "    checkpoint = _build_recursive_research_cycle_checkpoint(\n",
    label="validated planning private call",
)
validator_code = r'''


def validate_validated_recursive_planning_checkpoint(
    artifact: Mapping[str, Any],
    *,
    planning_handoff: Mapping[str, Any],
    source_discrepancy_report: Mapping[str, Any],
    source_evaluated_graph: Mapping[str, Any],
    fresh_plan: Mapping[str, Any],
    planner_program_state: Mapping[str, Any],
    source_hypothesis_portfolio: Mapping[str, Any] | None = None,
    previous_discrepancy_report: Mapping[str, Any] | None = None,
    candidate_match: Mapping[str, Any] | None = None,
    planner_critic_report: Mapping[str, Any] | None = None,
    planner_reasoning_proposal: Mapping[str, Any] | None = None,
    budget_units: float = 8.0,
    minimum_utility: float = 0.01,
    previous_checkpoint: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Rebuild the public planning artifact from exact source inputs."""
    if not isinstance(artifact, Mapping):
        raise ValidatedRecursivePlanningError("validated planning artifact must be an object")
    supplied = dict(artifact)
    if supplied.get("schema_version") != VALIDATED_RECURSIVE_PLANNING_SCHEMA_VERSION:
        raise ValidatedRecursivePlanningError("validated planning artifact schema_version drifted")
    if supplied.get("policy_version") != VALIDATED_RECURSIVE_PLANNING_POLICY_VERSION:
        raise ValidatedRecursivePlanningError("validated planning artifact policy_version drifted")
    embedded = supplied.get("validated_checkpoint_sha256")
    if not isinstance(embedded, str) or len(embedded) != 64:
        raise ValidatedRecursivePlanningError(
            "validated planning artifact SHA-256 is malformed"
        )
    unsigned = dict(supplied)
    unsigned.pop("validated_checkpoint_sha256", None)
    if _canonical_sha256(unsigned) != embedded:
        raise ValidatedRecursivePlanningError(
            "validated planning artifact SHA-256 does not match canonical content"
        )
    rebuilt = build_validated_recursive_planning_checkpoint(
        planning_handoff=planning_handoff,
        source_discrepancy_report=source_discrepancy_report,
        source_evaluated_graph=source_evaluated_graph,
        fresh_plan=fresh_plan,
        planner_program_state=planner_program_state,
        source_hypothesis_portfolio=source_hypothesis_portfolio,
        previous_discrepancy_report=previous_discrepancy_report,
        candidate_match=candidate_match,
        planner_critic_report=planner_critic_report,
        planner_reasoning_proposal=planner_reasoning_proposal,
        budget_units=budget_units,
        minimum_utility=minimum_utility,
        previous_checkpoint=previous_checkpoint,
    )
    if rebuilt != supplied:
        raise ValidatedRecursivePlanningError(
            "validated planning artifact differs from deterministic reconstruction"
        )
    checkpoint = rebuilt.get("recursive_checkpoint")
    if not isinstance(checkpoint, Mapping):
        raise ValidatedRecursivePlanningError(
            "validated planning artifact omitted recursive checkpoint"
        )
    return {
        "validated_checkpoint_sha256": embedded,
        "recursive_checkpoint": dict(checkpoint),
        "handoff_verification": dict(rebuilt["handoff_verification"]),
        "planner_verification": dict(rebuilt["planner_verification"]),
        "authorization_granted": False,
        "execution_performed": False,
        "scientific_status_changed": False,
    }
'''
planning = replace_once(
    planning,
    "\n\n__all__ = [\n",
    validator_code + "\n\n__all__ = [\n",
    label="validated planning validator insertion",
)
planning = replace_once(
    planning,
    '    "build_validated_recursive_planning_checkpoint",\n',
    '    "build_validated_recursive_planning_checkpoint",\n'
    '    "validate_validated_recursive_planning_checkpoint",\n',
    label="validated planning export",
)
write(planning_path, planning)

execution_module_path = (
    "src/materials_data_analyzer/research_loop/"
    "recursive_authorized_execution_evidence.py"
)
execution_module = r'''"""Independent typed-execution evidence for recursive research progression.

The public recursive controller never accepts a caller-authored verified execution
record. This adapter reconstructs one only from an existing typed request, the live
action registry, the domain-pinned verifier, and the immutable research ledger.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .action_registry import describe_action, load_action_registry
from .heat_conduction_action import (
    ACTION_TYPE as HEAT_ACTION_TYPE,
    ACTION_VERSION as HEAT_ACTION_VERSION,
    verify_heat_conduction_action_report_pinned,
)
from .kernel import ResearchLoopError, load_research_state
from .nist_pinned_verifier import verify_nist_structural_design_report_pinned
from .nist_structural_design_action import (
    ACTION_TYPE as NIST_ACTION_TYPE,
    ACTION_VERSION as NIST_ACTION_VERSION,
)

VERIFIED_EXECUTION_RECORD_SCHEMA_VERSION = "1.0"
RECURSIVE_EXECUTION_EVIDENCE_POLICY_VERSION = "1.0"

_ADAPTERS = {
    "reference-heat-conduction": (HEAT_ACTION_TYPE, HEAT_ACTION_VERSION),
    "nist-ambench-process-characterization": (NIST_ACTION_TYPE, NIST_ACTION_VERSION),
}


class RecursiveAuthorizedExecutionEvidenceError(ResearchLoopError):
    """Raised when typed execution cannot be independently reconstructed."""


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RecursiveAuthorizedExecutionEvidenceError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _load_json_record(path: Path, *, field: str) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecursiveAuthorizedExecutionEvidenceError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise RecursiveAuthorizedExecutionEvidenceError(f"{field} root must be an object")
    return value, {
        "path": str(path),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _resolve_file(value: str | Path, *, field: str) -> Path:
    try:
        path = Path(value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise RecursiveAuthorizedExecutionEvidenceError(
            f"{field} does not resolve to an existing file"
        ) from exc
    if not path.is_file():
        raise RecursiveAuthorizedExecutionEvidenceError(f"{field} must be a regular file")
    return path


def _resolve_directory(value: str | Path, *, field: str) -> Path:
    try:
        path = Path(value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise RecursiveAuthorizedExecutionEvidenceError(
            f"{field} does not resolve to an existing directory"
        ) from exc
    if not path.is_dir():
        raise RecursiveAuthorizedExecutionEvidenceError(f"{field} must be a directory")
    return path


def build_authenticated_recursive_execution_record(
    *,
    source_checkpoint_sha256: str,
    expected_candidate_action_id: str,
    expected_candidate_action_class: str,
    adapter_id: str,
    repository_root: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    request_path: str | Path,
    action_report_path: str | Path,
) -> dict[str, Any]:
    """Reconstruct one recursive execution record from verified repository artifacts."""
    if adapter_id not in _ADAPTERS:
        raise RecursiveAuthorizedExecutionEvidenceError(
            "recursive execution evidence supports only independently pinned heat/NIST adapters"
        )
    if (
        not isinstance(source_checkpoint_sha256, str)
        or len(source_checkpoint_sha256) != 64
        or any(ch not in "0123456789abcdef" for ch in source_checkpoint_sha256)
    ):
        raise RecursiveAuthorizedExecutionEvidenceError(
            "source_checkpoint_sha256 must be lowercase SHA-256"
        )
    if not isinstance(expected_candidate_action_id, str) or not expected_candidate_action_id.strip():
        raise RecursiveAuthorizedExecutionEvidenceError(
            "expected_candidate_action_id must be non-empty"
        )
    if (
        not isinstance(expected_candidate_action_class, str)
        or not expected_candidate_action_class.strip()
    ):
        raise RecursiveAuthorizedExecutionEvidenceError(
            "expected_candidate_action_class must be non-empty"
        )

    root = _resolve_directory(repository_root, field="repository_root")
    run = _resolve_directory(research_run, field="research_run")
    registry_path = _resolve_file(action_registry_path, field="action_registry_path")
    request_file = _resolve_file(request_path, field="request_path")
    report_file = _resolve_file(action_report_path, field="action_report_path")
    request, request_record = _load_json_record(request_file, field="typed execution request")

    concrete_action_type, concrete_action_version = _ADAPTERS[adapter_id]
    if request.get("action_id") != expected_candidate_action_id:
        raise RecursiveAuthorizedExecutionEvidenceError(
            "typed request action_id differs from recursive planner-selected candidate"
        )
    if request.get("action_type") != concrete_action_type:
        raise RecursiveAuthorizedExecutionEvidenceError(
            "typed request action_type differs from the selected execution adapter"
        )
    if request.get("action_version") != concrete_action_version:
        raise RecursiveAuthorizedExecutionEvidenceError(
            "typed request action_version differs from the selected execution adapter"
        )

    registry = load_action_registry(registry_path, repository_root=root)
    contract = describe_action(registry, concrete_action_type)
    if contract.get("version") != concrete_action_version:
        raise RecursiveAuthorizedExecutionEvidenceError(
            "live registry action version differs from typed execution adapter"
        )
    if contract.get("category") != expected_candidate_action_class:
        raise RecursiveAuthorizedExecutionEvidenceError(
            "live registry action category differs from planner-selected action class"
        )
    if request.get("expected_registry_sha256") != registry.get("registry_sha256"):
        raise RecursiveAuthorizedExecutionEvidenceError(
            "typed request is not pinned to the live execution registry"
        )

    request_run = Path(str(request.get("research_run"))).expanduser()
    if not request_run.is_absolute():
        request_run = request_file.parent / request_run
    if request_run.resolve(strict=True) != run:
        raise RecursiveAuthorizedExecutionEvidenceError(
            "typed request research_run differs from supplied immutable ledger"
        )
    request_registry = Path(str(request.get("registry"))).expanduser()
    if not request_registry.is_absolute():
        request_registry = request_file.parent / request_registry
    if request_registry.resolve(strict=True) != registry_path:
        raise RecursiveAuthorizedExecutionEvidenceError(
            "typed request registry path differs from supplied live registry"
        )

    if adapter_id == "reference-heat-conduction":
        verified = verify_heat_conduction_action_report_pinned(
            report_file,
            request_value=request,
            request_path=request_file,
            request_record=request_record,
        )
        if (
            verified.get("deterministic_recomputation_verified") is not True
            or verified.get("ledger_artifact_binding_verified") is not True
        ):
            raise RecursiveAuthorizedExecutionEvidenceError(
                "heat domain verifier did not establish deterministic ledger-bound execution"
            )
        result_sha256 = verified.get("solver_result_sha256")
    else:
        verified = verify_nist_structural_design_report_pinned(
            report_file,
            request_value=request,
            request_path=request_file,
            request_record=request_record,
        )
        if verified.get("valid") is not True:
            raise RecursiveAuthorizedExecutionEvidenceError(
                "NIST domain verifier did not establish a valid ledger-bound execution"
            )
        report_value, _ = _load_json_record(report_file, field="NIST action report")
        output = report_value.get("output")
        if not isinstance(output, Mapping):
            raise RecursiveAuthorizedExecutionEvidenceError(
                "NIST verified report omitted output binding"
            )
        result_sha256 = output.get("sha256")

    if (
        not isinstance(result_sha256, str)
        or len(result_sha256) != 64
        or any(ch not in "0123456789abcdef" for ch in result_sha256)
    ):
        raise RecursiveAuthorizedExecutionEvidenceError(
            "domain verifier did not yield one canonical result artifact SHA-256"
        )

    state = load_research_state(run)
    actions = state.get("actions")
    if not isinstance(actions, list):
        raise RecursiveAuthorizedExecutionEvidenceError("research action ledger is malformed")
    matches = [
        item
        for item in actions
        if isinstance(item, Mapping)
        and item.get("action_id") == expected_candidate_action_id
    ]
    if len(matches) != 1:
        raise RecursiveAuthorizedExecutionEvidenceError(
            "research ledger must contain exactly one planner-selected typed action"
        )
    action = matches[0]
    if action.get("action_type") != concrete_action_type:
        raise RecursiveAuthorizedExecutionEvidenceError(
            "research ledger concrete action type differs from verified request"
        )
    outcome = action.get("status")
    if outcome not in {"completed", "rejected", "failed"}:
        raise RecursiveAuthorizedExecutionEvidenceError(
            "research ledger action status is not a terminal execution outcome"
        )

    record: dict[str, Any] = {
        "schema_version": VERIFIED_EXECUTION_RECORD_SCHEMA_VERSION,
        "policy_version": RECURSIVE_EXECUTION_EVIDENCE_POLICY_VERSION,
        "source_checkpoint_sha256": source_checkpoint_sha256,
        "authorization_status": "explicit_request_authorized_by_existing_chain",
        "independent_verification_status": "verified_by_existing_chain",
        "action_id": expected_candidate_action_id,
        "action_type": expected_candidate_action_class,
        "action_version": concrete_action_version,
        "request_sha256": request_record["sha256"],
        "registry_sha256": registry["registry_sha256"],
        "result_sha256": result_sha256,
        "execution_outcome": outcome,
        "execution_success": outcome == "completed",
        "concrete_execution": {
            "adapter_id": adapter_id,
            "action_type": concrete_action_type,
            "action_version": concrete_action_version,
            "report_path": str(report_file),
            "research_ledger_sha256": state["ledger_sha256"],
            "domain_verifier_result_sha256": _canonical_sha256(verified),
            "domain_verifier_recomputed": True,
            "ledger_artifact_binding_reverified": True,
        },
        "scientific_evidence_upgraded": False,
    }
    record["verification_record_sha256"] = _canonical_sha256(record)
    return record


__all__ = [
    "RECURSIVE_EXECUTION_EVIDENCE_POLICY_VERSION",
    "RecursiveAuthorizedExecutionEvidenceError",
    "build_authenticated_recursive_execution_record",
]
'''
write(execution_module_path, execution_module)

evidence_path = "src/materials_data_analyzer/research_loop/recursive_research_cycle_evidence.py"
evidence = read(evidence_path)
import_anchor = (
    "from .recursive_research_cycle_controller import (\n"
    "    RECURSIVE_CYCLE_POLICY_VERSION,\n"
    "    RECURSIVE_CYCLE_SCHEMA_VERSION,\n"
    ")\n"
)
new_imports = import_anchor + (
    "from .recursive_authorized_execution_evidence import (\n"
    "    build_authenticated_recursive_execution_record,\n"
    ")\n"
    "from .validated_recursive_cycle_planning import (\n"
    "    validate_validated_recursive_planning_checkpoint,\n"
    ")\n"
)
evidence = replace_once(
    evidence,
    import_anchor,
    new_imports,
    label="evidence hardened imports",
)
evidence = replace_once(
    evidence,
    "def advance_recursive_cycle_after_verified_transition(\n",
    "def _advance_recursive_cycle_after_verified_transition(\n",
    label="evidence private core rename",
)

public_wrapper = r'''


def advance_recursive_cycle_after_verified_transition(
    *,
    validated_planning_artifact: Mapping[str, Any],
    planning_handoff: Mapping[str, Any],
    source_discrepancy_report: Mapping[str, Any],
    source_evaluated_graph: Mapping[str, Any],
    fresh_plan: Mapping[str, Any],
    planner_program_state: Mapping[str, Any],
    source_hypothesis_portfolio: Mapping[str, Any] | None = None,
    previous_discrepancy_report: Mapping[str, Any] | None = None,
    candidate_match: Mapping[str, Any] | None = None,
    planner_critic_report: Mapping[str, Any] | None = None,
    planner_reasoning_proposal: Mapping[str, Any] | None = None,
    budget_units: float = 8.0,
    minimum_utility: float = 0.01,
    previous_checkpoint: Mapping[str, Any] | None = None,
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
    """Advance only from fully reconstructed planning and typed execution evidence."""
    try:
        planning_verification = validate_validated_recursive_planning_checkpoint(
            validated_planning_artifact,
            planning_handoff=planning_handoff,
            source_discrepancy_report=source_discrepancy_report,
            source_evaluated_graph=source_evaluated_graph,
            fresh_plan=fresh_plan,
            planner_program_state=planner_program_state,
            source_hypothesis_portfolio=source_hypothesis_portfolio,
            previous_discrepancy_report=previous_discrepancy_report,
            candidate_match=candidate_match,
            planner_critic_report=planner_critic_report,
            planner_reasoning_proposal=planner_reasoning_proposal,
            budget_units=budget_units,
            minimum_utility=minimum_utility,
            previous_checkpoint=previous_checkpoint,
        )
    except ResearchLoopError as exc:
        raise RecursiveResearchEvidenceError(
            "post-execution progression requires the exact validated planning artifact"
        ) from exc
    checkpoint = _mapping(
        planning_verification.get("recursive_checkpoint"),
        "validated_planning_artifact.recursive_checkpoint",
    )
    (
        checkpoint_sha,
        _source_target,
        expected_action_id,
        expected_action_class,
        _expected_plan_sha,
    ) = _checkpoint(checkpoint)
    try:
        execution_record = build_authenticated_recursive_execution_record(
            source_checkpoint_sha256=checkpoint_sha,
            expected_candidate_action_id=expected_action_id,
            expected_candidate_action_class=expected_action_class,
            adapter_id=execution_adapter_id,
            repository_root=repository_root,
            research_run=research_run,
            action_registry_path=action_registry_path,
            request_path=request_path,
            action_report_path=action_report_path,
        )
    except ResearchLoopError as exc:
        raise RecursiveResearchEvidenceError(
            "typed execution could not be independently reconstructed from request/registry/report/ledger"
        ) from exc
    return _advance_recursive_cycle_after_verified_transition(
        authorization_checkpoint=checkpoint,
        verified_execution_record=execution_record,
        transition_bundle_root=transition_bundle_root,
        fresh_plan=fresh_plan,
        program_state=program_state,
        previous_progression=previous_progression,
    )
'''
evidence = replace_once(
    evidence,
    "\n__all__ = [\n",
    public_wrapper + "\n__all__ = [\n",
    label="public evidence wrapper insertion",
)
write(evidence_path, evidence)

for rel in (
    "tests/test_recursive_research_cycle_controller.py",
    "tests/test_recursive_research_cycle_integration.py",
    "tests/test_recursive_research_cycle_review_hardening.py",
):
    text = read(rel)
    text = text.replace(
        "    build_recursive_research_cycle_checkpoint,\n",
        "    _build_recursive_research_cycle_checkpoint as build_recursive_research_cycle_checkpoint,\n",
    )
    text = text.replace(
        "    validate_recursive_research_cycle_checkpoint,\n",
        "    _validate_recursive_research_cycle_checkpoint as validate_recursive_research_cycle_checkpoint,\n",
    )
    write(rel, text)

for rel in (
    "tests/test_recursive_research_cycle_evidence.py",
    "tests/test_recursive_research_cycle_integration.py",
    "tests/test_recursive_research_cycle_review_hardening.py",
):
    text = read(rel)
    text = text.replace(
        "    advance_recursive_cycle_after_verified_transition,\n",
        "    _advance_recursive_cycle_after_verified_transition as advance_recursive_cycle_after_verified_transition,\n",
    )
    write(rel, text)

review_path = "tests/test_recursive_research_cycle_review_hardening.py"
review = read(review_path)
if "test_production_api_hides_raw_checkpoint_builder" not in review:
    review += r'''


def test_production_api_hides_raw_checkpoint_builder() -> None:
    import materials_data_analyzer.research_loop.recursive_research_cycle_controller as controller

    assert "build_recursive_research_cycle_checkpoint" not in controller.__all__
    assert "validate_recursive_research_cycle_checkpoint" not in controller.__all__
    assert not hasattr(controller, "build_recursive_research_cycle_checkpoint")
    assert not hasattr(controller, "validate_recursive_research_cycle_checkpoint")


def test_public_progression_does_not_accept_self_certified_execution_record() -> None:
    import inspect
    import materials_data_analyzer.research_loop.recursive_research_cycle_evidence as evidence

    parameters = inspect.signature(
        evidence.advance_recursive_cycle_after_verified_transition
    ).parameters
    assert "authorization_checkpoint" not in parameters
    assert "verified_execution_record" not in parameters
    assert "validated_planning_artifact" in parameters
    assert "request_path" in parameters
    assert "action_report_path" in parameters
    assert "execution_adapter_id" in parameters


def test_recursive_execution_authentication_is_domain_verifier_backed() -> None:
    import inspect
    from materials_data_analyzer.research_loop import recursive_authorized_execution_evidence as auth

    source = inspect.getsource(auth.build_authenticated_recursive_execution_record)
    assert "verify_heat_conduction_action_report_pinned" in source
    assert "verify_nist_structural_design_report_pinned" in source
    assert "load_research_state" in source
    assert "load_action_registry" in source
    assert "describe_action" in source
'''
write(review_path, review)

print("PR #202 trust-boundary patch applied.")
