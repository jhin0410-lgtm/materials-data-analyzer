from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_exact_head_p2_round6 as round6,
)
from materials_data_analyzer.research_loop import (
    autonomous_production_exact_head_p2_round7 as round7,
)
from materials_data_analyzer.research_loop import (
    capability_expansion,
    capability_registry,
    capability_resolver,
    capability_smoke_replay_evidence,
)
from materials_data_analyzer.research_loop.in625_geometry_condition_source_acquisition import (
    FetchResult,
)


ROOT = Path(__file__).resolve().parents[1]
MISSION = ROOT / "configs/research/autonomous_in625_production_mission.v1.json"
MISSION_SHA = hashlib.sha256(MISSION.read_bytes()).hexdigest()


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


def _rehash(value: dict[str, Any], field: str) -> None:
    value.pop(field, None)
    value[field] = _canonical_sha(value)


def _write_json(root: Path, name: str, value: object) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _report(*, action_class: str | None = None, step: int | None = None) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": "trusted-replay-test-1.0",
        "scientific_status_changed": False,
    }
    if action_class is not None:
        report["next_action"] = {
            "action_class": action_class,
            "objective": f"Execute canonical trusted capability promotion {step}.",
            "eligible_evidence_lanes": ["paper_and_supplementary_material"],
            "automatic_acquisition_authorized": False,
            "caller_authored_arbitrary_urls_authorized": False,
        }
    report["report_sha256_without_self_field"] = _canonical_sha(report)
    return report


def _one_fetch_record() -> list[dict[str, Any]]:
    def delegate(
        url: str,
        *,
        allowed_hosts: tuple[str, ...],
        max_bytes: int,
        timeout_seconds: int,
    ) -> FetchResult:
        del allowed_hosts, max_bytes, timeout_seconds
        return FetchResult(
            body=b"retained deterministic verifier smoke bytes",
            final_url=url,
            status_code=200,
            content_type="application/octet-stream",
        )

    recorder = capability_smoke_replay_evidence.RecordingFetcher(delegate)
    recorder(
        "https://retained.test/exact-smoke",
        allowed_hosts=("retained.test",),
        max_bytes=4096,
        timeout_seconds=11,
    )
    return recorder.records


