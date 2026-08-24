from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import capability_expansion, capability_registry
from materials_data_analyzer.research_loop import capability_resolver
from materials_data_analyzer.research_loop import (
    autonomous_production_weaver_extension as production,
)
from materials_data_analyzer.research_loop.in625_geometry_condition_source_acquisition import FetchResult
from materials_data_analyzer.research_loop import weaver_2021_full_text_acquisition as acquisition
from materials_data_analyzer.research_loop import weaver_2021_full_text_capability as capability
from materials_data_analyzer.research_loop import weaver_2021_full_text_capability_verifier as verifier
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
            "action_class": capability.ACTION_CLASS,
            "objective": "Acquire exact Weaver primary full text.",
            "candidate": {
                "doi": policy.SOURCE_DOI,
                "title": policy.SOURCE_TITLE,
                "official_index_candidate_id": "weaver-candidate",
                "official_index_rank": 4,
                "discovered_url": "https://www.nist.gov/publications/weaver-metadata-only",
                "acquisition_authorized": False,
            },
            "caller_authored_url_authorized": False,
            "automatic_acquisition_authorized": False,
            "unrestricted_search_authorized": False,
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
        "generated_next_action_class": capability.ACTION_CLASS,
        "fifth_capability_gap_emitted": True,
        "fifth_capability_candidate_discovered": True,
        "fifth_capability_candidate_promoted": False,
        "bridge_established": False,
        "directly_comparable_mds2_rows": 0,
        "issue_76_exact_target_cells_satisfied": 0,
    }
    manifest["manifest_sha256"] = _canonical_sha(manifest)
    return manifest


def _fixture_bioc() -> bytes:
    text = " ".join(
        [
            policy.SOURCE_TITLE,
            policy.SOURCE_DOI,
            policy.SOURCE_PMCID,
            policy.SOURCE_PMID,
            "Jordan S. Weaver Jarred C. Heigel Brandon M. Lane",
            "The primary laser power and speed combination was 195 W and 800 mm/s with D4 spot diameters from 50 to 322 um.",
            "Cross-sections of single track laser scans produced on the AMMT machine for a fixed laser power and scan speed of 195 W and 800 mm/s with increasing spot diameter.",
            "Throughout this document the term spot size presumes a rotationally-symmetric Gaussian beam profile; we refer to the beam diameter using the D4σ definition, where D4σ = 4σ.",
            "Single scan laser tracks on IN625 were cross-sectioned and metallographically prepared, etched using Aqua Regia, and melt pool depth was measured.",
            "The data set contains 80 single track laser scans.",
        ]
    )
    return json.dumps(
        [{"source": "PMC", "documents": [{"id": policy.SOURCE_PMCID, "passages": [{"text": text}]}]}],
        ensure_ascii=False,
    ).encode("utf-8")


def test_policy_is_exactly_pinned_by_mission() -> None:
    assert hashlib.sha256(MISSION.read_bytes()).hexdigest() == MISSION_SHA
    qualification = policy.authenticate_weaver_2021_full_text_policy(
        repository_root=ROOT,
        mission_path=MISSION,
        expected_mission_sha256=MISSION_SHA,
    )
    assert qualification["policy_sha256"] == policy.POLICY_SHA256
    assert qualification["authority_extension_sha256"] == policy.AUTHORITY_EXTENSION_SHA256
    assert qualification["source_doi"] == policy.SOURCE_DOI
    assert qualification["source_pmcid"] == policy.SOURCE_PMCID
    assert qualification["network_access_performed"] is False
    assert qualification["caller_authored_url_used"] is False


def test_weaver_ammt_claim_does_not_invent_numeric_spot_range() -> None:
    claim = next(item for item in policy.CLAIMS if item[0] == "weaver-ammt-machine-condition")
    fragments = claim[1]
    scope = claim[2]
    assert "50" not in fragments
    assert "256" not in fragments
    assert "50" not in scope
    assert "256" not in scope
    assert fragments == (
        "AMMT machine",
        "fixed laser power and scan speed",
        "195 W",
        "800 mm",
        "increasing spot diameter",
    )


def test_resolver_discovers_only_bounded_weaver_factory() -> None:
    graph = _reference_graph()
    gap = capability_expansion.build_capability_gap(
        requested_action=graph["next_action"],  # type: ignore[arg-type]
        predecessor_report=graph,
        available_action_classes=[],
    )
    spec = capability_expansion.build_capability_specification(gap)
    result = capability_resolver.resolve_or_discover_capability(
        registry=capability_registry.build_initial_capability_registry(
            verified_action_classes=[]
        ),
        capability_specification=spec,
        available_verified_primitives=capability.REQUIRED_VERIFIED_PRIMITIVES,
    )
    assert result["resolution_status"] == "bounded_candidate_discovered"
    assert result["factory_id"] == capability.FACTORY_ID
    assert result["factory_catalogue_size"] == 5
    assert result["candidate"]["implementation_id"] == capability.IMPLEMENTATION_ID
    assert result["candidate"]["network_authority_granted"] is False
    assert result["candidate"]["execution_authority_granted"] is False


