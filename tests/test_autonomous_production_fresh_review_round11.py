from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_fresh_review_round11 as round11,
)


def test_canonical_json_equality_rejects_python_numeric_aliases() -> None:
    with pytest.raises(
        round11.AutonomousProductionFreshReviewRound11Error,
        match="type alias",
    ):
        round11._require_json_equal(
            {"authority": False, "count": 1},
            {"authority": 0, "count": 1.0},
            "type alias",
        )


def test_strict_integer_rejects_bool_and_float_aliases() -> None:
    for value in (True, 8.0):
        with pytest.raises(
            round11.AutonomousProductionFreshReviewRound11Error,
            match="JSON integer",
        ):
            round11._strict_int(value, expected=8, label="count")
    assert round11._strict_int(8, expected=8, label="count") == 8


def test_five_cycle_stop_replays_candidate_without_requiring_future_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    promotion = ("", "action", "impl", 6, "registry_binding")
    monkeypatch.setattr(round11._round6, "_PROMOTIONS", (promotion,))
    monkeypatch.setattr(round11._round6, "_INITIAL_VERIFIED_ACTIONS", ("base",))
    initial = {"capability_registry_sha256_without_self_field": "0" * 64}
    monkeypatch.setattr(
        round11._round6,
        "build_initial_capability_registry",
        lambda **_kwargs: copy.deepcopy(initial),
    )
    gap = {"requested_action_class": "action", "gap": "trusted"}
    spec = {
        "requested_action_class": "action",
        "capability_specification_sha256_without_self_field": "1" * 64,
    }
    predecessor = {
        "report_sha256_without_self_field": "p" * 64,
        "next_action": {"action_class": "action"},
    }
    monkeypatch.setattr(
        round11._round7,
        "_canonical_gap_and_specification",
        lambda **_kwargs: (copy.deepcopy(gap), copy.deepcopy(spec), copy.deepcopy(predecessor)),
    )
    monkeypatch.setattr(round11._round7, "_TRUSTED_PRIMITIVES", {"action": ("primitive",)})
    candidate = {"implementation_id": "impl", "candidate": "trusted"}
    resolution = {
        "resolution_status": "bounded_candidate_discovered",
        "candidate": copy.deepcopy(candidate),
        "unrestricted_discovery_performed": False,
        "arbitrary_code_generation_performed": False,
    }
    monkeypatch.setattr(
        round11,
        "resolve_or_discover_capability",
        lambda **_kwargs: copy.deepcopy(resolution),
    )
    artifacts: dict[str, dict[str, Any]] = {
        "capability-registry-initial.json": initial,
        "capability-gap.json": gap,
        "capability-specification.json": spec,
        "capability-resolution.json": resolution,
        "capability-candidate.json": candidate,
    }
    monkeypatch.setattr(
        round11._merge_gate,
        "_load",
        lambda _root, name: copy.deepcopy(artifacts[name]),
    )
    monkeypatch.setattr(round11._round10, "_RESOLUTION_ARTIFACTS", ("capability-resolution.json",))
    manifest = {"cycles": [{}, {}, {}, {}, {}]}

    assert round11._strict_replay_promotions(tmp_path, manifest) == {}


def test_six_cycle_stop_replays_post_promotion_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    promotion = ("", "action", "impl", 6, "registry_binding")
    monkeypatch.setattr(round11._round6, "_PROMOTIONS", (promotion,))
    monkeypatch.setattr(round11._round6, "_INITIAL_VERIFIED_ACTIONS", ("base",))
    initial = {"capability_registry_sha256_without_self_field": "0" * 64}
    monkeypatch.setattr(
        round11._round6,
        "build_initial_capability_registry",
        lambda **_kwargs: copy.deepcopy(initial),
    )
    gap = {"requested_action_class": "action", "gap": "trusted"}
    spec = {
        "requested_action_class": "action",
        "capability_specification_sha256_without_self_field": "1" * 64,
    }
    predecessor = {
        "report_sha256_without_self_field": "p" * 64,
        "next_action": {"action_class": "action"},
    }
    candidate = {"implementation_id": "impl", "candidate": "trusted"}
    discovery_resolution = {
        "resolution_status": "bounded_candidate_discovered",
        "candidate": copy.deepcopy(candidate),
        "unrestricted_discovery_performed": False,
        "arbitrary_code_generation_performed": False,
    }
    verification = {
        "capability_verification_sha256_without_self_field": "v" * 64,
        "promotion_eligible": True,
    }
    successor = {"capability_registry_sha256_without_self_field": "2" * 64}
    expected_post_resolution = {
        "resolution_status": "capability_already_available",
        "candidate": None,
    }
    forged_post_resolution = {
        "resolution_status": "no_bounded_candidate_available",
        "candidate": None,
    }

    monkeypatch.setattr(
        round11._round7,
        "_canonical_gap_and_specification",
        lambda **_kwargs: (
            copy.deepcopy(gap),
            copy.deepcopy(spec),
            copy.deepcopy(predecessor),
        ),
    )
    monkeypatch.setattr(round11._round7, "_TRUSTED_PRIMITIVES", {"action": ("primitive",)})
    monkeypatch.setattr(
        round11._round7,
        "_replay_trusted_candidate_and_verification",
        lambda **_kwargs: (copy.deepcopy(candidate), copy.deepcopy(verification)),
    )
    monkeypatch.setattr(
        round11,
        "promote_verified_capability",
        lambda **_kwargs: copy.deepcopy(successor),
    )

    def resolver(**kwargs: Any) -> dict[str, Any]:
        if kwargs["registry"] == initial:
            return copy.deepcopy(discovery_resolution)
        return copy.deepcopy(expected_post_resolution)

    monkeypatch.setattr(round11, "resolve_or_discover_capability", resolver)
    artifacts: dict[str, dict[str, Any]] = {
        "capability-registry-initial.json": initial,
        "capability-gap.json": gap,
        "capability-specification.json": spec,
        "capability-resolution.json": discovery_resolution,
        "capability-candidate.json": candidate,
        "capability-verification.json": verification,
        "capability-registry-promoted.json": successor,
        "capability-post-promotion-resolution.json": forged_post_resolution,
    }
    monkeypatch.setattr(
        round11._merge_gate,
        "_load",
        lambda _root, name: copy.deepcopy(artifacts[name]),
    )
    monkeypatch.setattr(
        round11._round10,
        "_RESOLUTION_ARTIFACTS",
        ("capability-resolution.json",),
    )
    manifest = {
        "cycles": [{}, {}, {}, {}, {}, {}],
        "registry_binding": "2" * 64,
    }

    with pytest.raises(
        round11.AutonomousProductionFreshReviewRound11Error,
        match="post-promotion resolution",
    ):
        round11._strict_replay_promotions(tmp_path, manifest)