def _verification(
    *,
    specification: Mapping[str, Any],
    candidate: Mapping[str, Any],
    primitives: tuple[str, ...] | list[str] | Mapping[Any, Any] | Any,
    replay_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    requirements = specification.get("verification_requirements")
    assert isinstance(requirements, list)
    core = capability_registry.build_capability_verification_receipt(
        capability_specification=specification,
        candidate=candidate,
        available_verified_primitives=list(primitives),
        verification_results={str(name): True for name in requirements},
    )
    unsigned = dict(core)
    unsigned.pop("capability_verification_sha256_without_self_field")
    unsigned.update(
        {
            "verifier_schema_version": "trusted-replay-test-1.0",
            "verifier_policy_version": "trusted-replay-test-1.0",
            "implementation_sha256": "d" * 64,
            "verifier_sha256": "e" * 64,
            "real_source_smoke_receipt_sha256": "f" * 64,
            "real_source_smoke_receipt": {
                "smoke_status": "test_original_live_smoke_passed",
                "network_requests_performed": 1,
                "scientific_status_changed": False,
            },
            "real_source_smoke_replay_evidence_sha256": replay_evidence[
                "smoke_replay_evidence_sha256_without_self_field"
            ],
            "real_source_smoke_replay_evidence": dict(replay_evidence),
        }
    )
    unsigned["capability_verification_sha256_without_self_field"] = _canonical_sha(unsigned)
    return unsigned


def _context_for_step(
    *,
    root: Path,
    step: int,
    predecessor: Mapping[str, Any],
    cycles: list[dict[str, Any]],
) -> Mapping[str, Any] | None:
    if step in (1, 2):
        return None
    if step == 3:
        predecessor_manifest: dict[str, Any] = {
            "schema_version": "1.6-test",
            "cycles": copy.deepcopy(cycles[:8]),
            "nist_ammt_source_discovery_sha256": predecessor[
                "report_sha256_without_self_field"
            ],
            "generated_next_action_class": round6._PROMOTIONS[2][1],
            "third_capability_gap_emitted": True,
            "directly_comparable_mds2_rows": 0,
            "issue_76_exact_target_cells_satisfied": 0,
            "bridge_established": False,
            "scientific_status_changed": False,
        }
        predecessor_manifest["manifest_sha256"] = _canonical_sha(predecessor_manifest)
        return {
            "discovery_report": copy.deepcopy(predecessor),
            "predecessor_manifest": predecessor_manifest,
        }

    metadata = b'{"@id":"test-nerdm-metadata"}\n'
    metadata_path = root / "nist-mds2-2923" / "nerdm-metadata.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_bytes(metadata)
    nist = _report()
    multisource = _report()
    discovery_report = _write_or_load_step3_predecessor(root)
    _write_json(root, "nist-scientific-intake.json", nist)
    _write_json(root, "multisource-source-acquisition.json", multisource)
    return {
        "nerdm_metadata_bytes": metadata,
        "nist_intake": nist,
        "multisource_evidence": multisource,
        "source_discovery_report": discovery_report,
        "calibration_candidate_assessment": copy.deepcopy(predecessor),
    }


def _write_or_load_step3_predecessor(root: Path) -> dict[str, Any]:
    path = root / "calibration-record-source-discovery.json"
    if path.is_file():
        value = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(value, dict)
        return value
    report = _report(action_class=round6._PROMOTIONS[2][1], step=3)
    _write_json(root, "calibration-record-source-discovery.json", report)
    return report


def _build_prefix(
    root: Path,
    *,
    through_step: int,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    registry = capability_registry.build_initial_capability_registry(
        verified_action_classes=round6._INITIAL_VERIFIED_ACTIONS,
    )
    _write_json(root, "capability-registry-initial.json", registry)
    final_cycle_index = round6._PROMOTIONS[through_step - 1][3]
    cycles: list[dict[str, Any]] = [
        {"cycle_index": index} for index in range(1, final_cycle_index + 1)
    ]
    manifest: dict[str, Any] = {"cycles": cycles}
    records: list[dict[str, Any]] = []
    expected_verifications: dict[str, dict[str, Any]] = {}

    for step, promotion in enumerate(round6._PROMOTIONS[:through_step], start=1):
        suffix, action_class, _implementation_id, cycle_index, manifest_field = promotion
        predecessor = _report(action_class=action_class, step=step)
        _write_json(root, round7._PREDECESSOR_REPORTS[step - 1], predecessor)
        gap = capability_expansion.build_capability_gap(
            requested_action=predecessor["next_action"],
            predecessor_report=predecessor,
            available_action_classes=round7._round5._verified_action_classes(registry),
        )
        specification = capability_expansion.build_capability_specification(gap)
        primitives = round7._TRUSTED_PRIMITIVES[action_class]
        resolution = capability_resolver.resolve_or_discover_capability(
            registry=registry,
            capability_specification=specification,
            available_verified_primitives=primitives,
        )
        candidate = copy.deepcopy(resolution["candidate"])
        assert isinstance(candidate, dict)

        context = _context_for_step(
            root=root,
            step=step,
            predecessor=predecessor,
            cycles=cycles,
        )
        replay_evidence = capability_smoke_replay_evidence.build_smoke_replay_evidence(
            action_class=action_class,
            capability_specification_sha256=specification[
                "capability_specification_sha256_without_self_field"
            ],
            capability_candidate_sha256=candidate[
                "capability_candidate_sha256_without_self_field"
            ],
            mission_sha256=MISSION_SHA,
            verification_context=context,
            fetch_records=_one_fetch_record(),
        )
        verification = _verification(
            specification=specification,
            candidate=candidate,
            primitives=primitives,
            replay_evidence=replay_evidence,
        )
        successor = capability_registry.promote_verified_capability(
            registry=registry,
            candidate=candidate,
            verification_receipt=verification,
        )
        _write_json(root, round6._name("capability-gap", suffix), gap)
        _write_json(root, round6._name("capability-specification", suffix), specification)
        _write_json(root, round6._name("capability-candidate", suffix), candidate)
        _write_json(root, round6._name("capability-verification", suffix), verification)
        _write_json(root, round6._name("capability-registry-promoted", suffix), successor)
        registry_sha = successor["capability_registry_sha256_without_self_field"]
        cycles[cycle_index - 1]["promoted_registry_sha256"] = registry_sha
        if manifest_field is not None:
            manifest[manifest_field] = registry_sha
        records.append(
            {
                "suffix": suffix,
                "specification": specification,
                "candidate": candidate,
                "verification": verification,
                "replay_evidence": replay_evidence,
                "context": context,
                "predecessor_registry": registry,
            }
        )
        expected_verifications[candidate["capability_candidate_sha256_without_self_field"]] = copy.deepcopy(
            verification
        )
        registry = successor

    manifest["cycles"] = cycles
    _write_json(root, "autonomous-production-manifest.json", manifest)
    return manifest, cycles, records, expected_verifications


def _install_authoritative_replay(
    monkeypatch: pytest.MonkeyPatch,
    expected: Mapping[str, Mapping[str, Any]],
    seen: list[str] | None = None,
) -> None:
    def replay_verifier(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["perform_real_source_smoke"] is False
        assert isinstance(kwargs["retained_smoke_replay_evidence"], Mapping)
        candidate = kwargs["candidate"]
        candidate_sha = candidate["capability_candidate_sha256_without_self_field"]
        if seen is not None:
            seen.append(candidate["action_class"])
        return copy.deepcopy(expected[candidate_sha])

    monkeypatch.setattr(
        round7._capability_verifier,
        "verify_bounded_capability_candidate",
        replay_verifier,
    )
    monkeypatch.setattr(
        round7._reference_verifier,
        "verify_reference_chain_capability_candidate",
        replay_verifier,
    )


def _replace_attacked_successor(
    *,
    root: Path,
    manifest: dict[str, Any],
    cycles: list[dict[str, Any]],
    step: int,
    record: Mapping[str, Any],
    candidate: dict[str, Any],
    verification: dict[str, Any],
) -> None:
    suffix, _action_class, _implementation_id, cycle_index, manifest_field = round6._PROMOTIONS[
        step - 1
    ]
    successor = capability_registry.promote_verified_capability(
        registry=record["predecessor_registry"],
        candidate=candidate,
        verification_receipt=verification,
    )
    _write_json(root, round6._name("capability-candidate", suffix), candidate)
    _write_json(root, round6._name("capability-verification", suffix), verification)
    _write_json(root, round6._name("capability-registry-promoted", suffix), successor)
    registry_sha = successor["capability_registry_sha256_without_self_field"]
    cycles[cycle_index - 1]["promoted_registry_sha256"] = registry_sha
    if manifest_field is not None:
        manifest[manifest_field] = registry_sha
    manifest["cycles"] = cycles
    _write_json(root, "autonomous-production-manifest.json", manifest)


def test_all_four_promotions_use_zero_network_authoritative_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _manifest, _cycles, _records, expected = _build_prefix(tmp_path, through_step=4)
    seen: list[str] = []
    _install_authoritative_replay(monkeypatch, expected, seen)

    round7.verify_exact_head_round7_boundaries(tmp_path)

    assert seen == [promotion[1] for promotion in round6._PROMOTIONS]


@pytest.mark.parametrize("step", [1, 2, 3, 4])
def test_self_consistently_rehashed_spec_candidate_receipt_cannot_replace_canonical_spec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    step: int,
) -> None:
    manifest, cycles, records, expected = _build_prefix(tmp_path, through_step=step)
    _install_authoritative_replay(monkeypatch, expected)
    record = records[step - 1]
    forged_spec = copy.deepcopy(record["specification"])
    forged_spec["attacker_added_spec_authority"] = True
    _rehash(forged_spec, "capability_specification_sha256_without_self_field")
    action_class = round6._PROMOTIONS[step - 1][1]
    primitives = round7._TRUSTED_PRIMITIVES[action_class]
    forged_resolution = capability_resolver.resolve_or_discover_capability(
        registry=record["predecessor_registry"],
        capability_specification=forged_spec,
        available_verified_primitives=primitives,
    )
    forged_candidate = copy.deepcopy(forged_resolution["candidate"])
    assert isinstance(forged_candidate, dict)
    forged_evidence = capability_smoke_replay_evidence.build_smoke_replay_evidence(
        action_class=action_class,
        capability_specification_sha256=forged_spec[
            "capability_specification_sha256_without_self_field"
        ],
        capability_candidate_sha256=forged_candidate[
            "capability_candidate_sha256_without_self_field"
        ],
        mission_sha256=MISSION_SHA,
        verification_context=record["context"],
        fetch_records=record["replay_evidence"]["fetch_records"],
    )
    forged_verification = _verification(
        specification=forged_spec,
        candidate=forged_candidate,
        primitives=primitives,
        replay_evidence=forged_evidence,
    )
    suffix = round6._PROMOTIONS[step - 1][0]
    _write_json(tmp_path, round6._name("capability-specification", suffix), forged_spec)
    _replace_attacked_successor(
        root=tmp_path,
        manifest=manifest,
        cycles=cycles,
        step=step,
        record=record,
        candidate=forged_candidate,
        verification=forged_verification,
    )

    with pytest.raises(
        round7.AutonomousProductionExactHeadRound7Error,
        match=f"capability promotion {step} specification drifted from canonical gap replay",
    ):
        round7.verify_exact_head_round7_boundaries(tmp_path)


@pytest.mark.parametrize("step", [3, 4])
@pytest.mark.parametrize(
    "authority_field",
    [
        "network_authority_granted",
        "execution_authority_granted",
        "scientific_status_change_authorized",
        "self_promotion_requested",
    ],
)
def test_promotion_three_and_four_permission_expanded_candidate_cannot_promote(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    step: int,
    authority_field: str,
) -> None:
    manifest, cycles, records, expected = _build_prefix(tmp_path, through_step=step)
    _install_authoritative_replay(monkeypatch, expected)
    record = records[step - 1]
    forged_candidate = copy.deepcopy(record["candidate"])
    forged_candidate[authority_field] = True
    _rehash(forged_candidate, "capability_candidate_sha256_without_self_field")

    forged_verification = copy.deepcopy(record["verification"])
    forged_verification["capability_candidate_sha256"] = forged_candidate[
        "capability_candidate_sha256_without_self_field"
    ]
    forged_verification["all_required_checks_passed"] = True
    forged_verification["promotion_eligible"] = True
    _rehash(forged_verification, "capability_verification_sha256_without_self_field")
    _replace_attacked_successor(
        root=tmp_path,
        manifest=manifest,
        cycles=cycles,
        step=step,
        record=record,
        candidate=forged_candidate,
        verification=forged_verification,
    )

    with pytest.raises(
        round7.AutonomousProductionExactHeadRound7Error,
        match=f"capability promotion {step} candidate drifted from trusted factory replay",
    ):
        round7.verify_exact_head_round7_boundaries(tmp_path)


@pytest.mark.parametrize("step", [3, 4])
def test_promotion_three_and_four_fabricated_passing_receipt_cannot_promote(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    step: int,
) -> None:
    manifest, cycles, records, expected = _build_prefix(tmp_path, through_step=step)
    _install_authoritative_replay(monkeypatch, expected)
    record = records[step - 1]
    candidate = copy.deepcopy(record["candidate"])
    forged_verification = copy.deepcopy(record["verification"])
    forged_verification["fabricated_passing_marker"] = True
    forged_verification["all_required_checks_passed"] = True
    forged_verification["promotion_eligible"] = True
    _rehash(forged_verification, "capability_verification_sha256_without_self_field")
    _replace_attacked_successor(
        root=tmp_path,
        manifest=manifest,
        cycles=cycles,
        step=step,
        record=record,
        candidate=candidate,
        verification=forged_verification,
    )

    with pytest.raises(
        round7.AutonomousProductionExactHeadRound7Error,
        match=(
            f"capability promotion {step} verification drifted from authoritative "
            "retained-evidence replay"
        ),
    ):
        round7.verify_exact_head_round7_boundaries(tmp_path)


def test_missing_retained_smoke_evidence_fails_closed_before_historical_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, cycles, records, expected = _build_prefix(tmp_path, through_step=2)
    _install_authoritative_replay(monkeypatch, expected)
    record = records[1]
    candidate = copy.deepcopy(record["candidate"])
    verification = copy.deepcopy(record["verification"])
    verification.pop("real_source_smoke_replay_evidence", None)
    verification.pop("real_source_smoke_replay_evidence_sha256", None)
    _rehash(verification, "capability_verification_sha256_without_self_field")
    _replace_attacked_successor(
        root=tmp_path,
        manifest=manifest,
        cycles=cycles,
        step=2,
        record=record,
        candidate=candidate,
        verification=verification,
    )

    with pytest.raises(
        round7.AutonomousProductionExactHeadRound7Error,
        match="capability promotion 2 retained smoke replay evidence is missing",
    ):
        round7.verify_exact_head_round7_boundaries(tmp_path)


def test_trusted_replay_is_wired_before_registry_lineage_replay() -> None:
    verifier = (
        ROOT
        / "src/materials_data_analyzer/research_loop/autonomous_production_live_verifier.py"
    ).read_text(encoding="utf-8")
    assert "verify_exact_head_round7_boundaries" in verifier
    assert verifier.index("verify_exact_head_round7_boundaries(output_root)") < verifier.index(
        "verify_exact_head_round6_boundaries(output_root)"
    )