def test_derived_authorization_binds_reference_graph_and_rejects_locator_substitution() -> None:
    graph = _reference_graph()
    manifest = _manifest(graph)
    qualification = policy.authenticate_weaver_2021_full_text_policy(
        repository_root=ROOT,
        mission_path=MISSION,
        expected_mission_sha256=MISSION_SHA,
    )
    authorization = acquisition.build_derived_weaver_authorization(
        qualification=qualification,
        reference_graph=graph,
        predecessor_manifest=manifest,
    )
    assert authorization["doi"] == policy.SOURCE_DOI
    assert authorization["pmcid"] == policy.SOURCE_PMCID
    assert authorization["doi_derived_from_reference_graph"] is True
    assert authorization["pmcid_derived_from_separately_pinned_policy"] is True
    assert authorization["caller_authored_url_used"] is False
    assert authorization["caller_authored_pmcid_used"] is False

    forged = json.loads(json.dumps(graph))
    forged["next_action"]["candidate"]["doi"] = "10.1000/attacker"
    forged.pop("report_sha256_without_self_field")
    forged["report_sha256_without_self_field"] = _canonical_sha(forged)
    forged_manifest = _manifest(forged)
    with pytest.raises(acquisition.Weaver2021FullTextAcquisitionError):
        acquisition.build_derived_weaver_authorization(
            qualification=qualification,
            reference_graph=forged,
            predecessor_manifest=forged_manifest,
        )


def test_fixture_acquisition_verifies_identity_and_preserves_scientific_gate() -> None:
    graph = _reference_graph()
    manifest = _manifest(graph)
    qualification = policy.authenticate_weaver_2021_full_text_policy(
        repository_root=ROOT,
        mission_path=MISSION,
        expected_mission_sha256=MISSION_SHA,
    )
    authorization = acquisition.build_derived_weaver_authorization(
        qualification=qualification,
        reference_graph=graph,
        predecessor_manifest=manifest,
    )

    def fake_fetcher(*args: object, **kwargs: object) -> FetchResult:
        del args, kwargs
        return FetchResult(
            body=_fixture_bioc(),
            final_url=policy.SOURCE_URL,
            status_code=200,
            content_type="application/json; charset=utf-8",
        )

    report = acquisition.execute_derived_weaver_acquisition(
        authorization=authorization,
        fetcher=fake_fetcher,
    )
    claims = {item["claim_id"]: item for item in report["claim_receipts"]}
    assert report["article_identity"]["article_identity_established"] is True
    assert report["core_claims_matched"] is True
    assert claims["weaver-primary-condition"]["matched"] is True
    assert claims["weaver-ammt-machine-condition"]["matched"] is True
    assert claims["weaver-d4sigma-definition"]["matched"] is True
    assert claims["weaver-cross-section-protocol"]["matched"] is True
    assert claims["weaver-dataset-size"]["matched"] is True
    assert claims["weaver-explicit-mds2-id"]["matched"] is False
    assert claims["weaver-explicit-power-conversion"]["matched"] is False
    gate = report["gate_assessment"]
    assert gate["exact_mds2_experiment_identity_established"] is False
    assert gate["machine_setting_to_calibrated_power_relation_established"] is False
    assert gate["directly_comparable_mds2_rows"] == 0
    assert gate["direct_numerical_cross_source_validation_authorized"] is False
    assert gate["issue_76_exact_target_cells_satisfied"] == 0
    assert report["literature_promoted_to_row_level_measurement_authority"] is False
    assert report["next_action"]["action_class"] == (
        "mds2_2923_weaver_row_identity_binding_assessment"
    )


