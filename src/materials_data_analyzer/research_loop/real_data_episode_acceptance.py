"""Fail-closed acceptance contract for materially different real-data research episodes.

The completion-track MVP is stronger than unit-test coverage: an episode must be bound to
real external evidence and demonstrate the research control cycle without fabricating a
scientific promotion.  This module evaluates episode reports only; it cannot acquire data,
release review, authorize execution, or upgrade evidence.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from .kernel import ResearchLoopError

REAL_DATA_EPISODE_ACCEPTANCE_SCHEMA_VERSION = "1.0"
REAL_DATA_EPISODE_ACCEPTANCE_POLICY_VERSION = "1.0"
_REQUIRED_STAGES = (
    "question_defined",
    "real_evidence_bound",
    "scientific_intake_recorded",
    "analysis_or_ineligibility_recorded",
    "weakness_or_contradiction_recorded",
    "next_action_recorded",
    "reanalysis_or_bounded_stop_recorded",
)
_ALLOWED_TERMINAL_STATES = {"blocked", "concluded", "stopped"}
_ALLOWED_INTAKE_STATES = {"accepted", "rejected", "pending_review", "ineligible"}


class RealDataEpisodeAcceptanceError(ResearchLoopError):
    """Raised when an acceptance input is malformed rather than merely incomplete."""


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
        raise RealDataEpisodeAcceptanceError(
            "episode report must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise RealDataEpisodeAcceptanceError(f"{field} must be non-empty trimmed text")
    return value


def _sha(value: object, field: str) -> str:
    text = _text(value, field)
    if len(text) != 64 or text != text.lower() or any(c not in "0123456789abcdef" for c in text):
        raise RealDataEpisodeAcceptanceError(f"{field} must be lowercase SHA-256")
    return text


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RealDataEpisodeAcceptanceError(f"{field} must be an object")
    return value


def _string_list(value: object, field: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list):
        raise RealDataEpisodeAcceptanceError(f"{field} must be a list")
    result: list[str] = []
    for index, raw in enumerate(value):
        text = _text(raw, f"{field}[{index}]")
        if text in result:
            raise RealDataEpisodeAcceptanceError(f"{field} must not contain duplicates")
        result.append(text)
    if nonempty and not result:
        raise RealDataEpisodeAcceptanceError(f"{field} must not be empty")
    return result


def _real_source_binding(value: object) -> tuple[dict[str, Any], bool]:
    binding = dict(_mapping(value, "real_source_binding"))
    source_kind = _text(binding.get("source_kind"), "real_source_binding.source_kind")
    source_locator = _text(binding.get("source_locator"), "real_source_binding.source_locator")
    artifact_sha = _sha(binding.get("artifact_sha256"), "real_source_binding.artifact_sha256")
    acquisition_receipt_sha = binding.get("acquisition_receipt_sha256")
    if acquisition_receipt_sha is not None:
        _sha(acquisition_receipt_sha, "real_source_binding.acquisition_receipt_sha256")
    synthetic = binding.get("synthetic")
    if not isinstance(synthetic, bool):
        raise RealDataEpisodeAcceptanceError("real_source_binding.synthetic must be boolean")
    return {
        "source_kind": source_kind,
        "source_locator": source_locator,
        "artifact_sha256": artifact_sha,
        "acquisition_receipt_sha256": acquisition_receipt_sha,
        "synthetic": synthetic,
    }, not synthetic


def evaluate_real_data_episode(report: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate one episode without assuming blocked evidence is scientifically accepted."""
    value = dict(_mapping(report, "report"))
    episode_id = _text(value.get("episode_id"), "episode_id")
    family = _text(value.get("episode_family_id"), "episode_family_id")
    modality = _text(value.get("modality"), "modality")
    evidence_class = _text(value.get("evidence_class"), "evidence_class")
    source, real_source = _real_source_binding(value.get("real_source_binding"))
    question = _text(value.get("research_question"), "research_question")

    intake = dict(_mapping(value.get("scientific_intake"), "scientific_intake"))
    intake_status = _text(intake.get("status"), "scientific_intake.status")
    if intake_status not in _ALLOWED_INTAKE_STATES:
        raise RealDataEpisodeAcceptanceError("unsupported scientific intake status")
    intake_reason = _text(intake.get("reason"), "scientific_intake.reason")

    analysis = dict(_mapping(value.get("analysis"), "analysis"))
    analysis_performed = analysis.get("performed")
    if not isinstance(analysis_performed, bool):
        raise RealDataEpisodeAcceptanceError("analysis.performed must be boolean")
    if not analysis_performed:
        _text(analysis.get("ineligibility_reason"), "analysis.ineligibility_reason")

    weaknesses = _string_list(
        value.get("weaknesses_or_contradictions"),
        "weaknesses_or_contradictions",
        nonempty=True,
    )
    next_action = dict(_mapping(value.get("next_action_decision"), "next_action_decision"))
    decision_sha = _sha(next_action.get("decision_report_sha256"), "next_action_decision.decision_report_sha256")
    action_recorded = next_action.get("action_recorded")
    if not isinstance(action_recorded, bool):
        raise RealDataEpisodeAcceptanceError("next_action_decision.action_recorded must be boolean")

    iteration_count = value.get("iteration_count")
    if isinstance(iteration_count, bool) or not isinstance(iteration_count, int) or iteration_count < 1:
        raise RealDataEpisodeAcceptanceError("iteration_count must be a positive integer")
    terminal_state = _text(value.get("terminal_state"), "terminal_state")
    if terminal_state not in _ALLOWED_TERMINAL_STATES:
        raise RealDataEpisodeAcceptanceError("episode must have a bounded terminal state")
    terminal_reason = _text(value.get("terminal_reason"), "terminal_reason")

    scientific_promotion = value.get("scientific_status_changed")
    if not isinstance(scientific_promotion, bool):
        raise RealDataEpisodeAcceptanceError("scientific_status_changed must be boolean")
    promotion_authorized = value.get("scientific_promotion_authorized")
    if not isinstance(promotion_authorized, bool):
        raise RealDataEpisodeAcceptanceError("scientific_promotion_authorized must be boolean")
    false_promotion = scientific_promotion and not promotion_authorized

    stages = {
        "question_defined": bool(question),
        "real_evidence_bound": real_source,
        "scientific_intake_recorded": bool(intake_status and intake_reason),
        "analysis_or_ineligibility_recorded": analysis_performed
        or bool(analysis.get("ineligibility_reason")),
        "weakness_or_contradiction_recorded": bool(weaknesses),
        "next_action_recorded": action_recorded and bool(decision_sha),
        "reanalysis_or_bounded_stop_recorded": iteration_count >= 2
        or terminal_state in _ALLOWED_TERMINAL_STATES,
    }
    episode_valid = all(stages[name] for name in _REQUIRED_STAGES) and not false_promotion
    full_cycle_complete = bool(
        episode_valid
        and intake_status == "accepted"
        and analysis_performed
        and iteration_count >= 2
        and terminal_state in {"concluded", "stopped"}
    )
    bounded_blocked_episode = bool(
        episode_valid
        and terminal_state == "blocked"
        and intake_status in {"pending_review", "ineligible", "rejected"}
    )

    result: dict[str, Any] = {
        "schema_version": REAL_DATA_EPISODE_ACCEPTANCE_SCHEMA_VERSION,
        "policy_version": REAL_DATA_EPISODE_ACCEPTANCE_POLICY_VERSION,
        "episode_id": episode_id,
        "episode_family_id": family,
        "modality": modality,
        "evidence_class": evidence_class,
        "real_source_binding": source,
        "stages": stages,
        "scientific_intake_status": intake_status,
        "analysis_performed": analysis_performed,
        "iteration_count": iteration_count,
        "terminal_state": terminal_state,
        "terminal_reason": terminal_reason,
        "scientific_status_changed": scientific_promotion,
        "scientific_promotion_authorized": promotion_authorized,
        "false_scientific_promotion_detected": false_promotion,
        "episode_valid": episode_valid,
        "mvp_full_cycle_complete": full_cycle_complete,
        "bounded_blocked_episode": bounded_blocked_episode,
    }
    result["acceptance_sha256"] = _canonical_sha256(result)
    return result


