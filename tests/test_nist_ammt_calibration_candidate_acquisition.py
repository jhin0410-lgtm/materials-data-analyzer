from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop import capability_expansion
from materials_data_analyzer.research_loop import capability_registry
from materials_data_analyzer.research_loop import capability_resolver
from materials_data_analyzer.research_loop import capability_verifier
from materials_data_analyzer.research_loop import nist_ammt_calibration_candidate_acquisition as acquisition
from materials_data_analyzer.research_loop import nist_ammt_calibration_candidate_bridge_assessment as assessment
from materials_data_analyzer.research_loop import nist_ammt_candidate_acquisition_policy as policy


ROOT = Path(__file__).resolve().parents[1]
MISSION = ROOT / "configs/research/autonomous_in625_production_mission.v1.json"
POLICY = ROOT / "configs/research/nist_ammt_calibration_candidate_derived_acquisition_policy.v1.json"
MISSION_SHA = "12cef407f27e6ff84bbee612c3fdf67c33b4a64ff326e84a76e70ece6441678d"
POLICY_SHA = "ef92f5d436a85f756d87e136ebc59a2cf64c932f8c599f23cd13c4c59bd8319b"
CANDIDATE_URL = (
    "https://www.nist.gov/publications/"
    "laser-calibration-powder-bed-fusion-additive-manufacturing-process"
)


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _discovery_report() -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "action_class": "experiment_specific_calibration_record_source_discovery",
        "discovery_status": "official_nist_ammt_publication_index_reviewed",
        "policy_id": "nist-ammt-publication-index-source-discovery-v1",
        "source_index": {
            "source_id": "nist-ammt-relevant-publications-index",
            "source_sha256": "a" * 64,
        },
        "candidate_links_followed": 0,
        "caller_authored_url_used": False,
        "candidate_urls_gain_acquisition_authority": False,
        "candidates": [
            {
                "candidate_id": "rank-1-candidate",
                "rank": 1,
                "url": CANDIDATE_URL,
                "link_host": "www.nist.gov",
                "discovered_from_source_id": "nist-ammt-relevant-publications-index",
                "candidate_url_followed": False,
                "acquisition_authorized": False,
                "row_level_measurement_authority": False,
            }
        ],
        "next_action": {
            "action_class": acquisition.ACTION_CLASS,
            "candidate_ids": ["rank-1-candidate"],
            "automatic_acquisition_authorized": False,
            "caller_authored_arbitrary_urls_authorized": False,
        },
    }
    report["report_sha256_without_self_field"] = _canonical_sha(report)
    return report


def _manifest(discovery_report: dict[str, Any]) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "nist_ammt_source_discovery_sha256": discovery_report[
            "report_sha256_without_self_field"
        ],
        "generated_next_action_class": acquisition.ACTION_CLASS,
        "third_capability_gap_emitted": True,
        "directly_comparable_mds2_rows": 0,
        "issue_76_exact_target_cells_satisfied": 0,
        "bridge_established": False,
    }
    manifest["manifest_sha256"] = _canonical_sha(manifest)
    return manifest


def _qualification() -> dict[str, Any]:
    return policy.authenticate_nist_ammt_candidate_acquisition_policy(
        repository_root=ROOT,
        mission_path=MISSION,
        expected_mission_sha256=MISSION_SHA,
        policy_path=POLICY,
    )


def _claim(claim_id: str, matched: bool) -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "matched": matched,
        "match_count": 1 if matched else 0,
        "matches": [] if not matched else [{"page_index_zero_based": 0}],
        "pattern_sha256": "f" * 64,
    }


def _acquisition_report() -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "action_class": acquisition.ACTION_CLASS,
        "acquisition_status": "derived_nist_calibration_candidate_and_full_text_acquired",
        "candidate_rank": 1,
        "candidate_url_derived_from_discovery": True,
        "full_text_url_derived_from_candidate_page": True,
        "network_requests_performed": 2,
        "caller_authored_url_used": False,
        "unrestricted_search_performed": False,
        "literature_promoted_to_row_level_measurement_authority": False,
        "acquisition_success_establishes_calibration_bridge": False,
        "scientific_status_changed": False,
        "claim_receipts": [
            _claim("digital_camera_in_situ_calibration_methodology", True),
            _claim("open_platform_testbed_experiment_scope", True),
            _claim("spot_calibration_200w_pulsed_condition", True),
            _claim("d4sigma_spot_definition", True),
            _claim("explicit_mds2_2923_identity", False),
            _claim("explicit_machine_setting_actual_power_bridge", False),
        ],
    }
    report["report_sha256_without_self_field"] = _canonical_sha(report)
    return report


