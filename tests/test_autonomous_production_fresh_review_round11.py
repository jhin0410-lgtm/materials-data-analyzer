from __future__ import annotations

import copy
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
