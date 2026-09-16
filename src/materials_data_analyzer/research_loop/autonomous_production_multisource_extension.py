"""Extend autonomous IN625 production with reviewed paper/official condition mapping."""
from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .autonomous_production_nist_extension import (
    run_autonomous_production as run_nist_autonomous_production,
)
from .in625_geometry_condition_mapping_assessment import (
    ACTION_CLASS as MAPPING_ACTION_CLASS,
    NEXT_ACTION_CLASS as MAPPING_NEXT_ACTION_CLASS,
    build_geometry_condition_mapping_assessment,
)
from .in625_geometry_condition_multisource_policy import (
    POLICY_ID as MULTISOURCE_POLICY_ID,
    authenticate_geometry_condition_multisource_policy,
)
from .in625_geometry_condition_source_acquisition import (
    FetchResult,
    acquire_geometry_condition_sources,
    fetch_exact_source,
)

AUTONOMOUS_PRODUCTION_SCHEMA_VERSION = "1.3"
AUTONOMOUS_PRODUCTION_POLICY_VERSION = "1.3"
MULTISOURCE_POLICY_PATH = (
    "configs/research/in625_geometry_condition_multisource_acquisition_policy.v1.json"
)
MULTISOURCE_REGISTRY_PATH = (
    "configs/research/in625_geometry_condition_source_reconnaissance.v1.json"
)
TARGET_PROCESS_PATH = "data/case_studies/nist_ambench_2018_02/source_process_conditions.csv"
TARGET_RESPONSE_PATH = (
    "data/case_studies/nist_ambench_2018_02/source_melt_pool_measurements.csv"
)
_AVAILABLE_ACTION_CLASSES = (
    "external_evidence_search",
    "reviewed_physical_comparability_assessment",
    "nist_mds2_2923_geometry_evidence_acquisition",
    MAPPING_ACTION_CLASS,
)