def test_exact_derived_policy_and_mission_pins_authenticate_without_network() -> None:
    assert hashlib.sha256(MISSION.read_bytes()).hexdigest() == MISSION_SHA
    assert hashlib.sha256(POLICY.read_bytes()).hexdigest() == POLICY_SHA
    result = _qualification()
    assert result["qualification_status"] == (
        "exact_nist_ammt_candidate_acquisition_policy_authenticated"
    )
    assert result["required_candidate_rank"] == 1
    assert result["candidate_page_allowed_hosts"] == ["www.nist.gov"]
    assert result["full_text_allowed_hosts"] == ["tsapps.nist.gov"]
    assert result["max_requests"] == 2
    assert result["network_access_performed"] is False
    assert result["caller_authored_url_used"] is False


def test_policy_repinning_cannot_widen_intrinsic_authority(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    config = root / "configs/research"
    config.mkdir(parents=True)
    modified = json.loads(POLICY.read_text(encoding="utf-8"))
    modified["network"]["full_text_allowed_hosts"].append("evil.example")
    policy_bytes = (
        json.dumps(modified, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    ).encode("utf-8")
    policy_path = config / POLICY.name
    policy_path.write_bytes(policy_bytes)
    mission = json.loads(MISSION.read_text(encoding="utf-8"))
    pin = next(
        item
        for item in mission["source_trust_policy_pins"]
        if item["policy_id"] == policy.POLICY_ID
    )
    pin["sha256"] = hashlib.sha256(policy_bytes).hexdigest()
    mission_bytes = (
        json.dumps(mission, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    ).encode("utf-8")
    mission_path = config / MISSION.name
    mission_path.write_bytes(mission_bytes)
    with pytest.raises(
        policy.NistAmmtCandidateAcquisitionPolicyError,
        match="exact bytes drifted",
    ):
        policy.authenticate_nist_ammt_candidate_acquisition_policy(
            repository_root=root,
            mission_path=mission_path,
            expected_mission_sha256=hashlib.sha256(mission_bytes).hexdigest(),
            policy_path=policy_path,
        )


def test_authorization_is_derived_from_exact_rank1_discovery_candidate() -> None:
    discovery_report = _discovery_report()
    manifest = _manifest(discovery_report)
    result = acquisition.build_derived_candidate_authorization(
        qualification=_qualification(),
        discovery_report=discovery_report,
        predecessor_manifest=manifest,
    )
    assert result["candidate_id"] == "rank-1-candidate"
    assert result["candidate_rank"] == 1
    assert result["candidate_url"] == CANDIDATE_URL
    assert result["candidate_url_derived_from_discovery"] is True
    assert result["full_text_url_derived_from_candidate_page"] is False
    assert result["caller_authored_url_used"] is False
    assert result["scientific_status_change_authorized"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        lambda report: report["candidates"][0].__setitem__("rank", 2),
        lambda report: report["candidates"][0].__setitem__(
            "url", "https://evil.example/forged"
        ),
        lambda report: report["candidates"][0].__setitem__(
            "acquisition_authorized", True
        ),
    ],
)
def test_rank_url_or_authority_substitution_is_rejected_even_if_report_rehashed(
    mutation: Any,
) -> None:
    report = _discovery_report()
    mutation(report)
    report.pop("report_sha256_without_self_field")
    report["report_sha256_without_self_field"] = _canonical_sha(report)
    manifest = _manifest(report)
    with pytest.raises(acquisition.NistAmmtCalibrationCandidateAcquisitionError):
        acquisition.build_derived_candidate_authorization(
            qualification=_qualification(),
            discovery_report=report,
            predecessor_manifest=manifest,
        )


def test_cross_run_manifest_substitution_is_rejected() -> None:
    report = _discovery_report()
    manifest = _manifest(report)
    manifest["nist_ammt_source_discovery_sha256"] = "0" * 64
    manifest.pop("manifest_sha256")
    manifest["manifest_sha256"] = _canonical_sha(manifest)
    with pytest.raises(
        acquisition.NistAmmtCalibrationCandidateAcquisitionError,
        match="not bound to exact discovery report",
    ):
        acquisition.build_derived_candidate_authorization(
            qualification=_qualification(),
            discovery_report=report,
            predecessor_manifest=manifest,
        )


def test_candidate_page_accepts_only_one_valid_page_derived_local_download() -> None:
    body = b"""
    <html><body>
      <div>Published July 27, 2022</div><div>Author(s) Ho Yeung</div>
      <h3>Download Paper</h3>
      <a href='https://evil.example/forged.pdf'>Local Download</a>
      <a href='https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=935350'>Local Download</a>
    </body></html>
    """
    text, url = acquisition._parse_candidate_page(body, CANDIDATE_URL)
    assert "Published" in text
    assert url == "https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=935350"


def test_candidate_page_rejects_multiple_distinct_authorized_local_downloads() -> None:
    body = b"""
    <html><body>
      <div>Published July 27, 2022</div><div>Author(s) Ho Yeung</div>
      <h3>Download Paper</h3>
      <a href='https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=935350'>Local Download</a>
      <a href='https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=999999'>Local Download</a>
    </body></html>
    """
    with pytest.raises(
        acquisition.NistAmmtCalibrationCandidateAcquisitionError,
        match="exactly one authorized Local Download",
    ):
        acquisition._parse_candidate_page(body, CANDIDATE_URL)


def test_resolver_discovers_candidate_acquisition_only_with_all_verified_primitives() -> None:
    action = {
        "action_class": acquisition.ACTION_CLASS,
        "objective": "Acquire rank-1 derived calibration candidate.",
        "eligible_evidence_lanes": ["official_calibration_or_metrology_documentation"],
    }
    gap = capability_expansion.build_capability_gap(
        requested_action=action,
        predecessor_report=_discovery_report(),
        available_action_classes=[],
    )
    spec = capability_expansion.build_capability_specification(gap)
    registry = capability_registry.build_initial_capability_registry(
        verified_action_classes=[]
    )
    result = capability_resolver.resolve_or_discover_capability(
        registry=registry,
        capability_specification=spec,
        available_verified_primitives=acquisition.REQUIRED_VERIFIED_PRIMITIVES,
    )
    assert result["resolution_status"] == "bounded_candidate_discovered"
    assert result["candidate"]["implementation_id"] == acquisition.IMPLEMENTATION_ID
    missing = capability_resolver.resolve_or_discover_capability(
        registry=registry,
        capability_specification=spec,
        available_verified_primitives=acquisition.REQUIRED_VERIFIED_PRIMITIVES[:-1],
    )
    assert missing["resolution_status"] == "no_bounded_candidate_available"


def test_verifier_requires_predecessor_context_before_real_candidate_smoke() -> None:
    gap = capability_expansion.build_capability_gap(
        requested_action={
            "action_class": acquisition.ACTION_CLASS,
            "objective": "Acquire rank-1 candidate.",
            "eligible_evidence_lanes": [],
        },
        predecessor_report=_discovery_report(),
        available_action_classes=[],
    )
    spec = capability_expansion.build_capability_specification(gap)
    candidate = capability_registry.build_capability_candidate(
        capability_specification=spec,
        factory_id=acquisition.FACTORY_ID,
        implementation_id=acquisition.IMPLEMENTATION_ID,
        mechanism="generate_declarative_adapter_instance",
        required_verified_primitives=acquisition.REQUIRED_VERIFIED_PRIMITIVES,
    )
    with pytest.raises(
        capability_verifier.CapabilityVerifierError,
        match="requires predecessor context",
    ):
        capability_verifier.verify_bounded_capability_candidate(
            capability_specification=spec,
            candidate=candidate,
            available_verified_primitives=acquisition.REQUIRED_VERIFIED_PRIMITIVES,
            repository_root=ROOT,
            mission_path=MISSION,
            expected_mission_sha256=MISSION_SHA,
            perform_real_source_smoke=True,
        )


def test_scientific_assessment_preserves_methodology_but_blocks_exact_bridge() -> None:
    report = _discovery_report()
    manifest = _manifest(report)
    result = assessment.build_calibration_candidate_bridge_assessment(
        acquisition_report=_acquisition_report(),
        predecessor_manifest=manifest,
    )
    assert result["evidence_scope"][
        "digital_camera_in_situ_calibration_methodology_established"
    ] is True
    assert result["evidence_scope"]["d4sigma_spot_definition_established"] is True
    assert result["experiment_specific_bridge"][
        "exact_mds2_2923_experiment_identity_established"
    ] is False
    assert result["experiment_specific_bridge"][
        "exact_machine_setting_to_calibrated_power_relation_established"
    ] is False
    assert result["experiment_specific_bridge"]["bridge_established"] is False
    assert result["gate_decision"]["directly_comparable_mds2_rows"] == 0
    assert result["gate_decision"]["issue_76_exact_target_cells_satisfied"] == 0
    assert result["next_action"]["action_class"] == (
        "mds2_2923_experiment_identity_reference_chain_assessment"
    )


def test_unexpected_explicit_bridge_requires_independent_review_not_auto_promotion() -> None:
    report = _acquisition_report()
    for item in report["claim_receipts"]:
        if item["claim_id"] in {
            "explicit_mds2_2923_identity",
            "explicit_machine_setting_actual_power_bridge",
        }:
            item["matched"] = True
            item["match_count"] = 1
    report.pop("report_sha256_without_self_field")
    report["report_sha256_without_self_field"] = _canonical_sha(report)
    discovery_report = _discovery_report()
    manifest = _manifest(discovery_report)
    with pytest.raises(
        assessment.NistAmmtCalibrationCandidateBridgeAssessmentError,
        match="independent review required",
    ):
        assessment.build_calibration_candidate_bridge_assessment(
            acquisition_report=report,
            predecessor_manifest=manifest,
        )
