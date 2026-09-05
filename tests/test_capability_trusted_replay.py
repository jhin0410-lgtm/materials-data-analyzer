from __future__ import annotations

import copy
import hashlib
import json
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
)


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
    (root / name).write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _specification(
    *,
    action_class: str,
    step: int,
    available_action_classes: list[str],
) -> dict[str, Any]:
    gap = capability_expansion.build_capability_gap(
        requested_action={
            "action_class": action_class,
            "objective": f"Execute trusted capability replay promotion {step}.",
            "eligible_evidence_lanes": ["paper_and_supplementary_material"],
        },
        predecessor_report={"report_sha256_without_self_field": "a" * 64},
        available_action_classes=available_action_classes,
    )
    return capability_expansion.build_capability_specification(gap)


def _install_deterministic_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    smoke: dict[str, Any] = {
        "schema_version": "test-1.0",
        "smoke_status": "deterministic_test_source_retrieved",
        "source_id": "test-source",
        "source_sha256": "b" * 64,
        "source_size_bytes": 128,
        "network_requests_performed": 1,
        "unrestricted_search_performed": False,
        "arbitrary_url_fetch_performed": False,
        "scientific_status_changed": False,
    }
    smoke["smoke_receipt_sha256_without_self_field"] = _canonical_sha(smoke)
    monkeypatch.setattr(
        round7._capability_verifier,
        "_real_source_smoke",
        lambda **_kwargs: (True, copy.deepcopy(smoke)),
    )


def _build_prefix(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    through_step: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    _install_deterministic_smoke(monkeypatch)
    registry = capability_registry.build_initial_capability_registry(
        verified_action_classes=round6._INITIAL_VERIFIED_ACTIONS,
    )
    _write_json(root, "capability-registry-initial.json", registry)
    available_actions = list(round6._INITIAL_VERIFIED_ACTIONS)
    cycles: list[dict[str, Any]] = [
        {"cycle_index": index} for index in range(1, round6._PROMOTIONS[through_step - 1][3] + 1)
    ]
    manifest: dict[str, Any] = {"cycles": cycles}
    records: list[dict[str, Any]] = []

    for step, promotion in enumerate(round6._PROMOTIONS[:through_step], start=1):
        suffix, action_class, _implementation_id, cycle_index, manifest_field = promotion
        specification = _specification(
            action_class=action_class,
            step=step,
            available_action_classes=available_actions,
        )
        primitives = round7._TRUSTED_PRIMITIVES[action_class]
        resolution = capability_resolver.resolve_or_discover_capability(
            registry=registry,
            capability_specification=specification,
            available_verified_primitives=primitives,
        )
        candidate = copy.deepcopy(resolution["candidate"])
        assert isinstance(candidate, dict)
        verification = round7._capability_verifier.verify_bounded_capability_candidate(
            capability_specification=specification,
            candidate=candidate,
            available_verified_primitives=primitives,
            repository_root=Path(__file__).resolve().parents[1],
            mission_path=(
                Path(__file__).resolve().parents[1]
                / "configs/research/autonomous_in625_production_mission.v1.json"
            ),
            expected_mission_sha256=hashlib.sha256(
                (
                    Path(__file__).resolve().parents[1]
                    / "configs/research/autonomous_in625_production_mission.v1.json"
                ).read_bytes()
            ).hexdigest(),
            perform_real_source_smoke=True,
        )
        successor = capability_registry.promote_verified_capability(
            registry=registry,
            candidate=candidate,
            verification_receipt=verification,
        )
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
                "predecessor_registry": registry,
            }
        )
        registry = successor
        available_actions.append(action_class)

    manifest["cycles"] = cycles
    _write_json(root, "autonomous-production-manifest.json", manifest)
    return manifest, cycles, records


def _replace_attacked_successor(
    *,
    root: Path,
    manifest: dict[str, Any],
    cycles: list[dict[str, Any]],
    step: int,
    record: dict[str, Any],
    candidate: dict[str, Any],
    verification: dict[str, Any],
) -> None:
    promotion = round6._PROMOTIONS[step - 1]
    suffix, _action_class, _implementation_id, cycle_index, manifest_field = promotion
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


@pytest.mark.parametrize("step", [1, 2])
@pytest.mark.parametrize(
    "authority_field",
    [
        "network_authority_granted",
        "execution_authority_granted",
        "scientific_status_change_authorized",
        "self_promotion_requested",
    ],
)
def test_rehashed_permission_expanded_candidate_cannot_promote(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    step: int,
    authority_field: str,
) -> None:
    manifest, cycles, records = _build_prefix(
        tmp_path,
        monkeypatch,
        through_step=step,
    )
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
    _rehash(
        forged_verification,
        "capability_verification_sha256_without_self_field",
    )
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


@pytest.mark.parametrize("step", [1, 2])
def test_rehashed_fabricated_passing_receipt_cannot_promote(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    step: int,
) -> None:
    manifest, cycles, records = _build_prefix(
        tmp_path,
        monkeypatch,
        through_step=step,
    )
    record = records[step - 1]
    candidate = copy.deepcopy(record["candidate"])
    forged_verification = copy.deepcopy(record["verification"])
    forged_smoke = copy.deepcopy(forged_verification["real_source_smoke_receipt"])
    forged_smoke["source_sha256"] = "f" * 64
    _rehash(forged_smoke, "smoke_receipt_sha256_without_self_field")
    forged_verification["real_source_smoke_receipt"] = forged_smoke
    forged_verification["real_source_smoke_receipt_sha256"] = forged_smoke[
        "smoke_receipt_sha256_without_self_field"
    ]
    forged_verification["all_required_checks_passed"] = True
    forged_verification["promotion_eligible"] = True
    _rehash(
        forged_verification,
        "capability_verification_sha256_without_self_field",
    )
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
        match=f"capability promotion {step} verification drifted from authoritative replay",
    ):
        round7.verify_exact_head_round7_boundaries(tmp_path)


def test_trusted_replay_is_wired_before_registry_lineage_replay() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    verifier = (
        repository_root
        / "src/materials_data_analyzer/research_loop/autonomous_production_live_verifier.py"
    ).read_text(encoding="utf-8")
    assert "verify_exact_head_round7_boundaries" in verifier
    assert verifier.index("verify_exact_head_round7_boundaries(output_root)") < verifier.index(
        "verify_exact_head_round6_boundaries(output_root)"
    )
