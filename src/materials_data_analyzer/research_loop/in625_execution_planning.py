"""Planning-state projection for the verified IN625 external-evidence action.

Planning may establish that a repository-registered real external source is an available
typed candidate. It does not assert that caller-supplied archive bytes are present or valid;
that stronger claim belongs to the independently pinned execution request/verifier boundary.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .action_registry import describe_action, load_action_registry
from .in625_external_evidence_action import ACTION_TYPE, ACTION_VERSION, COST_UNITS
from .in625_execution_verifier import ADAPTER_ID, REGISTRY_DOMAIN
from .kernel import LEDGER_FILENAME, ResearchLoopError, load_research_state

SOURCE_CONFIG_RELATIVE_PATH = "configs/research/in625_zenodo_20503603_verified_source.v1.json"
EXPECTED_SOURCE_ID = "zenodo-20503603-in625-lpbf-publication-supplement"
EXPECTED_RECORD_ID = 20503603


class In625ExecutionPlanningError(ResearchLoopError):
    """Raised when the verified external-evidence planning boundary drifts."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_file(value: str | Path, *, root: Path, field: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    path = path.resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise In625ExecutionPlanningError(f"{field} escapes repository root") from exc
    if not path.is_file():
        raise In625ExecutionPlanningError(f"{field} must resolve to a file")
    return path