def evaluate_real_data_episode_suite(
    reports: Sequence[Mapping[str, Any]],
    *,
    required_full_cycles: int = 3,
) -> dict[str, Any]:
    """Evaluate MVP completion while requiring materially different full cycles."""
    if isinstance(required_full_cycles, bool) or not isinstance(required_full_cycles, int) or required_full_cycles < 1:
        raise RealDataEpisodeAcceptanceError("required_full_cycles must be positive")
    if not isinstance(reports, Sequence) or isinstance(reports, (str, bytes, bytearray)):
        raise RealDataEpisodeAcceptanceError("reports must be a sequence")
    evaluations = [evaluate_real_data_episode(report) for report in reports]
    ids = [item["episode_id"] for item in evaluations]
    if len(ids) != len(set(ids)):
        raise RealDataEpisodeAcceptanceError("episode IDs must be unique")

    full = [item for item in evaluations if item["mvp_full_cycle_complete"]]
    full_families = {item["episode_family_id"] for item in full}
    full_modalities = {item["modality"] for item in full}
    full_evidence_classes = {item["evidence_class"] for item in full}
    materially_different = bool(
        len(full_families) >= required_full_cycles
        and len(full_modalities) >= 2
        and len(full_evidence_classes) >= 2
    )
    passed = len(full) >= required_full_cycles and materially_different
    result: dict[str, Any] = {
        "schema_version": REAL_DATA_EPISODE_ACCEPTANCE_SCHEMA_VERSION,
        "policy_version": REAL_DATA_EPISODE_ACCEPTANCE_POLICY_VERSION,
        "required_full_cycles": required_full_cycles,
        "episode_count": len(evaluations),
        "valid_episode_count": sum(bool(item["episode_valid"]) for item in evaluations),
        "full_cycle_count": len(full),
        "bounded_blocked_count": sum(bool(item["bounded_blocked_episode"]) for item in evaluations),
        "full_cycle_family_count": len(full_families),
        "full_cycle_modality_count": len(full_modalities),
        "full_cycle_evidence_class_count": len(full_evidence_classes),
        "materially_different_full_cycles": materially_different,
        "mvp_acceptance_passed": passed,
        "evaluations": evaluations,
        "scientific_status_changed": False,
        "execution_authorized_here": False,
        "human_review_synthesized_here": False,
    }
    result["suite_sha256"] = _canonical_sha256(result)
    return result


__all__ = [
    "REAL_DATA_EPISODE_ACCEPTANCE_POLICY_VERSION",
    "REAL_DATA_EPISODE_ACCEPTANCE_SCHEMA_VERSION",
    "RealDataEpisodeAcceptanceError",
    "evaluate_real_data_episode",
    "evaluate_real_data_episode_suite",
]
