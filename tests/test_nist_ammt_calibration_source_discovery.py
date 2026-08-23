from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop import (
    in625_geometry_condition_source_acquisition,
)
from materials_data_analyzer.research_loop import (
    nist_ammt_calibration_source_discovery as discovery,
)
from materials_data_analyzer.research_loop import (
    nist_ammt_source_discovery_policy as policy,
)


ROOT = Path(__file__).resolve().parents[1]
MISSION = ROOT / "configs/research/autonomous_in625_production_mission.v1.json"
POLICY = ROOT / "configs/research/nist_ammt_publication_index_source_discovery_policy.v1.json"
MISSION_SHA = "7de1c78d1411805623a4687a6d1956517edc009abe5790a0870e89ab6ccb4e88"
POLICY_SHA = "e053faca2a28adae1d299d5771b6df4a99e1e15400b536e1f7502f34051a9324"


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False) + "\n").encode(
        "utf-8"
    )


def _qualification() -> dict[str, Any]:
    return policy.authenticate_nist_ammt_source_discovery_policy(
        repository_root=ROOT,
        mission_path=MISSION,
        expected_mission_sha256=MISSION_SHA,
        policy_path=POLICY,
    )


def test_exact_mission_pinned_discovery_policy_authenticates_without_network() -> None:
    assert hashlib.sha256(MISSION.read_bytes()).hexdigest() == MISSION_SHA
    assert hashlib.sha256(POLICY.read_bytes()).hexdigest() == POLICY_SHA
    result = _qualification()
    assert result["qualification_status"] == (
        "exact_nist_ammt_source_discovery_policy_authenticated"
    )
    assert result["source_url"] == "https://www.nist.gov/el/ammt/relevant-publications"
    assert result["allowed_hosts"] == ["www.nist.gov"]
    assert result["max_requests"] == 1
    assert result["network_access_performed"] is False
    assert result["candidate_urls_gain_acquisition_authority"] is False


def test_repinned_policy_cannot_widen_intrinsic_discovery_authority(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    config = root / "configs/research"
    config.mkdir(parents=True)

    forged_policy = json.loads(POLICY.read_text(encoding="utf-8"))
    forged_policy["network"]["allowed_hosts"].append("example.com")
    forged_policy["network"]["max_requests"] = 100
    policy_bytes = _json_bytes(forged_policy)
    policy_path = config / POLICY.name
    policy_path.write_bytes(policy_bytes)

    mission = json.loads(MISSION.read_text(encoding="utf-8"))
    pin = next(
        item
        for item in mission["source_trust_policy_pins"]
        if item["policy_id"] == policy.POLICY_ID
    )
    pin["sha256"] = hashlib.sha256(policy_bytes).hexdigest()
    mission_bytes = _json_bytes(mission)
    mission_path = config / MISSION.name
    mission_path.write_bytes(mission_bytes)

    with pytest.raises(
        policy.NistAmmtSourceDiscoveryPolicyError,
        match="discovery policy exact bytes drifted",
    ):
        policy.authenticate_nist_ammt_source_discovery_policy(
            repository_root=root,
            mission_path=mission_path,
            expected_mission_sha256=hashlib.sha256(mission_bytes).hexdigest(),
            policy_path=policy_path,
        )


def test_bad_mission_root_fails_before_discovery_network() -> None:
    with pytest.raises(
        policy.NistAmmtSourceDiscoveryPolicyError,
        match="mission bytes do not match independently supplied mission SHA-256",
    ):
        policy.authenticate_nist_ammt_source_discovery_policy(
            repository_root=ROOT,
            mission_path=MISSION,
            expected_mission_sha256="0" * 64,
            policy_path=POLICY,
        )


def test_discovery_filters_off_host_links_and_never_follows_candidates() -> None:
    fixture = b"""
    <html><body>
      <h1>AMMT Relevant Publications</h1>
      <ul>
        <li><a href='/publications/laser-calibration-powder-bed-fusion-additive-manufacturing-process'>Laser Calibration for Powder Bed Fusion Additive Manufacturing Process</a></li>
        <li><a href='https://doi.org/10.1000/example'>AMMT laser spot metrology DOI</a></li>
        <li><a href='https://evil.example/paper'>AMMT laser power calibration attacker</a></li>
      </ul>
    </body></html>
    """
    calls: list[tuple[str, int]] = []

    def fetcher(url: str, **kwargs: Any) -> in625_geometry_condition_source_acquisition.FetchResult:
        calls.append((url, kwargs["max_bytes"]))
        return in625_geometry_condition_source_acquisition.FetchResult(
            body=fixture,
            final_url=policy.SOURCE_URL,
            status_code=200,
            content_type="text/html; charset=utf-8",
        )

    result = discovery.discover_nist_ammt_calibration_sources(
        qualification=_qualification(),
        fetcher=fetcher,
    )
    assert calls == [(policy.SOURCE_URL, policy.MAX_TOTAL_BYTES)]
    assert result["network_requests_performed"] == 1
    assert result["candidate_count"] == 2
    assert {item["link_host"] for item in result["candidates"]} == {
        "www.nist.gov",
        "doi.org",
    }
    assert all(item["candidate_url_followed"] is False for item in result["candidates"])
    assert all(item["acquisition_authorized"] is False for item in result["candidates"])
    assert result["candidate_links_followed"] == 0
    assert result["candidate_urls_gain_acquisition_authority"] is False
    assert result["unrestricted_search_performed"] is False
    assert result["scientific_status_changed"] is False


def test_discovery_rejects_transport_redirect_outside_exact_nist_host() -> None:
    def fetcher(*args: Any, **kwargs: Any) -> in625_geometry_condition_source_acquisition.FetchResult:
        return in625_geometry_condition_source_acquisition.FetchResult(
            body=b"<html><body>AMMT Relevant Publications</body></html>",
            final_url="https://example.com/relevant-publications",
            status_code=200,
            content_type="text/html",
        )

    with pytest.raises(
        discovery.NistAmmtCalibrationSourceDiscoveryError,
        match="left exact NIST host authority",
    ):
        discovery.discover_nist_ammt_calibration_sources(
            qualification=_qualification(),
            fetcher=fetcher,
        )


def test_empty_ranked_result_is_not_global_evidence_absence() -> None:
    fixture = b"<html><body><h1>AMMT Relevant Publications</h1><ul><li>No linked calibration record here.</li></ul></body></html>"

    def fetcher(*args: Any, **kwargs: Any) -> in625_geometry_condition_source_acquisition.FetchResult:
        return in625_geometry_condition_source_acquisition.FetchResult(
            body=fixture,
            final_url=policy.SOURCE_URL,
            status_code=200,
            content_type="text/html",
        )

    result = discovery.discover_nist_ammt_calibration_sources(
        qualification=_qualification(),
        fetcher=fetcher,
    )
    assert result["candidate_count"] == 0
    assert result["global_evidence_unavailability_claimed"] is False
    assert result["scientific_status_changed"] is False
    assert result["next_action"]["automatic_acquisition_authorized"] is False