class AutonomousProductionMultisourceExtensionError(ValueError):
    """Raised when multi-source production cannot preserve exact authority."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionMultisourceExtensionError(message)


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
        raise AutonomousProductionMultisourceExtensionError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise AutonomousProductionMultisourceExtensionError(f"{field} root must be an object")
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _resolved_output(root: Path, output_root: str | Path) -> Path:
    output = Path(output_root).expanduser()
    if not output.is_absolute():
        output = root / output
    output = output.resolve(strict=True)
    try:
        output.relative_to(root)
    except ValueError as exc:
        raise AutonomousProductionMultisourceExtensionError(
            "autonomous production output escaped repository root"
        ) from exc
    return output


def _maximum_cycle_stop(next_action: str) -> dict[str, Any]:
    return {
        "status": "stopped",
        "reason_code": "maximum_cycles_reached",
        "requested_action_class": next_action,
        "available_production_action_classes": list(_AVAILABLE_ACTION_CLASSES),
        "global_evidence_unavailability_claimed": False,
        "positive_scientific_closeout": False,
        "scientific_status_changed": False,
    }


def _bounded_capability_stop(next_action: str) -> dict[str, Any]:
    _require(
        next_action not in _AVAILABLE_ACTION_CLASSES,
        "bounded stop received implemented capability",
    )
    return {
        "status": "stopped",
        "reason_code": "registered_capability_unavailable_for_current_next_action",
        "requested_action_class": next_action,
        "available_production_action_classes": list(_AVAILABLE_ACTION_CLASSES),
        "scope": "exact_current_autonomous_production_capability_set",
        "global_evidence_unavailability_claimed": False,
        "network_failure_interpreted_as_negative_scientific_evidence": False,
        "positive_scientific_closeout": False,
        "scientific_status_changed": False,
    }


def _capturing_multisource_fetcher(
    registry: Mapping[str, Any],
) -> tuple[Any, dict[str, bytes]]:
    """Capture the exact bytes returned by each authorized first-pass source fetch."""
    sources = registry.get("sources")
    _require(
        isinstance(sources, list) and len(sources) == 8,
        "multi-source registry must contain exactly eight sources",
    )
    allowed_urls: set[str] = set()
    for index, raw_source in enumerate(sources, start=1):
        _require(
            isinstance(raw_source, Mapping),
            f"multi-source registry entry {index} must be an object",
        )
        url = raw_source.get("url")
        _require(
            isinstance(url, str) and bool(url),
            f"multi-source registry entry {index} URL is missing",
        )
        _require(url not in allowed_urls, "multi-source registry contains duplicate URLs")
        allowed_urls.add(url)

    captured: dict[str, bytes] = {}

    def fetcher(
        url: str,
        *,
        allowed_hosts: tuple[str, ...],
        max_bytes: int,
        timeout_seconds: float,
    ) -> FetchResult:
        _require(url in allowed_urls, "capture fetch escaped the trusted source registry")
        _require(url not in captured, "capture fetch repeated a trusted source URL")
        result = fetch_exact_source(
            url,
            allowed_hosts=allowed_hosts,
            max_bytes=max_bytes,
            timeout_seconds=timeout_seconds,
        )
        captured[url] = bytes(result.body)
        return result

    return fetcher, captured


def _attach_retained_source_bytes(
    evidence: dict[str, Any],
    captured: Mapping[str, bytes],
) -> None:
    """Bind exact first-fetch bytes into the self-hashed acquisition report."""
    records = evidence.get("sources")
    _require(
        isinstance(records, list) and len(records) == 8,
        "multi-source evidence records are incomplete",
    )
    observed_urls: set[str] = set()
    for index, raw_record in enumerate(records, start=1):
        _require(
            isinstance(raw_record, dict),
            f"multi-source evidence record {index} must be mutable JSON",
        )
        requested_url = raw_record.get("requested_url")
        _require(
            isinstance(requested_url, str) and requested_url in captured,
            f"multi-source evidence record {index} has no retained fetch bytes",
        )
        _require(
            requested_url not in observed_urls,
            "multi-source evidence contains a duplicate requested URL",
        )
        observed_urls.add(requested_url)
        body = captured[requested_url]
        _require(
            hashlib.sha256(body).hexdigest() == raw_record.get("source_sha256")
            and len(body) == raw_record.get("source_size_bytes"),
            f"multi-source evidence record {index} drifted before byte retention",
        )
        raw_record["source_bytes_b64"] = base64.b64encode(body).decode("ascii")
        raw_record["source_bytes_persisted"] = True

    _require(
        len(observed_urls) == len(captured) == 8,
        "multi-source retained fetch byte count drifted",
    )
    evidence["source_bytes_persisted"] = True
    evidence["retained_source_bytes_count"] = 8
    evidence.pop("report_sha256_without_self_field", None)
    evidence["report_sha256_without_self_field"] = _canonical_sha(evidence)


def run_autonomous_production(
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    output_root: str | Path,
    max_cycles: int = 5,
) -> dict[str, Any]:
    """Run the proven NIST path, then exact multi-source condition mapping when generated."""
    if (
        isinstance(max_cycles, bool)
        or not isinstance(max_cycles, int)
        or max_cycles < 1
        or max_cycles > 8
    ):
        raise AutonomousProductionMultisourceExtensionError(
            "max_cycles must be an integer from 1 to 8"
        )
    root = Path(repository_root).expanduser().resolve(strict=True)
    mission = Path(mission_path).expanduser().resolve(strict=True)
    try:
        mission.relative_to(root)
    except ValueError as exc:
        raise AutonomousProductionMultisourceExtensionError(
            "mission_path must remain inside repository_root"
        ) from exc
    _require(
        hashlib.sha256(mission.read_bytes()).hexdigest() == expected_mission_sha256,
        "mission bytes do not match independently pinned mission SHA-256",
    )

    nist_cycles = min(max_cycles, 3)
    base_manifest = run_nist_autonomous_production(
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=expected_mission_sha256,
        output_root=output_root,
        max_cycles=nist_cycles,
    )
    if max_cycles <= 3:
        return base_manifest

    output = _resolved_output(root, output_root)
    manifest = _read_json(
        output / "autonomous-production-manifest.json",
        "NIST production manifest",
    )
    intake = _read_json(output / "nist-scientific-intake.json", "NIST scientific intake")
    rediagnosis = _read_json(
        output / "nist-post-acquisition-rediagnosis.json",
        "post-NIST re-diagnosis",
    )
    _require(
        manifest.get("generated_next_action_class") == MAPPING_ACTION_CLASS,
        "NIST production result did not generate reviewed geometry condition mapping",
    )
    _require(
        rediagnosis.get("next_action", {}).get("action_class") == MAPPING_ACTION_CLASS,
        "post-NIST re-diagnosis action drifted",
    )
    cycles = manifest.get("cycles")
    _require(
        isinstance(cycles, list) and len(cycles) == 3,
        "NIST base cycle history drifted",
    )

    policy_path = (root / MULTISOURCE_POLICY_PATH).resolve(strict=True)
    registry_path = (root / MULTISOURCE_REGISTRY_PATH).resolve(strict=True)
    qualification = authenticate_geometry_condition_multisource_policy(
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=expected_mission_sha256,
        policy_path=policy_path,
        registry_path=registry_path,
    )
    _require(
        qualification["network_access_performed"] is False,
        "policy qualification claimed network access",
    )
    _write_json(output / "multisource-policy-qualification.json", qualification)

    registry = _read_json(registry_path, "multi-source registry")
    retaining_fetcher, captured = _capturing_multisource_fetcher(registry)
    evidence = acquire_geometry_condition_sources(
        qualification=qualification,
        source_registry=registry,
        fetcher=retaining_fetcher,
    )
    _require(
        evidence["network_requests_performed"] == 8,
        "multi-source acquisition did not perform exactly eight requests",
    )
    _require(
        evidence["all_claim_anchors_matched"] is True,
        "multi-source claim acquisition incomplete",
    )
    _require(
        evidence["paper_claims_promoted_to_row_level_authority"] is False,
        "paper claim authority was promoted",
    )
    _attach_retained_source_bytes(evidence, captured)
    _write_json(output / "multisource-source-acquisition.json", evidence)

    mapping = build_geometry_condition_mapping_assessment(
        nist_intake=intake,
        multisource_evidence=evidence,
        target_process_bytes=(root / TARGET_PROCESS_PATH).read_bytes(),
        target_response_bytes=(root / TARGET_RESPONSE_PATH).read_bytes(),
    )
    _require(
        mapping["gate_decision"]["directly_comparable_mds2_rows"] == 0,
        "mapping unexpectedly created directly comparable mds2 rows",
    )
    _require(
        mapping["gate_decision"]["direct_numerical_validation_authorized"] is False,
        "mapping improperly authorized direct numerical validation",
    )
    _require(
        mapping["gate_decision"]["issue_76_exact_target_cells_satisfied"] == 0,
        "mapping improperly promoted Issue #76",
    )
    _require(
        mapping["next_action"]["action_class"] == MAPPING_NEXT_ACTION_CLASS,
        "mapping next action drifted",
    )
    _write_json(output / "geometry-condition-mapping-assessment.json", mapping)

    cycle3 = cycles[-1]
    cycle4: dict[str, Any] = {
        "cycle_index": 4,
        "predecessor_cycle_sha256": cycle3["cycle_sha256"],
        "input_blocker": "geometry_condition_mapping_not_established",
        "selected_action_class": MAPPING_ACTION_CLASS,
        "handler": "provenance_bound_multisource_geometry_condition_mapping",
        "capability_available": True,
        "network_policy_id": MULTISOURCE_POLICY_ID,
        "network_policy_sha256": qualification["policy_sha256"],
        "source_registry_git_blob_sha1": qualification["registry_git_blob_sha1"],
        "source_acquisition_report_sha256": evidence["report_sha256_without_self_field"],
        "source_count": 8,
        "network_requests_performed": 8,
        "mapping_assessment_sha256": mapping["report_sha256_without_self_field"],
        "directly_comparable_mds2_rows": 0,
        "eos_rows_excluded_from_direct_mapping": 144,
        "paper_claims_promoted_to_row_level_authority": False,
        "direct_numerical_validation_authorized": False,
        "issue_76_exact_target_cells_satisfied": 0,
        "output_blocker": "experiment_specific_calibration_protocol_bridge_not_established",
        "output_next_action_class": MAPPING_NEXT_ACTION_CLASS,
        "new_verified_information": True,
        "scientific_status_changed": False,
    }
    cycle4["cycle_sha256"] = _canonical_sha(cycle4)
    cycles.append(cycle4)

    if max_cycles < 5:
        stop = _maximum_cycle_stop(MAPPING_NEXT_ACTION_CLASS)
    else:
        stop = _bounded_capability_stop(MAPPING_NEXT_ACTION_CLASS)
        cycle5: dict[str, Any] = {
            "cycle_index": 5,
            "predecessor_cycle_sha256": cycle4["cycle_sha256"],
            "input_blocker": "experiment_specific_calibration_protocol_bridge_not_established",
            "selected_action_class": MAPPING_NEXT_ACTION_CLASS,
            "capability_available": False,
            "eligible_evidence_lanes": mapping["next_action"]["eligible_evidence_lanes"],
            "stop_reason_code": stop["reason_code"],
            "global_evidence_unavailability_claimed": False,
            "new_verified_information": False,
            "scientific_status_changed": False,
        }
        cycle5["cycle_sha256"] = _canonical_sha(cycle5)
        cycles.append(cycle5)

    final_manifest = dict(manifest)
    final_manifest.pop("manifest_sha256", None)
    final_manifest.update(
        {
            "schema_version": AUTONOMOUS_PRODUCTION_SCHEMA_VERSION,
            "policy_version": AUTONOMOUS_PRODUCTION_POLICY_VERSION,
            "cycles": cycles,
            "stop": stop,
            "multisource_condition_policy_sha256": qualification["policy_sha256"],
            "multisource_condition_registry_git_blob_sha1": qualification[
                "registry_git_blob_sha1"
            ],
            "multisource_condition_source_count": 8,
            "multisource_condition_network_requests_performed": 8,
            "multisource_condition_source_acquisition_sha256": evidence[
                "report_sha256_without_self_field"
            ],
            "geometry_condition_mapping_assessment_sha256": mapping[
                "report_sha256_without_self_field"
            ],
            "geometry_condition_mapping_review_completed": True,
            "geometry_condition_mapping_established": False,
            "directly_comparable_mds2_rows": 0,
            "paper_evidence_promoted_to_row_level_authority": False,
            "direct_numerical_cross_source_validation_authorized": False,
            "issue_76_exact_target_cells_satisfied": 0,
            "final_blocker": "experiment_specific_calibration_protocol_bridge_not_established",
            "generated_next_action_class": MAPPING_NEXT_ACTION_CLASS,
            "scientific_status_changed": False,
            "empirical_model_validation_established": False,
            "hypothesis_truth_established": False,
            "positive_scientific_closeout_established": False,
            "global_evidence_unavailability_claimed": False,
        }
    )
    final_manifest["manifest_sha256"] = _canonical_sha(final_manifest)
    _write_json(output / "bounded-stop.json", stop)
    _write_json(output / "autonomous-production-manifest.json", final_manifest)
    return final_manifest


__all__ = [
    "AUTONOMOUS_PRODUCTION_POLICY_VERSION",
    "AUTONOMOUS_PRODUCTION_SCHEMA_VERSION",
    "AutonomousProductionMultisourceExtensionError",
    "run_autonomous_production",
]
