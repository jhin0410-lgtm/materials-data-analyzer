from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from materials_data_analyzer.research_loop import in625_blind_challenge_history as module
from materials_data_analyzer.research_loop.evidence_packet import canonical_sha256


def _inquiry() -> dict:
    value = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "inquiry_type": "in625_retrospective_model_discrepancy",
        "plan": {
            "selected_next_action": {
                "action_id": "inquiry:test:blind-submission-provenance:search-evidence",
                "action_class": "external_evidence_search",
                "execution_mode": "requires_explicit_authorization",
                "required_evidence": [
                    "authoritative archived source/provenance evidence for the original "
                    "2018 AMB2018-02-MP blind challenge submissions"
                ],
                "automatic_execution_authorized": False,
            }
        },
        "authority_boundary": {
            "network_execution_authorized": False,
            "physical_experiment_execution_authorized": False,
            "published_computational_result_promoted_to_empirical": False,
            "hypothesis_truth_established": False,
            "engineering_readiness_established": False,
            "scientific_status_promoted": False,
        },
    }
    value["inquiry_sha256"] = canonical_sha256(value)
    return value


_SOURCE_HTML = {
    "https://www.nist.gov/ambench/am-bench-2018-challenge-submissions-and-awards": b"""
        <html><body>Melt pool geometry CHAL-AMB2018-02-MP 10</body></html>
    """,
    "https://www.nist.gov/publications/outcomes-and-conclusions-2018-am-bench-measurements-challenge-problems-modeling": b"""
        <html><body>46 blind modeling simulations were submitted by the international AM community.</body></html>
    """,
    "https://www.nist.gov/ambench/new-am-bench-focus-higher-technology-readiness-level-applications": b"""
        <html><body>For AM Bench 2018, none of the 10 research groups that submitted
        modeling predictions for the width, depth, and length of laser melt pools on bare
        metal plates came close to predicting the measured values.</body></html>
    """,
    "https://www.nist.gov/ambench/challenges-and-descriptions": b"""
        <html><body>The true laser power levels for AMMT were A) 137.9 W, 400 mm/s,
        B) 179.2 W, 800 mm/s, C) 179.2 W, 1200 mm/s.
        Upon further investigation the true laser spot sizes were different than intended.
        The AMMT laser spot D4sigma diameter was 170 micrometers and the
        CBM laser spot D4sigma diameter was 100 micrometers.</body></html>
    """,
}


def _fake_fetch(url: str, **_kwargs: object) -> SimpleNamespace:
    return SimpleNamespace(
        body=_SOURCE_HTML[url],
        final_url=url,
        status_code=200,
        content_type="text/html",
    )


def _request_and_authorization() -> tuple[dict, dict]:
    inquiry = _inquiry()
    request = module.build_in625_blind_history_request(
        inquiry,
        trusted_inquiry_sha256=canonical_sha256(inquiry),
    )
    authorization = module.authorize_in625_blind_history_request(
        request,
        trusted_request_sha256=canonical_sha256(request),
    )
    return request, authorization


def test_fixed_nist_history_action_executes_and_replays(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(module, "fetch_exact_source", _fake_fetch)
    request, authorization = _request_and_authorization()
    source_root = tmp_path / "sources"

    result = module.execute_in625_blind_history_acquisition(
        request,
        authorization_receipt=authorization,
        trusted_authorization_sha256=canonical_sha256(authorization),
        source_output_dir=source_root,
    )
    verified = module.verify_in625_blind_history_acquisition(
        result,
        request=request,
        authorization_receipt=authorization,
        trusted_authorization_sha256=canonical_sha256(authorization),
        source_output_dir=source_root,
    )

    facts = verified["verified_historical_context"]
    assert verified["source_count"] == 4
    assert facts["amb2018_total_blind_modeling_simulations"] == 46
    assert facts["amb2018_02_melt_pool_geometry_submission_count"] == 10
    assert (
        facts[
            "nist_retrospective_statement_none_of_10_mp_groups_came_close_to_measurements"
        ]
        is True
    )
    assert facts["current_corrected_ammt_process_conditions"]["B"]["actual_power_w"] == 179.2
    assert facts["current_corrected_spot_d4sigma_um"] == {"AMMT": 170.0, "CBM": 100.0}
    assert facts["individual_blind_submission_numeric_predictions_acquired"] is False
    assert verified["bounded_interpretation"][
        "specific_cause_of_retrospective_improvement_established"
    ] is False
    assert verified["authority_boundary"]["scientific_status_promoted"] is False


def test_selected_non_search_action_cannot_compile_history_request() -> None:
    inquiry = _inquiry()
    inquiry["plan"]["selected_next_action"]["action_class"] = "sensitivity_analysis"
    inquiry.pop("inquiry_sha256")
    inquiry["inquiry_sha256"] = canonical_sha256(inquiry)

    with pytest.raises(module.In625BlindHistoryError, match="external_evidence_search"):
        module.build_in625_blind_history_request(
            inquiry,
            trusted_inquiry_sha256=canonical_sha256(inquiry),
        )


def test_rehashed_request_cannot_replace_fixed_nist_source() -> None:
    request, _authorization = _request_and_authorization()
    forged = copy.deepcopy(request)
    forged["network_contract"]["sources"][0]["url"] = "https://www.nist.gov/forged"
    forged.pop("request_sha256")
    forged["request_sha256"] = canonical_sha256(forged)

    with pytest.raises(module.In625BlindHistoryError, match="network contract drifted"):
        module.authorize_in625_blind_history_request(
            forged,
            trusted_request_sha256=canonical_sha256(forged),
        )


def test_rehashed_authorization_cannot_promote_scientific_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(module, "fetch_exact_source", _fake_fetch)
    request, authorization = _request_and_authorization()
    forged = copy.deepcopy(authorization)
    forged["scientific_status_promotion_authorized"] = True
    forged.pop("authorization_sha256")
    forged["authorization_sha256"] = canonical_sha256(forged)

    with pytest.raises(module.In625BlindHistoryError, match="exact finite request"):
        module.execute_in625_blind_history_acquisition(
            request,
            authorization_receipt=forged,
            trusted_authorization_sha256=canonical_sha256(forged),
            source_output_dir=tmp_path / "sources",
        )


def test_retained_source_mutation_fails_independent_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(module, "fetch_exact_source", _fake_fetch)
    request, authorization = _request_and_authorization()
    source_root = tmp_path / "sources"
    result = module.execute_in625_blind_history_acquisition(
        request,
        authorization_receipt=authorization,
        trusted_authorization_sha256=canonical_sha256(authorization),
        source_output_dir=source_root,
    )
    target = source_root / "01_submissions_awards.html"
    target.write_bytes(b"<html>mutated</html>")

    with pytest.raises(module.In625BlindHistoryError, match="claim anchor missing"):
        module.verify_in625_blind_history_acquisition(
            result,
            request=request,
            authorization_receipt=authorization,
            trusted_authorization_sha256=canonical_sha256(authorization),
            source_output_dir=source_root,
        )


def test_external_inquiry_root_rejects_rehashed_selected_action() -> None:
    inquiry = _inquiry()
    trusted = canonical_sha256(inquiry)
    forged = copy.deepcopy(inquiry)
    forged["plan"]["selected_next_action"]["required_evidence"] = ["different source"]
    forged.pop("inquiry_sha256")
    forged["inquiry_sha256"] = canonical_sha256(forged)

    with pytest.raises(module.In625BlindHistoryError, match="external trust-root"):
        module.build_in625_blind_history_request(
            forged,
            trusted_inquiry_sha256=trusted,
        )
