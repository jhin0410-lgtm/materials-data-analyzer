"""Bind the live MVP reports to an explicit weakness -> action -> reanalysis sequence.

The base live compiler proves that each domain has two persisted diagnostic iterations.  This
module adds the stronger temporal/causal control-plane statement required by Issue #165: the
recorded next action must be the action that triggers the second analysis artifact, not a future
recommendation invented after the episode has already stopped.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from typing import Any

from .kernel import ResearchLoopError
from .real_data_episode_acceptance import evaluate_real_data_episode_suite

LIVE_MVP_SEQUENCE_SCHEMA_VERSION = "1.0"
LIVE_MVP_SEQUENCE_POLICY_VERSION = "1.0"


class LiveMvpSequenceError(ResearchLoopError):
    """Raised when a claimed reanalysis cycle is not bound to observed evidence."""


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
        raise LiveMvpSequenceError("sequence evidence must be canonical-JSON serializable") from exc
    return hashlib.sha256(raw).hexdigest()


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise LiveMvpSequenceError(f"{label} must be an object")
    return dict(value)


def _sha(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise LiveMvpSequenceError(f"{label} must be lowercase SHA-256")
    return value


def _action(action_type: str, rationale: str, evidence: list[str]) -> tuple[dict[str, Any], str]:
    record = {
        "action_type": action_type,
        "rationale": rationale,
        "evidence_sha256": sorted(evidence),
        "execution_authorized_here": False,
        "physical_experiment_executed_here": False,
        "scientific_status_changed": False,
    }
    return record, _canonical_sha256(record)


_SEQUENCE_SPECS: dict[str, dict[str, object]] = {
    "live-nasa-pcoe-battery-v1": {
        "action_type": "run_protocol_aware_posthoc_audit_before_predictive_interpretation",
        "rationale": (
            "Target-comparability and battery-influence diagnostics exposed weaknesses that "
            "required the persisted protocol-aware post-hoc audit before bounded stop."
        ),
        "action_evidence_keys": [
            "target_comparability_audit_sha256",
            "battery_influence_triage_sha256",
            "diagnostic_priority_sha256",
        ],
        "reanalysis_type": "protocol_aware_posthoc_audit",
        "reanalysis_artifact_key": "protocol_audit_sha256",
        "post_stop_action": "retain_diagnostic_scope_and_prioritize_protocol_or_source_quality_followup",
        "post_stop_rationale": (
            "Predictive evidence remained unsupported after the protocol re-audit, so later work "
            "must remain diagnostic and target protocol/source-quality evidence."
        ),
    },
    "live-public-dwcnt-multimodal-v1": {
        "action_type": "run_explicit_tga_candidate_boundary_review",
        "rationale": (
            "The initial public TGA analysis produced diagnostic thermal-event candidates and a "
            "bounded startup segment that required a separately persisted candidate review."
        ),
        "action_evidence_keys": [
            "source_manifest_sha256",
            "analysis_manifest_sha256",
        ],
        "reanalysis_type": "tga_candidate_boundary_review",
        "reanalysis_artifact_key": "tga_case_review_sha256",
        "post_stop_action": "resolve_cross_technique_aliquot_lineage_and_review_retained_tga_candidates",
        "post_stop_rationale": (
            "The second pass retained diagnostic candidates but did not establish identical "
            "physical aliquots across techniques or validate TEM quantitative segmentation."
        ),
    },
    "live-public-rwgs-xrd-eds-v1": {
        "action_type": "run_independent_handoff_and_comparability_validation_before_process_response_use",
        "rationale": (
            "The producer analysis exposed an SEM method mismatch and incomplete cross-technique "
            "lineage, requiring independent handoff/comparability validation before any modeling."
        ),
        "action_evidence_keys": [
            "analysis_manifest_sha256",
            "comparability_matrix_sha256",
        ],
        "reanalysis_type": "independent_handoff_and_comparability_validation",
        "reanalysis_artifact_key": "independent_validation_summary_sha256",
        "post_stop_action": "resolve_physical_aliquot_lineage_eds_ni_and_acquisition_metadata_before_modeling",
        "post_stop_rationale": (
            "Independent validation preserved Diagnostic status, the SEM method block, unresolved "
            "Ni review, and missing acquisition/aliquot evidence."
        ),
    },
}


def bind_live_episode_sequence(result: Mapping[str, Any]) -> dict[str, Any]:
    """Replace post-hoc recommendations with the actual action that triggered iteration two."""
    value = copy.deepcopy(dict(_mapping(result, "live MVP result")))
    reports = value.get("episode_reports")
    if not isinstance(reports, list) or len(reports) != len(_SEQUENCE_SPECS):
        raise LiveMvpSequenceError("live MVP result must contain exactly the three canonical episodes")

    seen: set[str] = set()
    rebound: list[dict[str, Any]] = []
    for raw_report in reports:
        report = _mapping(raw_report, "episode report")
        episode_id = report.get("episode_id")
        if not isinstance(episode_id, str) or episode_id not in _SEQUENCE_SPECS:
            raise LiveMvpSequenceError(f"unsupported live episode for sequence binding: {episode_id!r}")
        if episode_id in seen:
            raise LiveMvpSequenceError(f"duplicate live episode: {episode_id}")
        seen.add(episode_id)
        if report.get("scientific_status_changed") is not False:
            raise LiveMvpSequenceError(f"{episode_id} changed scientific status")
        if report.get("scientific_promotion_authorized") is not False:
            raise LiveMvpSequenceError(f"{episode_id} authorized scientific promotion")
        if report.get("iteration_count") != 2:
            raise LiveMvpSequenceError(f"{episode_id} must expose exactly two bounded iterations")

        observed = _mapping(report.get("observed_artifacts"), f"{episode_id} observed_artifacts")
        spec = _SEQUENCE_SPECS[episode_id]
        evidence_keys = spec["action_evidence_keys"]
        if not isinstance(evidence_keys, list):
            raise LiveMvpSequenceError("internal sequence evidence-key specification is malformed")
        action_evidence = [
            _sha(observed.get(key), f"{episode_id}.{key}")
            for key in evidence_keys
        ]
        action, action_sha = _action(
            str(spec["action_type"]),
            str(spec["rationale"]),
            action_evidence,
        )
        reanalysis_key = str(spec["reanalysis_artifact_key"])
        reanalysis_sha = _sha(observed.get(reanalysis_key), f"{episode_id}.{reanalysis_key}")
        report["next_action_decision"] = {
            "decision_report_sha256": action_sha,
            "action_recorded": True,
        }
        report["next_action_record"] = action
        report["reanalysis_record"] = {
            "iteration": 2,
            "triggering_decision_sha256": action_sha,
            "reanalysis_type": str(spec["reanalysis_type"]),
            "result_artifact_sha256": reanalysis_sha,
            "result_artifact_observed_key": reanalysis_key,
            "scientific_status_changed": False,
        }
        report["post_stop_followup"] = {
            "action_type": str(spec["post_stop_action"]),
            "rationale": str(spec["post_stop_rationale"]),
            "executed_in_this_episode": False,
            "scientific_status_changed": False,
        }
        rebound.append(report)

    if seen != set(_SEQUENCE_SPECS):
        raise LiveMvpSequenceError("canonical live episode set is incomplete")

    acceptance = evaluate_real_data_episode_suite(rebound, required_full_cycles=3)
    if acceptance.get("mvp_acceptance_passed") is not True:
        raise LiveMvpSequenceError("sequence-bound live episode suite does not satisfy MVP acceptance")
    value["episode_reports"] = rebound
    value["suite_acceptance"] = acceptance
    value["sequence_binding"] = {
        "schema_version": LIVE_MVP_SEQUENCE_SCHEMA_VERSION,
        "policy_version": LIVE_MVP_SEQUENCE_POLICY_VERSION,
        "episode_count": len(rebound),
        "weakness_to_action_to_reanalysis_bound": True,
        "future_followups_kept_separate_from_completed_reanalysis": True,
        "scientific_status_changed": False,
        "execution_authorized_here": False,
    }
    value.pop("result_sha256", None)
    value["result_sha256"] = _canonical_sha256(value)
    return value


__all__ = [
    "LIVE_MVP_SEQUENCE_POLICY_VERSION",
    "LIVE_MVP_SEQUENCE_SCHEMA_VERSION",
    "LiveMvpSequenceError",
    "bind_live_episode_sequence",
]