def test_verifier_refuses_promotion_when_core_claims_do_not_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _reference_graph()
    manifest = _manifest(graph)
    gap = capability_expansion.build_capability_gap(
        requested_action=graph["next_action"],  # type: ignore[arg-type]
        predecessor_report=graph,
        available_action_classes=[],
    )
    spec = capability_expansion.build_capability_specification(gap)
    candidate = capability_registry.build_capability_candidate(
        capability_specification=spec,
        factory_id=capability.FACTORY_ID,
        implementation_id=capability.IMPLEMENTATION_ID,
        mechanism=capability.MECHANISM,
        required_verified_primitives=capability.REQUIRED_VERIFIED_PRIMITIVES,
    )
    fake_report: dict[str, object] = {
        "acquisition_status": "exact_weaver_primary_full_text_acquired_and_identity_verified",
        "article_identity": {"article_identity_established": True},
        "source": {"source_sha256": "a" * 64},
        "core_claims_matched": False,
        "evidence_scope": {
            "weaver_full_text_acquired": True,
            "weaver_article_identity_established": True,
        },
        "gate_assessment": {
            "exact_mds2_rows_to_weaver_experiment_established": False,
            "exact_mds2_experiment_identity_established": False,
            "machine_setting_to_calibrated_power_relation_established": False,
            "spot_size_transfer_authorized": False,
            "protocol_equivalence_established": False,
            "uncertainty_transfer_authorized": False,
            "directly_comparable_mds2_rows": 0,
            "direct_numerical_cross_source_validation_authorized": False,
            "cross_machine_pooling_authorized": False,
            "issue_76_exact_target_cells_satisfied": 0,
        },
        "network_requests_performed": 1,
        "caller_authored_url_used": False,
        "caller_authored_pmcid_used": False,
        "unrestricted_search_performed": False,
        "literature_promoted_to_row_level_measurement_authority": False,
        "acquisition_success_establishes_scientific_bridge": False,
        "scientific_status_changed": False,
        "positive_scientific_closeout": False,
        "global_evidence_unavailability_claimed": False,
        "next_action": {
            "action_class": acquisition.NEXT_ACTION_CLASS,
            "automatic_execution_authorized": False,
            "network_access_required": False,
        },
        "report_sha256_without_self_field": "b" * 64,
    }
    monkeypatch.setattr(
        acquisition,
        "execute_derived_weaver_acquisition",
        lambda **kwargs: fake_report,
    )
    receipt = verifier.verify_weaver_2021_full_text_capability_candidate(
        capability_specification=spec,
        candidate=candidate,
        available_verified_primitives=capability.REQUIRED_VERIFIED_PRIMITIVES,
        repository_root=ROOT,
        mission_path=MISSION,
        expected_mission_sha256=MISSION_SHA,
        verification_context={"reference_graph": graph, "predecessor_manifest": manifest},
        perform_real_source_smoke=True,
    )
    assert receipt["verification_results"][
        "real_source_smoke_test_when_network_evidence_is_required"
    ] is False
    assert receipt["promotion_eligible"] is False
    assert receipt["real_source_smoke_receipt"]["core_claims_matched"] is False


def test_execution_must_match_independently_verified_weaver_bytes() -> None:
    evidence: dict[str, object] = {
        "core_claims_matched": True,
        "source": {"source_sha256": "a" * 64},
    }
    evidence["report_sha256_without_self_field"] = _canonical_sha(evidence)
    smoke: dict[str, object] = {
        "network_requests_performed": 2,
        "execution_evidence_reuse_authorized": False,
        "core_claims_matched": True,
        "evidence_self_hash_recomputed": True,
        "weaver_evidence_sha256": evidence["report_sha256_without_self_field"],
        "weaver_source_sha256": "a" * 64,
    }
    smoke["report_sha256_without_self_field"] = _canonical_sha(smoke)
    verification = {"real_source_smoke_receipt": smoke}

    evidence_sha, source_sha = production._validate_execution_against_verification(
        evidence=evidence,
        verification=verification,
    )
    assert evidence_sha == evidence["report_sha256_without_self_field"]
    assert source_sha == "a" * 64

    drifted = json.loads(json.dumps(evidence))
    drifted["source"]["source_sha256"] = "b" * 64
    drifted.pop("report_sha256_without_self_field")
    drifted["report_sha256_without_self_field"] = _canonical_sha(drifted)
    with pytest.raises(
        production.AutonomousProductionWeaverExtensionError,
        match="execution evidence drifted after independent verification",
    ):
        production._validate_execution_against_verification(
            evidence=drifted,
            verification=verification,
        )


def test_wrong_article_identity_fails_before_claim_admission() -> None:
    graph = _reference_graph()
    manifest = _manifest(graph)
    qualification = policy.authenticate_weaver_2021_full_text_policy(
        repository_root=ROOT,
        mission_path=MISSION,
        expected_mission_sha256=MISSION_SHA,
    )
    authorization = acquisition.build_derived_weaver_authorization(
        qualification=qualification,
        reference_graph=graph,
        predecessor_manifest=manifest,
    )

    def fake_fetcher(*args: object, **kwargs: object) -> FetchResult:
        del args, kwargs
        return FetchResult(
            body=json.dumps([{"documents": [{"passages": [{"text": "attacker paper"}]}]}]).encode(),
            final_url=policy.SOURCE_URL,
            status_code=200,
            content_type="application/json",
        )

    with pytest.raises(
        acquisition.Weaver2021FullTextAcquisitionError,
        match="title identity",
    ):
        acquisition.execute_derived_weaver_acquisition(
            authorization=authorization,
            fetcher=fake_fetcher,
        )
