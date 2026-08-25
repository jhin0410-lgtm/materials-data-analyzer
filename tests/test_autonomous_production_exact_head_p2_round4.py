from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_exact_head_p2_round4 as round4,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _hashed(value: dict[str, Any], field: str) -> dict[str, Any]:
    result = dict(value)
    result[field] = _canonical_sha(result)
    return result


def _cycles() -> list[dict[str, Any]]:
    return [{"cycle_index": index} for index in range(1, 13)]


@pytest.mark.parametrize(
    "field",
    [
        "exact_row_identity_established",
        "exact_experiment_identity_established",
        "automatic_unrestricted_search_authorized",
        "caller_authored_arbitrary_urls_authorized",
    ],
)
def test_rehashed_late_report_cannot_promote_round4_authority(
    field: str,
) -> None:
    report = _hashed(
        {
            "schema_version": "test",
            field: True,
        },
        "report_sha256_without_self_field",
    )
    round4._merge_gate._verify_self_hash(
        report,
        "report_sha256_without_self_field",
        label="round4 adversarial late report",
    )
    with pytest.raises(
        round4.AutonomousProductionExactHeadRound4Error,
        match="promoted fail-closed authority",
    ):
        round4._walk_round4_authority(report, label="round4 adversarial late report")


def _terminal_fixture(root: Path) -> None:
    requested = "weaver_2021_spot_size_full_text_derived_acquisition"
    gap = _hashed(
        {
            "requested_action_class": requested,
            "scientific_status_changed": False,
        },
        "capability_gap_sha256_without_self_field",
    )
    specification = _hashed(
        {
            "requested_action_class": requested,
            "capability_gap_sha256": gap["capability_gap_sha256_without_self_field"],
        },
        "capability_specification_sha256_without_self_field",
    )
    registry = _hashed(
        {
            "records": [],
            "arbitrary_code_execution_allowed": False,
            "candidate_self_promotion_allowed": False,
            "network_authority_synthesis_allowed": False,
        },
        "capability_registry_sha256_without_self_field",
    )
    resolution = {
        "action_class": requested,
        "arbitrary_code_generation_performed": False,
        "candidate": None,
        "factory_catalogue_size": 4,
        "implementation_id": None,
        "policy_version": "1.3",
        "registry_sha256": registry["capability_registry_sha256_without_self_field"],
        "resolution_status": "no_bounded_candidate_available",
        "schema_version": "1.3",
        "unrestricted_discovery_performed": False,
    }
    _write_json(root / "capability-gap-5.json", gap)
    _write_json(root / "capability-specification-5.json", specification)
    _write_json(root / "capability-registry-promoted-4.json", registry)
    _write_json(root / "capability-resolution-5.json", resolution)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("candidate", {"injected": True}),
        ("action_class", "external_evidence_search"),
        ("unrestricted_discovery_performed", True),
        ("arbitrary_code_generation_performed", True),
    ],
)
def test_terminal_capability_resolution_cannot_be_injected(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    _terminal_fixture(tmp_path)
    round4._verify_terminal_capability_resolution(tmp_path, _cycles())
    path = tmp_path / "capability-resolution-5.json"
    resolution = json.loads(path.read_text(encoding="utf-8"))
    resolution[field] = value
    _write_json(path, resolution)
    with pytest.raises(
        round4.AutonomousProductionExactHeadRound4Error,
        match="terminal capability resolution drifted",
    ):
        round4._verify_terminal_capability_resolution(tmp_path, _cycles())


def _naderi_policy() -> dict[str, Any]:
    claim_ids = list(round4._NADERI_MATCH_RECEIPTS)
    claims = []
    for index, claim_id in enumerate(claim_ids, start=1):
        claims.append(
            {
                "claim_id": claim_id,
                "match_mode": "ordered_same_page_fragments",
                "max_span_utf8_bytes": 4096,
                "required_fragments": [f"fragment-{index}", f"fragment-{index}-b"],
                "scope": f"scope-{index}",
            }
        )
    return {
        "policy_id": "nist-mds2-2923-reference-chain-naderi-evidence-v1",
        "action_class": "mds2_2923_experiment_identity_reference_chain_assessment",
        "source": {
            "source_id": "naderi-2022-scaling-fidelity-reference-chain",
            "url": "https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=935135",
            "doi": "10.1007/s40192-022-00289-w",
            "expected_sha256": "c35a62f9f3b9346af2e0fa99de46710b3017c915e3c792dbf01c83b920a53e81",
            "expected_size_bytes": 4597480,
        },
        "claims": claims,
    }


def _naderi_report(policy: dict[str, Any], policy_sha: str) -> dict[str, Any]:
    claims = []
    for claim in policy["claims"]:
        claim_id = claim["claim_id"]
        receipt = round4._NADERI_MATCH_RECEIPTS[claim_id]
        claims.append(
            {
                "allowed_text_extraction_modes": ["plain", "layout"],
                "claim_id": claim_id,
                "match_count": 1,
                "match_mode": claim["match_mode"],
                "matched": True,
                "matches": receipt["matches"],
                "max_span_utf8_bytes": claim["max_span_utf8_bytes"],
                "required_fragment_count": len(claim["required_fragments"]),
                "required_fragments_sha256": round4._canonical_sha256(
                    claim["required_fragments"]
                ),
                "scope": claim["scope"],
                "selected_text_extraction_mode": receipt[
                    "selected_text_extraction_mode"
                ],
                "source_text_persisted": False,
            }
        )
    source_policy = policy["source"]
    report = {
        "action_class": policy["action_class"],
        "policy_id": policy["policy_id"],
        "policy_sha256": policy_sha,
        "network_requests_performed": 1,
        "unrestricted_search_performed": False,
        "arbitrary_url_fetch_performed": False,
        "caller_authored_url_used": False,
        "source": {
            "source_id": source_policy["source_id"],
            "requested_url": source_policy["url"],
            "final_url": source_policy["url"],
            "doi": source_policy["doi"],
            "source_sha256": source_policy["expected_sha256"],
            "source_size_bytes": source_policy["expected_size_bytes"],
            "source_bytes_persisted": False,
            "source_text_persisted": False,
            "row_level_measurement_authority": False,
        },
        "claims": claims,
    }
    return _hashed(report, "report_sha256_without_self_field")


def test_rehashed_naderi_report_cannot_substitute_source_or_claim_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _naderi_policy()
    policy_sha = _canonical_sha(policy)
    monkeypatch.setattr(round4, "_load_naderi_policy", lambda: (policy, policy_sha))
    report = _naderi_report(policy, policy_sha)
    _write_json(tmp_path / "nist-mds2-2923-reference-chain-evidence.json", report)
    round4._verify_naderi_source_provenance(tmp_path, _cycles())

    report["source"]["source_sha256"] = "0" * 64
    report.pop("report_sha256_without_self_field")
    report["report_sha256_without_self_field"] = _canonical_sha(report)
    _write_json(tmp_path / "nist-mds2-2923-reference-chain-evidence.json", report)
    with pytest.raises(
        round4.AutonomousProductionExactHeadRound4Error,
        match="source provenance drifted",
    ):
        round4._verify_naderi_source_provenance(tmp_path, _cycles())

    report = _naderi_report(policy, policy_sha)
    report["claims"][0]["matches"][0]["matched_span_sha256"] = "f" * 64
    report.pop("report_sha256_without_self_field")
    report["report_sha256_without_self_field"] = _canonical_sha(report)
    _write_json(tmp_path / "nist-mds2-2923-reference-chain-evidence.json", report)
    with pytest.raises(
        round4.AutonomousProductionExactHeadRound4Error,
        match="canonical claim receipt drifted",
    ):
        round4._verify_naderi_source_provenance(tmp_path, _cycles())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("response_compatibility_established", True),
        ("protocol_compatibility_established", True),
        ("source_globally_unusable_claimed", True),
    ],
)
def test_rehashed_comparability_decision_cannot_promote_missing_gate_fields(
    tmp_path: Path,
    field: str,
    value: bool,
) -> None:
    assessment = _hashed(
        {"gate_decision": dict(round4._COMPLETE_COMPARABILITY_GATE)},
        "assessment_sha256",
    )
    _write_json(tmp_path / "physical-comparability-assessment.json", assessment)
    round4._verify_complete_comparability_gate(tmp_path)

    assessment["gate_decision"][field] = value
    assessment.pop("assessment_sha256")
    assessment["assessment_sha256"] = _canonical_sha(assessment)
    _write_json(tmp_path / "physical-comparability-assessment.json", assessment)
    with pytest.raises(
        round4.AutonomousProductionExactHeadRound4Error,
        match="physical comparability gate decision drifted",
    ):
        round4._verify_complete_comparability_gate(tmp_path)


def test_round4_is_wired_into_public_verifier_and_live_workflow() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    verifier = (
        repository_root
        / "src/materials_data_analyzer/research_loop/autonomous_production_live_verifier.py"
    ).read_text(encoding="utf-8")
    workflow = (
        repository_root / ".github/workflows/autonomous-production-live.yml"
    ).read_text(encoding="utf-8")

    assert "verify_exact_head_round4_boundaries" in verifier
    assert "tests/test_autonomous_production_exact_head_p2_round4.py" in workflow
