"""Deterministic safety benchmark distilled from post-MVP real-data failure modes.

The tiny tabular fixtures in this module are regression fixtures, not scientific evidence.
They encode failure *classes* observed in live fatigue, SSRM, Co-Cr, and SOFC work so that
future generic-intake changes cannot silently turn structural observations into specimen,
lineage, model-validity, or scientific-support claims.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from .delimited_structural_intake import inspect_delimited_structure

POST_MVP_FAILURE_MODE_BENCHMARK_SCHEMA_VERSION = "1.0"


def _canonical_sha(value: object) -> str:
    body = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _has_hint(report: Mapping[str, Any], hint: str) -> bool:
    return any(
        hint in profile.get("header_semantic_hints_proposal_only", [])
        for profile in report.get("column_profiles", [])
        if isinstance(profile, Mapping)
    )


def _has_constant_column(report: Mapping[str, Any]) -> bool:
    return any(
        profile.get("constant_nonblank_signal") is True
        for profile in report.get("column_profiles", [])
        if isinstance(profile, Mapping)
    )


def evaluate_structural_claim_safety(
    *,
    structure: Mapping[str, Any],
    claim_kind: str,
    provenance_authenticated: bool,
    domain_intake_accepted: bool,
    independent_units_established: bool = False,
    authoritative_cross_modal_join_established: bool = False,
    raw_derived_reconciliation_established: bool = False,
    derived_representation: bool = False,
    model_validity_established: bool = False,
    human_review_required: bool = False,
    human_review_released: bool = False,
) -> dict[str, Any]:
    """Apply non-semantic safety gates to one structural claim request.

    Inputs such as model validity and cross-modal joins must come from separately
    authenticated domain/review contracts. This function never derives them from headers.
    """
    blockers: list[str] = []
    if structure.get("scientific_status_changed") is not False:
        blockers.append("generic_structure_attempted_scientific_status_change")
    if structure.get("accepted_for_analysis") is not False:
        blockers.append("generic_structure_attempted_analysis_acceptance")
    if not provenance_authenticated:
        blockers.append("provenance_not_authenticated")
    if not domain_intake_accepted:
        blockers.append("domain_scientific_intake_not_accepted")
    if human_review_required and not human_review_released:
        blockers.append("required_human_review_not_released")

    if claim_kind == "independent_replicate_effect":
        if not independent_units_established:
            blockers.append("independent_experimental_units_not_established")
        if _has_hint(structure, "time_like") or _has_hint(structure, "frequency_like"):
            blockers.append("repeated_observation_axis_cannot_supply_independent_n")
    elif claim_kind == "cross_modal_mechanism":
        if not authoritative_cross_modal_join_established:
            blockers.append("authoritative_cross_modal_sample_join_not_established")
    elif claim_kind == "derived_representation_effect":
        if not derived_representation:
            blockers.append("representation_role_not_established")
        if not raw_derived_reconciliation_established:
            blockers.append("raw_derived_reconciliation_not_established")
        if _has_constant_column(structure):
            blockers.append("constant_or_stale_column_signal_requires_review")
    elif claim_kind == "fit_model_validity":
        if not derived_representation:
            blockers.append("fit_representation_role_not_established")
        if not model_validity_established:
            blockers.append("model_validity_not_established_by_domain_contract")
    elif claim_kind == "scientific_status_promotion":
        # The common provenance/domain/review gates above are the relevant contract.
        pass
    else:
        blockers.append("unsupported_claim_kind")

    return {
        "claim_kind": claim_kind,
        "authorized": not blockers,
        "blockers": sorted(set(blockers)),
        "generic_structure_used_as_scientific_validation": False,
        "scientific_status_changed": False,
    }


def _scenario_reports() -> list[dict[str, Any]]:
    repeated = inspect_delimited_structure(
        b"time_s,voltage_v\n0.0,1.01\n0.2,1.00\n0.4,0.99\n"
    )
    lineage = inspect_delimited_structure(
        b"image_name,metric\nsem_01.tif,0.12\nsem_02.tif,0.15\n"
    )
    stale = inspect_delimited_structure(
        b"current_density,voltage,power_density\n0.10,0.90,0.090\n"
        b"0.10,0.90,0.095\n0.10,0.90,0.101\n"
    )
    fit = inspect_delimited_structure(
        b"parameter,value,error_percent\nR1,0.4,42\nCPE1,0.02,499\n"
    )
    review = inspect_delimited_structure(
        b"sample_id,value\ns1,1.2\ns2,1.4\n"
    )

    return [
        {
            "scenario_id": "repeated_observation_as_independent_n",
            "observed_live_failure_class": "time_or_frequency_rows_are_repeated_observations_not_independent_specimens",
            "result": evaluate_structural_claim_safety(
                structure=repeated,
                claim_kind="independent_replicate_effect",
                provenance_authenticated=True,
                domain_intake_accepted=True,
                independent_units_established=False,
            ),
            "required_blockers": [
                "independent_experimental_units_not_established",
                "repeated_observation_axis_cannot_supply_independent_n",
            ],
        },
        {
            "scenario_id": "missing_cross_modal_sample_lineage",
            "observed_live_failure_class": "image_or_measurement_files_exist_without_authoritative_same_sample_join",
            "result": evaluate_structural_claim_safety(
                structure=lineage,
                claim_kind="cross_modal_mechanism",
                provenance_authenticated=True,
                domain_intake_accepted=True,
                authoritative_cross_modal_join_established=False,
            ),
            "required_blockers": ["authoritative_cross_modal_sample_join_not_established"],
        },
        {
            "scenario_id": "derived_summary_stale_or_truncated_representation",
            "observed_live_failure_class": "derived_summary_can_have_stale_columns_or_information_loss",
            "result": evaluate_structural_claim_safety(
                structure=stale,
                claim_kind="derived_representation_effect",
                provenance_authenticated=True,
                domain_intake_accepted=True,
                derived_representation=True,
                raw_derived_reconciliation_established=False,
            ),
            "required_blockers": [
                "constant_or_stale_column_signal_requires_review",
                "raw_derived_reconciliation_not_established",
            ],
        },
        {
            "scenario_id": "fit_derived_representation_without_model_validation",
            "observed_live_failure_class": "fit_parameters_are_derived_and_do_not_self_validate_model_identifiability",
            "result": evaluate_structural_claim_safety(
                structure=fit,
                claim_kind="fit_model_validity",
                provenance_authenticated=True,
                domain_intake_accepted=True,
                derived_representation=True,
                model_validity_established=False,
            ),
            "required_blockers": ["model_validity_not_established_by_domain_contract"],
        },
        {
            "scenario_id": "provenance_and_human_review_gate",
            "observed_live_failure_class": "exact_bytes_and_required_human_review_must_precede_scientific_promotion",
            "result": evaluate_structural_claim_safety(
                structure=review,
                claim_kind="scientific_status_promotion",
                provenance_authenticated=False,
                domain_intake_accepted=False,
                human_review_required=True,
                human_review_released=False,
            ),
            "required_blockers": [
                "domain_scientific_intake_not_accepted",
                "provenance_not_authenticated",
                "required_human_review_not_released",
            ],
        },
    ]


def run_post_mvp_failure_mode_benchmark() -> dict[str, Any]:
    """Run locked post-MVP safety scenarios and return auditable metrics."""
    scenarios = _scenario_reports()
    unsafe_authorizations = 0
    missing_required_blockers = 0
    scientific_status_changes = 0
    scenario_results: list[dict[str, Any]] = []
    for scenario in scenarios:
        result = scenario["result"]
        required = set(scenario["required_blockers"])
        observed = set(result["blockers"])
        missing = sorted(required - observed)
        if result["authorized"]:
            unsafe_authorizations += 1
        if missing:
            missing_required_blockers += 1
        if result["scientific_status_changed"]:
            scientific_status_changes += 1
        scenario_results.append(
            {
                "scenario_id": scenario["scenario_id"],
                "observed_live_failure_class": scenario["observed_live_failure_class"],
                "authorized": result["authorized"],
                "observed_blockers": result["blockers"],
                "required_blockers": sorted(required),
                "missing_required_blockers": missing,
            }
        )

    report: dict[str, Any] = {
        "schema_version": POST_MVP_FAILURE_MODE_BENCHMARK_SCHEMA_VERSION,
        "scenario_count": len(scenarios),
        "scenario_results": scenario_results,
        "unsafe_authorization_count": unsafe_authorizations,
        "missing_required_blocker_scenario_count": missing_required_blockers,
        "scientific_status_change_count": scientific_status_changes,
        "zero_false_evidence_promotion": unsafe_authorizations == 0,
        "all_required_failure_modes_detected": missing_required_blockers == 0,
        "generic_intake_scientific_status_unchanged": scientific_status_changes == 0,
        "benchmark_pass": (
            unsafe_authorizations == 0
            and missing_required_blockers == 0
            and scientific_status_changes == 0
        ),
        "regression_fixtures_are_scientific_evidence": False,
        "scientific_status_changed": False,
    }
    report["benchmark_sha256"] = _canonical_sha(report)
    return report


__all__ = [
    "POST_MVP_FAILURE_MODE_BENCHMARK_SCHEMA_VERSION",
    "evaluate_structural_claim_safety",
    "run_post_mvp_failure_mode_benchmark",
]
