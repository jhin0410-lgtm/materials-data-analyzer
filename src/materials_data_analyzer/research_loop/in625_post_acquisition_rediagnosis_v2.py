"""Quality-aware post-acquisition re-diagnosis for the exact IN625 external source.

V2 composes the provenance-only post-acquisition diagnosis with the separately reviewed
observed-quality contract.  Physical comparability remains the primary scientific blocker.
The one exact source missingness observation is propagated as a secondary data-quality
blocker so downstream comparison code cannot silently impute, reconstruct, or drop it.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .in625_post_acquisition_rediagnosis import (
    build_in625_post_acquisition_rediagnosis,
)
from .in625_tensile_quality_contract import verify_in625_tensile_observed_quality
from .kernel import ResearchLoopError

SCHEMA_VERSION = "2.0"
POLICY_VERSION = "2.0"


class In625PostAcquisitionRediagnosisV2Error(ResearchLoopError):
    """Raised when quality-aware post-acquisition diagnosis loses a verified binding."""


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise In625PostAcquisitionRediagnosisV2Error(f"{field} must be an object")
    return value


def _canonical_sha(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise In625PostAcquisitionRediagnosisV2Error(
            "quality-aware re-diagnosis must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def build_in625_post_acquisition_rediagnosis_v2(
    *,
    network_authorization: Mapping[str, Any],
    network_receipt: Mapping[str, Any],
    typed_execution_result: Mapping[str, Any],
    reviewed_tensile_manifest: Mapping[str, Any],
    quality_contract_path: str | Path,
) -> dict[str, Any]:
    """Re-diagnose after acquisition while preserving the exact observed missingness."""
    base = build_in625_post_acquisition_rediagnosis(
        network_authorization=network_authorization,
        network_receipt=network_receipt,
        typed_execution_result=typed_execution_result,
        reviewed_tensile_manifest=reviewed_tensile_manifest,
    )
    quality = verify_in625_tensile_observed_quality(
        reviewed_tensile_manifest=reviewed_tensile_manifest,
        quality_contract_path=quality_contract_path,
    )
    base_sha = base.get("rediagnosis_sha256")
    if not isinstance(base_sha, str) or len(base_sha) != 64:
        raise In625PostAcquisitionRediagnosisV2Error(
            "base post-acquisition re-diagnosis lacks canonical digest"
        )
    quality_sha = quality.get("verification_sha256")
    if not isinstance(quality_sha, str) or len(quality_sha) != 64:
        raise In625PostAcquisitionRediagnosisV2Error(
            "observed-quality verification lacks canonical digest"
        )

    current_blocker = dict(_mapping(base.get("current_blocker"), "base.current_blocker"))
    if current_blocker.get("code") != "cross_source_physical_comparability_not_established":
        raise In625PostAcquisitionRediagnosisV2Error(
            "quality-aware diagnosis requires physical comparability as the base blocker"
        )
    current_blocker["summary"] = (
        "Real external IN625 tensile rows now exist, but sample/process/protocol equivalence "
        "to the target evidence and replicate independence remain unestablished. The exact "
        "source also contains one bound Load N blank that must be handled explicitly if that "
        "response participates in a future comparison."
    )

    next_action = dict(_mapping(base.get("next_action"), "base.next_action"))
    required = next_action.get("required_evidence")
    if not isinstance(required, list):
        raise In625PostAcquisitionRediagnosisV2Error(
            "base next action required_evidence must be a list"
        )
    next_action["required_evidence"] = [
        *required,
        (
            "An explicit no-imputation comparison policy for the bound AM-AB-H block 1 "
            "Excel row 79 Load N blank whenever Load N is selected as a comparison response"
        ),
    ]
    next_action["source_quality_constraint"] = {
        "quality_contract_verified": True,
        "affected_field": "load_n",
        "affected_row_count": quality["incomplete_numeric_measurement_row_count"],
        "missing_value_imputation_authorized": False,
        "inverse_reconstruction_authorized": False,
        "row_exclusion_authorized": False,
    }

    evidence_state = dict(_mapping(base.get("evidence_state"), "base.evidence_state"))
    evidence_state.update(
        {
            "observed_source_quality_contract_verified": True,
            "complete_numeric_measurement_row_count": quality[
                "complete_numeric_measurement_row_count"
            ],
            "incomplete_numeric_measurement_row_count": quality[
                "incomplete_numeric_measurement_row_count"
            ],
            "isolated_source_missingness_observed": quality[
                "isolated_source_missingness_observed"
            ],
            "missingness_mechanism_established": False,
            "missing_value_imputation_authorized": False,
        }
    )

    stop_state = dict(_mapping(base.get("stop_state"), "base.stop_state"))
    stop_state["reason"] = (
        "A meaningful real-evidence state was reached. Physical comparability is the primary "
        "next scientific bottleneck, while one exact source missingness observation remains "
        "a bounded secondary data-quality constraint; neither supports positive closeout."
    )
    stop_state["positive_scientific_closeout"] = False

    result: dict[str, Any] = {
        **{key: value for key, value in base.items() if key != "rediagnosis_sha256"},
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "predecessor_rediagnosis_sha256": base_sha,
        "observed_quality_verification_sha256": quality_sha,
        "observed_quality_verification": quality,
        "current_blocker": current_blocker,
        "secondary_blockers": [
            {
                "code": "reviewed_numeric_source_missingness_observed",
                "kind": "data_quality",
                "severity": "bounded",
                "measurement_row_count": quality["measurement_row_count"],
                "affected_row_count": quality[
                    "incomplete_numeric_measurement_row_count"
                ],
                "known_incomplete_rows": quality["known_incomplete_rows"],
                "blocks_external_evidence_availability": False,
                "blocks_unqualified_use_of_affected_load_value": True,
                "missingness_mechanism_established": False,
                "imputation_authorized": False,
                "row_exclusion_authorized": False,
                "scientific_status_changed": False,
            }
        ],
        "next_action": next_action,
        "evidence_state": evidence_state,
        "stop_state": stop_state,
        "scientific_status_changed": False,
    }
    result["rediagnosis_sha256"] = _canonical_sha(result)
    return result


__all__ = [
    "In625PostAcquisitionRediagnosisV2Error",
    "build_in625_post_acquisition_rediagnosis_v2",
]
