from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import weaver_2021_full_text_acquisition as acquisition
from materials_data_analyzer.research_loop import weaver_2021_full_text_policy as policy


ROOT = Path(__file__).resolve().parents[1]
MISSION = ROOT / "configs/research/autonomous_in625_production_mission.v1.json"
MISSION_SHA = "98d8730a4ba1221685267ed56cd7ae75f2ce60fcfdd8f8bb426a3825986c70ea"


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _reference_graph() -> dict[str, object]:
    graph: dict[str, object] = {
        "next_action": {
            "action_class": policy.ACTION_CLASS,
            "candidate": {
                "doi": policy.SOURCE_DOI,
                "title": policy.SOURCE_TITLE,
                "acquisition_authorized": False,
            },
            "automatic_acquisition_authorized": False,
            "caller_authored_url_authorized": False,
        },
        "scientific_status_changed": False,
    }
    graph["report_sha256_without_self_field"] = _canonical_sha(graph)
    return graph


def _manifest(graph: dict[str, object]) -> dict[str, object]:
    manifest: dict[str, object] = {
        "reference_chain_assessment_sha256": graph[
            "report_sha256_without_self_field"
        ],
        "generated_next_action_class": policy.ACTION_CLASS,
        "fifth_capability_gap_emitted": True,
    }
    manifest["manifest_sha256"] = _canonical_sha(manifest)
    return manifest


def _authorization() -> dict[str, object]:
    graph = _reference_graph()
    qualification = policy.authenticate_weaver_2021_full_text_policy(
        repository_root=ROOT,
        mission_path=MISSION,
        expected_mission_sha256=MISSION_SHA,
    )
    return acquisition.build_derived_weaver_authorization(
        qualification=qualification,
        reference_graph=graph,
        predecessor_manifest=_manifest(graph),
    )


def test_derived_authorization_carries_complete_authority_chain() -> None:
    authorization = _authorization()
    assert authorization["mission_sha256"] == policy.BASE_MISSION_SHA256
    assert authorization["authority_extension_id"] == policy.AUTHORITY_EXTENSION_ID
    assert authorization["authority_extension_sha256"] == policy.AUTHORITY_EXTENSION_SHA256
    assert authorization["policy_id"] == policy.POLICY_ID
    assert authorization["policy_sha256"] == policy.POLICY_SHA256


def test_spoofed_qualification_extension_is_rejected() -> None:
    graph = _reference_graph()
    qualification = policy.authenticate_weaver_2021_full_text_policy(
        repository_root=ROOT,
        mission_path=MISSION,
        expected_mission_sha256=MISSION_SHA,
    )
    forged = dict(qualification)
    forged["authority_extension_sha256"] = "0" * 64
    with pytest.raises(
        acquisition.Weaver2021FullTextAcquisitionError,
        match="qualification authority chain drifted",
    ):
        acquisition.build_derived_weaver_authorization(
            qualification=forged,
            reference_graph=graph,
            predecessor_manifest=_manifest(graph),
        )


def test_rehashed_authorization_extension_substitution_fails_before_fetch() -> None:
    forged = _authorization()
    forged["authority_extension_sha256"] = "0" * 64
    forged.pop("authorization_sha256")
    forged["authorization_sha256"] = _canonical_sha(forged)
    fetch_called = False

    def forbidden_fetch(*args: object, **kwargs: object) -> object:
        nonlocal fetch_called
        fetch_called = True
        raise AssertionError("network fetch must not occur")

    with pytest.raises(
        acquisition.Weaver2021FullTextAcquisitionError,
        match="authorization authority chain drifted",
    ):
        acquisition.execute_derived_weaver_acquisition(
            authorization=forged,
            fetcher=forbidden_fetch,  # type: ignore[arg-type]
        )
    assert fetch_called is False