def _cycle6_report() -> dict[str, Any]:
    sources = [
        {
            "request_index": index,
            "row_level_measurement_authority": False,
            "scientific_status_changed": False,
            "source_bytes_persisted": True,
        }
        for index in range(1, 9)
    ]
    reacquired = {
        "report_sha256_without_self_field": "r" * 64,
        "network_requests_performed": 8,
        "network_request_budget": 8,
        "retained_source_bytes_count": 8,
        "source_count": 8,
        "paper_claims_promoted_to_row_level_authority": False,
        "scientific_status_changed": False,
        "sources": sources,
    }
    return {"reacquired_source_evidence": reacquired}


def test_cycle6_source_row_authority_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bridge = _cycle6_report()
    bridge["reacquired_source_evidence"]["sources"][0][
        "row_level_measurement_authority"
    ] = True
    monkeypatch.setattr(
        round11._merge_gate,
        "_load",
        lambda _root, name: copy.deepcopy(bridge)
        if name == "calibration-protocol-bridge-capability-result.json"
        else {},
    )
    monkeypatch.setattr(
        round11._merge_gate,
        "_verify_self_hash",
        lambda *_args, **_kwargs: "r" * 64,
    )
    monkeypatch.setattr(
        round11._round9,
        "_validate_multisource_report_boundaries",
        lambda _report: None,
    )
    manifest = {"cycles": [{}, {}, {}, {}, {}, {}]}

    with pytest.raises(
        round11.AutonomousProductionFreshReviewRound11Error,
        match="widened scientific/provenance authority",
    ):
        round11._verify_cycle6_execution_boundary(tmp_path, manifest)


def test_cycle6_execution_counts_are_type_sensitive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bridge = _cycle6_report()
    bridge["reacquired_source_evidence"]["network_requests_performed"] = 8.0
    monkeypatch.setattr(
        round11._merge_gate,
        "_load",
        lambda _root, _name: copy.deepcopy(bridge),
    )
    monkeypatch.setattr(
        round11._merge_gate,
        "_verify_self_hash",
        lambda *_args, **_kwargs: "r" * 64,
    )
    monkeypatch.setattr(
        round11._round9,
        "_validate_multisource_report_boundaries",
        lambda _report: None,
    )
    manifest = {"cycles": [{}, {}, {}, {}, {}, {}]}

    with pytest.raises(
        round11.AutonomousProductionFreshReviewRound11Error,
        match="JSON integer",
    ):
        round11._verify_cycle6_execution_boundary(tmp_path, manifest)


def test_cycle1_missing_network_authorization_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    output = repository / "outputs" / "autonomous-in625-production"
    output.mkdir(parents=True)
    config_path = repository / round11._SOURCE_CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "zenodo": {
                    "readme_file": "README - Dataset description.txt",
                    "archive_file": "Dataset.zip",
                    "files": {
                        "Dataset.zip": {"verified_sha256": "d" * 64},
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    registry_path = repository / round11._ACTION_REGISTRY_PATH
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text("{}\n", encoding="utf-8")
    (output / "record.json").write_bytes(b"metadata")
    (output / "README - Dataset description.txt").write_bytes(b"readme")
    mission = repository / "mission.json"
    mission.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        round11._round7,
        "_trusted_mission_binding",
        lambda: (repository, mission, "0" * 64),
    )
    expected_authorization = {"authorization_sha256": "a" * 64}
    monkeypatch.setattr(
        round11,
        "build_in625_archive_network_authorization",
        lambda **_kwargs: copy.deepcopy(expected_authorization),
    )
    manifest = {
        "cycles": [
            {
                "network_authorization_sha256": "a" * 64,
            }
        ]
    }

    with pytest.raises(
        round11.AutonomousProductionFreshReviewRound11Error,
        match="network-authorization.json",
    ):
        round11._verify_cycle1_authority_artifacts(output, manifest)
