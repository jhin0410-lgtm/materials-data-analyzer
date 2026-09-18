from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_fresh_review_round10 as round10,
)


def _install_loader(
    monkeypatch: pytest.MonkeyPatch,
    artifacts: dict[str, dict[str, Any]],
) -> None:
    monkeypatch.setattr(
        round10._merge_gate,
        "_load",
        lambda _root, name: copy.deepcopy(artifacts[name]),
    )
    monkeypatch.setattr(
        round10._merge_gate,
        "_verify_self_hash",
        lambda value, field, **_kwargs: str(value[field]),
    )


def test_geometry_mapping_is_rebuilt_not_merely_self_hashed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trusted = tmp_path / "trusted"
    process = trusted / round10._TARGET_PROCESS_PATH
    response = trusted / round10._TARGET_RESPONSE_PATH
    process.parent.mkdir(parents=True, exist_ok=True)
    process.write_bytes(b"trusted-process")
    response.write_bytes(b"trusted-response")
    nist = {"report_sha256_without_self_field": "n" * 64}
    multisource = {"report_sha256_without_self_field": "m" * 64}
    expected = {
        "report_sha256_without_self_field": "g" * 64,
        "target_binding": {"process": "trusted"},
    }
    persisted = copy.deepcopy(expected)
    persisted["target_binding"] = {"process": "forged"}
    artifacts = {
        "nist-scientific-intake.json": nist,
        "multisource-source-acquisition.json": multisource,
        "geometry-condition-mapping-assessment.json": persisted,
    }
    _install_loader(monkeypatch, artifacts)
    monkeypatch.setattr(
        round10._source_replay, "verify_source_replay_boundaries", lambda _root: None
    )
    monkeypatch.setattr(
        round10, "verify_multisource_acquisition_against_reviewed_witness", lambda _report: None
    )
    monkeypatch.setattr(
        round10._merge_gate, "_trusted_repository_root", lambda: trusted
    )
    monkeypatch.setattr(
        round10,
        "build_geometry_condition_mapping_assessment",
        lambda **_kwargs: copy.deepcopy(expected),
    )
    manifest = {
        "cycles": [{}, {}, {}, {
            "mapping_assessment_sha256": "g" * 64,
            "source_acquisition_report_sha256": "m" * 64,
        }],
        "geometry_condition_mapping_assessment_sha256": "g" * 64,
        "multisource_condition_source_acquisition_sha256": "m" * 64,
    }

    with pytest.raises(
        round10.AutonomousProductionFreshReviewRound10Error,
        match="geometry-condition mapping drifted",
    ):
        round10._verify_geometry_mapping(tmp_path, manifest)


def test_persisted_resolver_output_must_equal_finite_factory_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    promotion = ("", "action", "impl", 6, "registry_binding")
    monkeypatch.setattr(round10._round6, "_PROMOTIONS", (promotion,))
    monkeypatch.setattr(round10._round6, "_INITIAL_VERIFIED_ACTIONS", ("base",))
    initial = {"capability_registry_sha256_without_self_field": "0" * 64}
    monkeypatch.setattr(
        round10._round6,
        "build_initial_capability_registry",
        lambda **_kwargs: copy.deepcopy(initial),
    )
    specification = {
        "requested_action_class": "action",
        "capability_specification_sha256_without_self_field": "1" * 64,
    }
    predecessor = {"next_action": {"action_class": "action"}}
    monkeypatch.setattr(
        round10._round7,
        "_canonical_gap_and_specification",
        lambda **_kwargs: ({}, copy.deepcopy(specification), copy.deepcopy(predecessor)),
    )
    monkeypatch.setattr(round10._round7, "_TRUSTED_PRIMITIVES", {"action": ("p",)})
    candidate = {"implementation_id": "impl", "candidate": "trusted"}
    expected_resolution = {
        "resolution_status": "bounded_candidate_discovered",
        "candidate": copy.deepcopy(candidate),
        "unrestricted_discovery_performed": False,
        "arbitrary_code_generation_performed": False,
    }
    monkeypatch.setattr(
        round10,
        "resolve_or_discover_capability",
        lambda **_kwargs: copy.deepcopy(expected_resolution),
    )
    forged_resolution = copy.deepcopy(expected_resolution)
    forged_resolution["unrestricted_discovery_performed"] = True
    verification = {"verified": True}
    successor = {"capability_registry_sha256_without_self_field": "2" * 64}
    artifacts = {
        "capability-registry-initial.json": initial,
        "capability-resolution.json": forged_resolution,
        "capability-candidate.json": candidate,
        "capability-verification.json": verification,
        "capability-registry-promoted.json": successor,
    }
    _install_loader(monkeypatch, artifacts)
    monkeypatch.setattr(
        round10._round7,
        "_replay_trusted_candidate_and_verification",
        lambda **_kwargs: (copy.deepcopy(candidate), copy.deepcopy(verification)),
    )
    monkeypatch.setattr(
        round10,
        "promote_verified_capability",
        lambda **_kwargs: copy.deepcopy(successor),
    )
    manifest = {"cycles": [{}, {}, {}, {}, {}], "registry_binding": "2" * 64}

    with pytest.raises(
        round10.AutonomousProductionFreshReviewRound10Error,
        match="persisted resolver output drifted",
    ):
        round10._replay_promotions_and_resolutions(tmp_path, manifest)