def _source_identity(path: Path) -> tuple[dict[str, Any], str, str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise In625ExecutionPlanningError("verified IN625 source config is not valid JSON") from exc
    if not isinstance(value, dict) or value.get("source_id") != EXPECTED_SOURCE_ID:
        raise In625ExecutionPlanningError("verified IN625 source identity drifted")
    zenodo = value.get("zenodo")
    if not isinstance(zenodo, Mapping) or zenodo.get("record_id") != EXPECTED_RECORD_ID:
        raise In625ExecutionPlanningError("verified IN625 Zenodo record identity drifted")
    archive_name = zenodo.get("archive_file")
    files = zenodo.get("files")
    if not isinstance(archive_name, str) or not isinstance(files, Mapping):
        raise In625ExecutionPlanningError("verified IN625 archive identity is malformed")
    archive = files.get(archive_name)
    if not isinstance(archive, Mapping):
        raise In625ExecutionPlanningError("verified IN625 archive source entry is missing")
    archive_sha = archive.get("verified_sha256")
    if (
        not isinstance(archive_sha, str)
        or len(archive_sha) != 64
        or archive_sha != archive_sha.lower()
        or any(ch not in "0123456789abcdef" for ch in archive_sha)
    ):
        raise In625ExecutionPlanningError("verified IN625 archive SHA-256 is not repository-pinned")
    boundaries = value.get("scientific_boundaries")
    if not isinstance(boundaries, Mapping):
        raise In625ExecutionPlanningError("verified IN625 source scientific boundaries are missing")
    for key in (
        "automatic_scientific_promotion",
        "source_acquisition_establishes_direct_nist_comparability",
        "source_acquisition_establishes_hypothesis_truth",
        "source_acquisition_establishes_positive_scientific_closeout",
    ):
        if boundaries.get(key) is not False:
            raise In625ExecutionPlanningError(f"verified IN625 source boundary {key} must remain false")
    return value, _sha256_file(path), archive_sha


def _verified_registry(path: Path, root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    registry = load_action_registry(path, repository_root=root)
    if registry.get("domain") != REGISTRY_DOMAIN:
        raise In625ExecutionPlanningError("IN625 external-evidence registry domain drifted")
    contract = describe_action(registry, ACTION_TYPE)
    if (
        contract.get("version") != ACTION_VERSION
        or contract.get("availability") != "available"
        or contract.get("category") != "external_evidence_search"
        or contract.get("cost_units") != COST_UNITS
    ):
        raise In625ExecutionPlanningError("IN625 external-evidence action contract drifted")
    required_prohibited = {
        "synthetic_empirical_measurement_creation",
        "sample_identity_inference",
        "measurement_semantics_inference",
        "replicate_independence_inference",
        "direct_nist_condition_comparability_claim",
        "empirical_model_validation_claim",
        "hypothesis_truth_claim",
        "positive_scientific_closeout",
        "physical_experiment_execution",
        "automatic_scientific_evidence_promotion",
        "engineering_decision",
    }
    if not required_prohibited.issubset(set(contract.get("prohibited_effects", []))):
        raise In625ExecutionPlanningError("IN625 registry lost scientific boundary prohibitions")
    return registry, contract


def build_in625_execution_planning_state(
    *,
    repository_root: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
) -> dict[str, Any]:
    """Expose one real repository-pinned external source as a typed planning candidate."""
    root = Path(repository_root).expanduser().resolve(strict=True)
    run = Path(research_run).expanduser().resolve(strict=True)
    registry_path = _resolve_file(action_registry_path, root=root, field="action_registry_path")
    registry, contract = _verified_registry(registry_path, root)
    source_path = _resolve_file(SOURCE_CONFIG_RELATIVE_PATH, root=root, field="source_config")
    _, source_sha, archive_sha = _source_identity(source_path)

    state = load_research_state(run)
    if state.get("status") != "active":
        raise In625ExecutionPlanningError("IN625 external-evidence research run must be active")
    actions = state.get("actions")
    budget = state.get("budget")
    if not isinstance(actions, list) or not isinstance(budget, Mapping):
        raise In625ExecutionPlanningError("IN625 external-evidence research state is malformed")
    ledger = (run / LEDGER_FILENAME).resolve(strict=True)
    bindings = [
        {
            "role": "in625_external_evidence_registry",
            "path": registry_path.relative_to(root).as_posix(),
            "sha256": _sha256_file(registry_path),
        },
        {
            "role": "in625_verified_source_identity",
            "path": source_path.relative_to(root).as_posix(),
            "source_id": EXPECTED_SOURCE_ID,
            "zenodo_record_id": str(EXPECTED_RECORD_ID),
            "sha256": source_sha,
            "verified_archive_sha256": archive_sha,
        },
        {
            "role": "research_ledger",
            "path": str(ledger),
            "sha256": state["ledger_sha256"],
        },
    ]
    prior = [
        item
        for item in actions
        if isinstance(item, Mapping) and item.get("action_type") == ACTION_TYPE
    ]
    budget_allows = (
        int(budget.get("actions_remaining", 0)) > 0
        and int(budget.get("cost_units_remaining", 0)) >= COST_UNITS
    )
    if prior:
        selected = None
        frontier: list[dict[str, Any]] = []
        reason = (
            "The verified IN625 external source has already been registered in this research run; "
            "repeating the same source acquisition is not autonomously justified."
        )
        selection_status = "no_positive_value_action"
        stop_status = "terminal_for_current_scope"
        blocker_code = "verified_external_source_already_registered"
    elif not budget_allows:
        selected = None
        frontier = []
        reason = "The active research budget cannot fund the registered external-evidence action."
        selection_status = "budget_blocked"
        stop_status = "operationally_blocked"
        blocker_code = "external_evidence_action_budget_unavailable"
    else:
        selected = {
            "action_type": ACTION_TYPE,
            "action_version": ACTION_VERSION,
            "availability": "available",
            "cost_units": COST_UNITS,
            "priority_score": 100,
            "trigger": "empirical_evidence_not_acquired",
            "rationale": (
                "Register the exact repository-pinned Zenodo IN625 publication supplement as real external "
                "source evidence. Exact archive bytes still require a separate explicit typed request and verifier."
            ),
            "execution_registry_id": registry["registry_id"],
            "execution_registry_sha256": registry["registry_sha256"],
            "execution_registry_path": registry["registry_path"],
            "expected_source_config_sha256": source_sha,
            "expected_archive_sha256": archive_sha,
            "expected_information_gain": {
                "status": "qualitative_source_availability_gain_only",
                "value": None,
                "unit": None,
                "boundary": (
                    "Source acquisition can reduce the empirical-evidence availability gap but does not establish "
                    "comparability, model validity, or hypothesis truth."
                ),
            },
        }
        frontier = [selected]
        reason = selected["rationale"]
        selection_status = "ready_to_execute"
        stop_status = "continue"
        blocker_code = "empirical_evidence_not_acquired"

    return {
        "schema_version": "1.0",
        "adapter_id": ADAPTER_ID,
        "domain": REGISTRY_DOMAIN,
        "research_question": state["question"],
        "metrics": state["metrics"],
        "constraints": list(state["constraints"]),
        "stop_rules": list(state["stop_rules"]),
        "budget": dict(budget),
        "evidence_bindings": bindings,
        "action_frontier": frontier,
        "selected_action": selected,
        "current_blocker": {
            "kind": "external_empirical_evidence",
            "code": blocker_code,
            "summary": reason,
        },
        "evidence_gap": {
            "status": (
                "real_external_source_available_for_explicit_acquisition"
                if selected is not None
                else "source_registration_not_selected"
            ),
            "requirements": [
                "Exact archive bytes must match the repository-pinned SHA-256 before execution.",
                "Acquisition alone must not be interpreted as condition comparability or scientific support.",
            ],
        },
        "stop_state": {
            "status": stop_status,
            "selection_status": selection_status,
            "reason": reason,
            "reopen_conditions": (
                []
                if selected is not None
                else [
                    "A distinct independently verified external source or a new scientific intake objective is introduced."
                ]
            ),
        },
        "network_access_performed": False,
        "archive_bytes_verified_in_planning": False,
        "scientific_status_upgrade_authorized": False,
    }


__all__ = ["In625ExecutionPlanningError", "build_in625_execution_planning_state"]
