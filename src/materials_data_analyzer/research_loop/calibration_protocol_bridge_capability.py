"""Bounded capability for re-acquiring authorized AMMT bridge evidence and refining its frontier.

The capability deliberately does not invent a machine-setting to calibrated-power conversion.
It reuses the already mission-pinned eight-source authority, then determines only what the
authenticated claim packet establishes and what remains unresolved.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .in625_geometry_condition_multisource_policy import (
    ALLOWED_HOSTS,
    MAX_SOURCE_BYTES,
    TIMEOUT_SECONDS,
    authenticate_geometry_condition_multisource_policy,
)
from .in625_geometry_condition_source_acquisition import (
    acquire_geometry_condition_sources,
    fetch_exact_source,
)

ACTION_CLASS = "ammt_mds2_2923_calibration_protocol_bridge_evidence_acquisition"
NEXT_ACTION_CLASS = "experiment_specific_calibration_record_source_discovery"
IMPLEMENTATION_ID = "ammt-calibration-bridge-existing-source-adapter-v1"
FACTORY_ID = "existing-authorized-source-reacquisition-v1"
REQUIRED_VERIFIED_PRIMITIVES = (
    "exact_multisource_policy_authentication",
    "exact_allowlisted_source_acquisition",
    "provenance_bound_bridge_frontier_evaluation",
)
MULTISOURCE_POLICY_PATH = (
    "configs/research/in625_geometry_condition_multisource_acquisition_policy.v1.json"
)
MULTISOURCE_REGISTRY_PATH = (
    "configs/research/in625_geometry_condition_source_reconnaissance.v1.json"
)

_REQUIRED_CLAIMS = frozenset(
    {
        "amb2018-ammt-actual-power-correction",
        "benchmark-ammt-calibration-note",
        "benchmark-later-spot-size-correction-note",
        "lane-ammt-cbm-spot-diameters",
        "lane-ammt-corrected-cases",
        "lane-cross-section-uncertainty-exists",
        "naderi-ammt-spot-range",
        "naderi-spot-measurement-authority",
    }
)


class CalibrationProtocolBridgeCapabilityError(ValueError):
    """Raised when the bridge capability cannot preserve its exact authority."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CalibrationProtocolBridgeCapabilityError(message)


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _read_json(path: Path, field: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CalibrationProtocolBridgeCapabilityError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise CalibrationProtocolBridgeCapabilityError(f"{field} root must be an object")
    return value


def _source_claim_ids(evidence: Mapping[str, Any]) -> set[str]:
    sources = evidence.get("sources")
    _require(isinstance(sources, list), "source evidence list is missing")
    claim_ids: set[str] = set()
    for source in sources:
        _require(isinstance(source, Mapping), "source evidence entry must be an object")
        claims = source.get("claims")
        _require(isinstance(claims, list), "source claim receipts are missing")
        for claim in claims:
            _require(isinstance(claim, Mapping), "source claim receipt must be an object")
            if claim.get("matched") is True and isinstance(claim.get("claim_id"), str):
                claim_ids.add(claim["claim_id"])
    return claim_ids


def _source_sha_map(evidence: Mapping[str, Any]) -> dict[str, str]:
    sources = evidence.get("sources")
    _require(isinstance(sources, list), "source evidence list is missing")
    result: dict[str, str] = {}
    for source in sources:
        _require(isinstance(source, Mapping), "source evidence entry must be an object")
        source_id = source.get("source_id")
        source_sha = source.get("source_sha256")
        _require(
            isinstance(source_id, str) and isinstance(source_sha, str),
            "source SHA binding is missing",
        )
        result[source_id] = source_sha
    return result


def build_bridge_frontier_report(
    *,
    mapping_assessment: Mapping[str, Any],
    reacquired_evidence: Mapping[str, Any],
    prior_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Reassess only authenticated bridge facts and generate a narrower discovery action."""
    decision = mapping_assessment.get("gate_decision")
    _require(isinstance(decision, Mapping), "mapping gate decision is missing")
    _require(
        decision.get("directly_comparable_mds2_rows") == 0,
        "predecessor unexpectedly contains directly comparable rows",
    )
    _require(
        decision.get("direct_numerical_validation_authorized") is False,
        "predecessor improperly authorized direct numerical validation",
    )
    _require(
        decision.get("issue_76_exact_target_cells_satisfied") == 0,
        "predecessor improperly promoted Issue #76",
    )
    _require(
        reacquired_evidence.get("acquisition_status")
        == "exact_multisource_condition_evidence_acquired",
        "reacquired evidence status drifted",
    )
    _require(
        reacquired_evidence.get("source_count") == 8
        and reacquired_evidence.get("network_requests_performed") == 8
        and reacquired_evidence.get("all_claim_anchors_matched") is True,
        "reacquired source packet is incomplete",
    )
    _require(
        reacquired_evidence.get("paper_claims_promoted_to_row_level_authority") is False,
        "literature authority was improperly promoted",
    )
    claim_ids = _source_claim_ids(reacquired_evidence)
    _require(
        _REQUIRED_CLAIMS.issubset(claim_ids),
        "bridge capability required claim packet is incomplete",
    )

    current_source_shas = _source_sha_map(reacquired_evidence)
    source_version_changes: list[str] = []
    if prior_evidence is not None:
        prior_source_shas = _source_sha_map(prior_evidence)
        source_version_changes = sorted(
            source_id
            for source_id, source_sha in current_source_shas.items()
            if prior_source_shas.get(source_id) != source_sha
        )

    report: dict[str, Any] = {
        "schema_version": "1.0",
        "action_class": ACTION_CLASS,
        "execution_status": "authorized_bridge_sources_reacquired_and_frontier_refined",
        "source_count": 8,
        "network_requests_performed": 8,
        "reacquired_source_report_sha256": reacquired_evidence.get(
            "report_sha256_without_self_field"
        ),
        "source_version_changes": source_version_changes,
        "new_source_version_information": bool(source_version_changes),
        "established_by_authenticated_claim_packet": {
            "amb2018_ammt_actual_power_correction_exists": True,
            "later_ammt_and_cbm_spot_size_correction_exists": True,
            "ammt_spot_measurement_basis_is_documented": True,
            "cross_section_measurement_uncertainty_is_documented": True,
        },
        "still_unresolved": {
            "mds2_machine_setting_to_amb2018_calibrated_actual_power_bridge": True,
            "experiment_identity_equivalence_between_mds2_spot_sweep_and_amb2018_tracks": True,
            "experiment_specific_cross_section_protocol_equivalence": True,
            "experiment_specific_uncertainty_transfer": True,
        },
        "bridge_established": False,
        "directly_comparable_mds2_rows": 0,
        "direct_numerical_validation_authorized": False,
        "cross_machine_pooling_authorized": False,
        "paper_claims_promoted_to_row_level_authority": False,
        "issue_76_exact_target_cells_satisfied": 0,
        "network_failure_interpreted_as_negative_scientific_evidence": False,
        "scientific_status_changed": False,
        "next_action": {
            "action_class": NEXT_ACTION_CLASS,
            "objective": (
                "Discover an authoritative experiment-specific calibration record, supplement, "
                "repository artifact, or provenance-bound correspondence that explicitly links "
                "the mds2-2923 AMMT machine-setting experiment to calibrated laser power and "
                "protocol identity."
            ),
            "eligible_evidence_lanes": [
                "official_calibration_or_metrology_documentation",
                "paper_and_supplementary_material",
                "authoritative_repository_or_dataset",
                "provenance_bound_author_correspondence_or_repository_release",
            ],
            "automatic_unrestricted_search_authorized": False,
            "caller_authored_arbitrary_urls_authorized": False,
        },
    }
    report["report_sha256_without_self_field"] = _canonical_sha(report)
    return report


def smoke_exact_source_authority(
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
) -> dict[str, Any]:
    """Perform one exact-source network smoke under the already mission-pinned policy."""
    root = Path(repository_root).expanduser().resolve(strict=True)
    policy_path = (root / MULTISOURCE_POLICY_PATH).resolve(strict=True)
    registry_path = (root / MULTISOURCE_REGISTRY_PATH).resolve(strict=True)
    qualification = authenticate_geometry_condition_multisource_policy(
        repository_root=root,
        mission_path=mission_path,
        expected_mission_sha256=expected_mission_sha256,
        policy_path=policy_path,
        registry_path=registry_path,
    )
    registry = _read_json(registry_path, "multi-source source registry")
    sources = registry.get("sources")
    _require(isinstance(sources, list) and sources, "source registry is empty")
    first = sources[0]
    _require(isinstance(first, Mapping), "first source registry entry is invalid")
    source_id = first.get("source_id")
    url = first.get("url")
    _require(isinstance(source_id, str) and isinstance(url, str), "first source identity is invalid")
    fetched = fetch_exact_source(
        url,
        allowed_hosts=ALLOWED_HOSTS,
        max_bytes=MAX_SOURCE_BYTES,
        timeout_seconds=TIMEOUT_SECONDS,
    )
    receipt: dict[str, Any] = {
        "schema_version": "1.0",
        "smoke_status": "exact_authorized_source_retrieved",
        "policy_sha256": qualification["policy_sha256"],
        "registry_git_blob_sha1": qualification["registry_git_blob_sha1"],
        "source_id": source_id,
        "requested_url": url,
        "final_url": fetched.final_url,
        "source_sha256": hashlib.sha256(fetched.body).hexdigest(),
        "source_size_bytes": len(fetched.body),
        "network_requests_performed": 1,
        "unrestricted_search_performed": False,
        "arbitrary_url_fetch_performed": False,
        "scientific_status_changed": False,
    }
    receipt["smoke_receipt_sha256_without_self_field"] = _canonical_sha(receipt)
    return receipt


def execute_bridge_capability(
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    mapping_assessment: Mapping[str, Any],
    prior_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute the promoted adapter under the exact existing multi-source authority."""
    root = Path(repository_root).expanduser().resolve(strict=True)
    policy_path = (root / MULTISOURCE_POLICY_PATH).resolve(strict=True)
    registry_path = (root / MULTISOURCE_REGISTRY_PATH).resolve(strict=True)
    qualification = authenticate_geometry_condition_multisource_policy(
        repository_root=root,
        mission_path=mission_path,
        expected_mission_sha256=expected_mission_sha256,
        policy_path=policy_path,
        registry_path=registry_path,
    )
    registry = _read_json(registry_path, "multi-source source registry")
    reacquired = acquire_geometry_condition_sources(
        qualification=qualification,
        source_registry=registry,
    )
    return build_bridge_frontier_report(
        mapping_assessment=mapping_assessment,
        reacquired_evidence=reacquired,
        prior_evidence=prior_evidence,
    )


__all__ = [
    "ACTION_CLASS",
    "FACTORY_ID",
    "IMPLEMENTATION_ID",
    "NEXT_ACTION_CLASS",
    "REQUIRED_VERIFIED_PRIMITIVES",
    "CalibrationProtocolBridgeCapabilityError",
    "build_bridge_frontier_report",
    "execute_bridge_capability",
    "smoke_exact_source_authority",
]