def _derived_artifacts() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    qualification = {"policy_sha256": "q" * 64}
    authorization = {
        "authorization_sha256": "a" * 64,
        "policy_sha256": "q" * 64,
        "mission_sha256": "m" * 64,
    }
    acquisition = {
        "authorization_sha256": "a" * 64,
        "report_sha256_without_self_field": "x" * 64,
    }
    assessment = {
        "report_sha256_without_self_field": "s" * 64,
        "new_verified_information": True,
        "evidence_scope": {"trusted": True},
        "next_action": {"action_class": "reference-chain"},
    }
    artifacts = {
        "nist-ammt-candidate-acquisition-policy-qualification.json": qualification,
        "nist-ammt-derived-candidate-authorization.json": authorization,
        "nist-ammt-calibration-candidate-acquisition.json": acquisition,
        "nist-ammt-calibration-candidate-bridge-assessment.json": assessment,
    }
    manifest = {
        "cycles": [{}, {}, {}, {}, {}, {}, {}, {}, {}, {
            "output_next_action_class": "reference-chain",
            "new_verified_information": True,
        }],
        "derived_candidate_acquisition_sha256": "x" * 64,
        "calibration_candidate_bridge_assessment_sha256": "s" * 64,
    }
    return artifacts, manifest


def _install_derived_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    artifacts: dict[str, dict[str, Any]],
) -> None:
    _install_loader(monkeypatch, artifacts)
    context = {
        "discovery_report": {"report_sha256_without_self_field": "d" * 64},
        "predecessor_manifest": {"manifest_sha256": "p" * 64},
    }
    monkeypatch.setattr(
        round10, "_trusted_step3_context", lambda **_kwargs: copy.deepcopy(context)
    )
    monkeypatch.setattr(
        round10._round7,
        "_trusted_mission_binding",
        lambda: (tmp_path, tmp_path / "mission.json", "m" * 64),
    )
    monkeypatch.setattr(
        round10,
        "authenticate_nist_ammt_candidate_acquisition_policy",
        lambda **_kwargs: {"policy_sha256": "q" * 64},
    )
    monkeypatch.setattr(
        round10._candidate_acquisition,
        "build_derived_candidate_authorization",
        lambda **_kwargs: {
            "authorization_sha256": "a" * 64,
            "policy_sha256": "q" * 64,
            "mission_sha256": "m" * 64,
        },
    )
    monkeypatch.setattr(
        round10._trusted_binding,
        "verify_trusted_replay_artifact_bindings",
        lambda _root: None,
    )
    monkeypatch.setattr(
        round10._bridge_assessment,
        "build_calibration_candidate_bridge_assessment",
        lambda **_kwargs: {
            "report_sha256_without_self_field": "s" * 64,
            "new_verified_information": True,
            "evidence_scope": {"trusted": True},
            "next_action": {"action_class": "reference-chain"},
        },
    )


def test_derived_authorization_is_rebuilt_from_trusted_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts, manifest = _derived_artifacts()
    artifacts["nist-ammt-derived-candidate-authorization.json"]["policy_sha256"] = "f" * 64
    _install_derived_replay(tmp_path, monkeypatch, artifacts)

    with pytest.raises(
        round10.AutonomousProductionFreshReviewRound10Error,
        match="authorization drifted from trusted replay",
    ):
        round10._verify_derived_authorization_and_bridge_assessment(
            tmp_path, manifest, {3: {}}
        )


def test_bridge_assessment_is_rebuilt_from_bound_acquisition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts, manifest = _derived_artifacts()
    artifacts["nist-ammt-calibration-candidate-bridge-assessment.json"][
        "evidence_scope"
    ] = {"trusted": False, "forged": True}
    _install_derived_replay(tmp_path, monkeypatch, artifacts)

    with pytest.raises(
        round10.AutonomousProductionFreshReviewRound10Error,
        match="bridge assessment drifted",
    ):
        round10._verify_derived_authorization_and_bridge_assessment(
            tmp_path, manifest, {3: {}}
        )
