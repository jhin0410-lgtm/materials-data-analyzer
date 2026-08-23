from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop import (
    nist_ammt_candidate_acquisition_policy as acquisition_policy,
)
from materials_data_analyzer.research_loop import (
    nist_ammt_candidate_discovery_lineage as lineage,
)


ROOT = Path(__file__).resolve().parents[1]
MISSION = ROOT / "configs/research/autonomous_in625_production_mission.v1.json"
MISSION_SHA = "7de1c78d1411805623a4687a6d1956517edc009abe5790a0870e89ab6ccb4e88"
SOURCE_URL = "https://www.nist.gov/el/ammt/relevant-publications"
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


def _candidate_id(url: str = CANDIDATE_URL) -> str:
    return "nist-ammt-index-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _report() -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "action_class": "experiment_specific_calibration_record_source_discovery",
        "discovery_status": "official_nist_ammt_publication_index_reviewed",
        "policy_id": acquisition_policy.DISCOVERY_POLICY_ID,
        "policy_sha256": acquisition_policy.DISCOVERY_POLICY_SHA256,
        "source_index": {
            "source_id": acquisition_policy.DISCOVERY_SOURCE_ID,
            "requested_url": SOURCE_URL,
            "final_url": SOURCE_URL,
            "source_sha256": "a" * 64,
        },
        "candidate_links_followed": 0,
        "caller_authored_url_used": False,
        "unrestricted_search_performed": False,
        "candidate_urls_gain_acquisition_authority": False,
        "candidates": [
            {
                "candidate_id": _candidate_id(),
                "rank": 1,
                "url": CANDIDATE_URL,
                "link_host": "www.nist.gov",
                "discovered_from_source_id": acquisition_policy.DISCOVERY_SOURCE_ID,
                "candidate_url_followed": False,
                "acquisition_authorized": False,
                "row_level_measurement_authority": False,
            }
        ],
        "next_action": {
            "action_class": acquisition_policy.ACTION_CLASS,
            "candidate_ids": [_candidate_id()],
            "automatic_acquisition_authorized": False,
            "caller_authored_arbitrary_urls_authorized": False,
        },
    }
    report["report_sha256_without_self_field"] = _canonical_sha(report)
    return report


def _qualification() -> dict[str, Any]:
    return acquisition_policy.authenticate_nist_ammt_candidate_acquisition_policy(
        repository_root=ROOT,
        mission_path=MISSION,
        expected_mission_sha256=MISSION_SHA,
    )


def _rehash(report: dict[str, Any]) -> None:
    report.pop("report_sha256_without_self_field", None)
    report["report_sha256_without_self_field"] = _canonical_sha(report)


def test_exact_discovery_policy_source_and_rank1_lineage_verifies() -> None:
    result = lineage.verify_discovery_lineage(
        qualification=_qualification(),
        discovery_report=_report(),
    )
    assert result["verification_status"] == (
        "exact_discovery_policy_source_and_rank1_lineage_verified"
    )
    assert result["discovery_policy_sha256"] == (
        acquisition_policy.DISCOVERY_POLICY_SHA256
    )
    assert result["source_index_url"] == SOURCE_URL
    assert result["candidate_id"] == _candidate_id()
    assert result["candidate_rank"] == 1
    assert result["candidate_url"] == CANDIDATE_URL
    assert result["network_access_performed"] is False
    assert result["acquisition_authority_granted"] is False
    assert result["scientific_status_changed"] is False


def test_self_consistent_wrong_discovery_policy_sha_is_rejected() -> None:
    report = _report()
    report["policy_sha256"] = "0" * 64
    _rehash(report)
    with pytest.raises(
        lineage.NistAmmtCandidateDiscoveryLineageError,
        match="exact mission-pinned discovery policy",
    ):
        lineage.verify_discovery_lineage(
            qualification=_qualification(),
            discovery_report=report,
        )


@pytest.mark.parametrize("field", ["requested_url", "final_url"])
def test_self_consistent_source_index_url_substitution_is_rejected(field: str) -> None:
    report = _report()
    report["source_index"][field] = "https://www.nist.gov/forged-index"
    _rehash(report)
    with pytest.raises(
        lineage.NistAmmtCandidateDiscoveryLineageError,
        match="source-index identity/URL lineage drifted",
    ):
        lineage.verify_discovery_lineage(
            qualification=_qualification(),
            discovery_report=report,
        )


def test_self_consistent_candidate_id_not_derived_from_url_is_rejected() -> None:
    report = _report()
    report["candidates"][0]["candidate_id"] = "nist-ammt-index-deadbeefdeadbeef"
    report["next_action"]["candidate_ids"] = ["nist-ammt-index-deadbeefdeadbeef"]
    _rehash(report)
    with pytest.raises(
        lineage.NistAmmtCandidateDiscoveryLineageError,
        match="candidate ID is not derived from its exact URL",
    ):
        lineage.verify_discovery_lineage(
            qualification=_qualification(),
            discovery_report=report,
        )


def test_reauthorized_candidate_flag_is_rejected_even_when_report_rehashed() -> None:
    report = _report()
    report["candidates"][0]["acquisition_authorized"] = True
    _rehash(report)
    with pytest.raises(
        lineage.NistAmmtCandidateDiscoveryLineageError,
        match="authority/provenance drifted",
    ):
        lineage.verify_discovery_lineage(
            qualification=_qualification(),
            discovery_report=report,
        )


def test_qualification_with_wrong_discovery_lineage_is_rejected() -> None:
    qualification = copy.deepcopy(_qualification())
    qualification["required_discovery_policy_sha256"] = "0" * 64
    with pytest.raises(
        lineage.NistAmmtCandidateDiscoveryLineageError,
        match="qualification discovery lineage drifted",
    ):
        lineage.verify_discovery_lineage(
            qualification=qualification,
            discovery_report=_report(),
        )
