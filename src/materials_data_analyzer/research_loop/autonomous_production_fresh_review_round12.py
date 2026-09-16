"""Fresh-review round 12: independent replay of retained execution/control-plane evidence.

This additive verifier closes authority gaps that self-consistent manifest rehashing must not
satisfy. It binds cycle-1 request/execution evidence to the immutable ledger and standing
network policy, rebuilds the retained Zenodo README manifest from exact bytes, replays the
original pre-authorization cycle-8 resolver state, checks exact discovery-cycle projections,
and runs the cycle-10 derived authorization/assessment replay as soon as that lifecycle stage
exists rather than only on a complete 12-cycle run.

No check here promotes scientific evidence. Operational provenance, literature evidence, and
scientific conclusions remain separate trust domains.
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from . import autonomous_production_fresh_review_round10 as _round10
from . import autonomous_production_fresh_review_round11 as _round11
from . import autonomous_production_merge_gate_hardening as _merge_gate
from . import autonomous_production_recursive_capability_extension as _recursive_extension
from . import autonomous_production_reference_chain_extension as _reference_extension
from .capability_resolver import CapabilityResolverError, resolve_or_discover_capability
from .in625_external_evidence_action import ACTION_TYPE, ACTION_VERSION
from .in625_network_policy import In625NetworkPolicyError, authenticate_in625_network_policy
from .in625_zenodo_live_evidence import (
    In625ZenodoLiveEvidenceError,
    build_verified_in625_zenodo_readme_manifest,
)
from .kernel import ResearchLoopError, load_research_state
from .recursive_authorization_provenance import (
    RecursiveAuthorizationProvenanceError,
    verify_preexecution_authorization,
)

AutonomousProductionFreshReviewRound12Error = (
    _merge_gate.AutonomousProductionMergeGateHardeningError
)

_NETWORK_POLICY_PATH = "configs/research/in625_zenodo_network_acquisition_policy.v1.json"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionFreshReviewRound12Error(message)


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    return value


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(_round11._canonical_bytes(value)).hexdigest()


def _qualification_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    raw_path = result.get("source_config_path")
    _round11._safe_historical_suffix(
        raw_path,
        suffix=tuple(PurePosixPath(_round11._SOURCE_CONFIG_PATH).parts),
        label="standing policy source_config_path",
    )
    result["source_config_path"] = _round11._SOURCE_CONFIG_PATH
    return result


def _verify_cycle1_independent_bindings(
    root: Path,
    manifest: Mapping[str, Any],
) -> None:
    cycles = manifest.get("cycles")
    _require(isinstance(cycles, list) and cycles, "autonomous production cycle 1 is missing")
    cycle1 = _mapping(cycles[0], label="cycle 1")
    repository_root, mission_path, mission_sha = _round11._round7._trusted_mission_binding()
    source_config_path = (repository_root / _round11._SOURCE_CONFIG_PATH).resolve(strict=True)
    network_policy_path = (repository_root / _NETWORK_POLICY_PATH).resolve(strict=True)
    registry_path = (repository_root / _round11._ACTION_REGISTRY_PATH).resolve(strict=True)

    try:
        qualification = authenticate_in625_network_policy(
            repository_root=repository_root,
            mission_path=mission_path,
            expected_mission_sha256=mission_sha,
            policy_path=network_policy_path,
            source_config_path=source_config_path,
        )
    except (In625NetworkPolicyError, OSError) as exc:
        raise AutonomousProductionFreshReviewRound12Error(
            f"cycle-1 standing network policy replay failed: {exc}"
        ) from exc
    _require(
        cycle1.get("network_policy_sha256") == qualification.get("policy_sha256"),
        "cycle-1 network policy digest drifted from mission-pinned policy replay",
    )
    persisted_qualification = _merge_gate._load(
        root, "standing-network-policy-qualification.json"
    )
    _round11._require_json_equal(
        _qualification_projection(persisted_qualification),
        _qualification_projection(qualification),
        "standing network policy qualification drifted from independent replay",
    )

    source_config = _round11._load_plain_json(
        source_config_path, label="tracked IN625 source config"
    )
    zenodo = _mapping(source_config.get("zenodo"), label="tracked IN625 source config zenodo")
    readme_name = zenodo.get("readme_file")
    _require(isinstance(readme_name, str) and bool(readme_name), "tracked README identity is missing")
    metadata_path = root / "record.json"
    readme_path = root / readme_name
    _require(metadata_path.is_file(), "cycle-1 retained Zenodo metadata is missing")
    _require(readme_path.is_file(), "cycle-1 retained Zenodo README is missing")
    try:
        expected_source_manifest = build_verified_in625_zenodo_readme_manifest(
            config=source_config,
            metadata_bytes=metadata_path.read_bytes(),
            readme_bytes=readme_path.read_bytes(),
        )
    except (In625ZenodoLiveEvidenceError, OSError) as exc:
        raise AutonomousProductionFreshReviewRound12Error(
            f"cycle-1 source README manifest replay failed: {exc}"
        ) from exc
    persisted_source_manifest = _merge_gate._load(root, "source-readme-manifest.json")
    _round11._require_json_equal(
        persisted_source_manifest,
        expected_source_manifest,
        "source README manifest drifted from retained metadata/README replay",
    )

    request_path = _round11._find_request_by_sha(root, cycle1.get("typed_request_sha256"))
    request = _round11._load_plain_json(
        request_path, label="cycle-1 typed execution request"
    )
    research_run = root / "typed-research-run"
    try:
        state = load_research_state(research_run)
    except (ResearchLoopError, OSError) as exc:
        raise AutonomousProductionFreshReviewRound12Error(
            f"cycle-1 retained research state replay failed: {exc}"
        ) from exc
    actions = state.get("actions")
    _require(isinstance(actions, list) and len(actions) == 1, "cycle-1 ledger action count drifted")
    action = _mapping(actions[0], label="cycle-1 immutable-ledger action")
    action_id = action.get("action_id")
    _require(isinstance(action_id, str) and bool(action_id), "cycle-1 ledger action id is missing")
    _require(
        request.get("action_id") == action_id,
        "cycle-1 typed request action_id drifted from immutable-ledger action",
    )

    try:
        preexecution = verify_preexecution_authorization(
            adapter_id=_round11._execution_verifier.ADAPTER_ID,
            repository_root=repository_root,
            research_run=research_run,
            action_registry_path=registry_path,
            expected_action_id=action_id,
            expected_concrete_action_type=ACTION_TYPE,
            expected_concrete_action_version=ACTION_VERSION,
            expected_candidate_action_class=ACTION_TYPE,
        )
    except (RecursiveAuthorizationProvenanceError, ResearchLoopError, OSError) as exc:
        raise AutonomousProductionFreshReviewRound12Error(
            f"cycle-1 pre-execution ledger/authorization replay failed: {exc}"
        ) from exc
    prefix_sha = preexecution.get("pre_execution_ledger_sha256")
    _require(
        cycle1.get("pre_execution_ledger_sha256") == prefix_sha,
        "cycle-1 pre-execution ledger digest drifted from immutable-ledger prefix replay",
    )
    handoff = _merge_gate._load(root, "typed-execution-handoff.json")
    _require(
        handoff.get("research_ledger_sha256") == prefix_sha,
        "typed execution handoff ledger digest drifted from immutable-ledger prefix replay",
    )

    artifacts = action.get("artifacts")
    _require(isinstance(artifacts, list), "cycle-1 ledger action artifacts are malformed")
    expected_suffix = (
        "typed-research-run",
        "actions",
        action_id,
        "action_result.json",
    )
    matches: list[Mapping[str, Any]] = []
    for raw in artifacts:
        if not isinstance(raw, Mapping):
            continue
        path = raw.get("path")
        if not isinstance(path, str):
            continue
        normalized = path.replace("\\", "/")
        parts = tuple(part for part in PurePosixPath(normalized).parts if part not in {"/", ""})
        if tuple(parts[-len(expected_suffix):]) == expected_suffix:
            matches.append(raw)
    _require(len(matches) == 1, "immutable ledger must bind exactly one action_result.json artifact")
    artifact = matches[0]
    _require(
        isinstance(artifact.get("sha256"), str)
        and len(str(artifact.get("sha256"))) == 64
        and type(artifact.get("bytes")) is int
        and int(artifact.get("bytes")) > 0,
        "immutable ledger action-result artifact binding is malformed",
    )
    retained_report = research_run / "actions" / action_id / "action_result.json"
    _require(retained_report.is_file(), "retained cycle-1 action_result.json is missing")
    _require(
        hashlib.sha256(retained_report.read_bytes()).hexdigest() == artifact.get("sha256")
        and retained_report.stat().st_size == artifact.get("bytes"),
        "retained cycle-1 action_result.json bytes drifted from immutable ledger binding",
    )


def _verify_original_cycle8_resolution(
    root: Path,
    manifest: Mapping[str, Any],
    replay: Mapping[int, Mapping[str, Any]],
) -> None:
    cycles = manifest.get("cycles")
    _require(isinstance(cycles, list), "autonomous production cycles must be a list")
    if len(cycles) < 8:
        return
    step2 = replay.get(2)
    _require(isinstance(step2, Mapping), "promotion-2 replay state is missing at cycle 8")
    registry = _mapping(step2.get("registry_after"), label="promotion-2 promoted registry")
    suffix, action_class, _implementation, _promotion_cycle, _manifest_field = (
        _round11._round6._PROMOTIONS[2]
    )
    _gap, specification, _predecessor = _round11._round7._canonical_gap_and_specification(
        root=root,
        step=3,
        action_class=action_class,
        registry=registry,
        suffix=suffix,
    )
    try:
        expected = resolve_or_discover_capability(
            registry=registry,
            capability_specification=specification,
            available_verified_primitives=_recursive_extension._VERIFIED_PRIMITIVES,
        )
    except CapabilityResolverError as exc:
        raise AutonomousProductionFreshReviewRound12Error(
            f"cycle-8 original resolver replay failed: {exc}"
        ) from exc
    _require(
        expected.get("resolution_status") == "no_bounded_candidate_available",
        "cycle-8 original resolver unexpectedly gained bounded authority",
    )
    persisted = _merge_gate._load(root, "capability-resolution-3.json")
    _round11._require_json_equal(
        persisted,
        expected,
        "cycle-8 original capability-resolution-3 drifted from pre-authorization replay",
    )


def _verify_discovery_cycle_projections(
    root: Path,
    manifest: Mapping[str, Any],
    replay: Mapping[int, Mapping[str, Any]],
) -> None:
    cycles = manifest.get("cycles")
    _require(isinstance(cycles, list), "autonomous production cycles must be a list")

    if len(cycles) >= 5:
        gap = _merge_gate._load(root, "capability-gap.json")
        spec = _merge_gate._load(root, "capability-specification.json")
        resolution = _merge_gate._load(root, "capability-resolution.json")
        expected = {
            "cycle_index": 5,
            "predecessor_cycle_sha256": _mapping(cycles[3], label="cycle 4").get("cycle_sha256"),
            "input_blocker": "experiment_specific_calibration_protocol_bridge_not_established",
            "selected_action_class": _round11._round6._PROMOTIONS[0][1],
            "capability_available": False,
            "capability_gap_class": gap["gap_class"],
            "capability_gap_sha256": gap["capability_gap_sha256_without_self_field"],
            "capability_specification_sha256": spec["capability_specification_sha256_without_self_field"],
            "resolution_status": resolution["resolution_status"],
            "bounded_candidate_discovered": isinstance(resolution.get("candidate"), Mapping),
            "unrestricted_discovery_performed": False,
            "arbitrary_code_generation_performed": False,
            "global_evidence_unavailability_claimed": False,
            "new_verified_information": True,
            "scientific_status_changed": False,
        }
        expected["cycle_sha256"] = _canonical_sha(expected)
        _round11._require_json_equal(
            cycles[4], expected, "cycle 5 projection drifted from canonical capability discovery"
        )

    if len(cycles) >= 7:
        gap = _merge_gate._load(root, "capability-gap-2.json")
        spec = _merge_gate._load(root, "capability-specification-2.json")
        resolution = _merge_gate._load(root, "capability-resolution-2.json")
        candidate = _mapping(resolution.get("candidate"), label="cycle-7 canonical candidate")
        expected = {
            "cycle_index": 7,
            "predecessor_cycle_sha256": _mapping(cycles[5], label="cycle 6").get("cycle_sha256"),
            "input_blocker": "experiment_specific_calibration_record_not_discovered",
            "selected_action_class": _round11._round6._PROMOTIONS[1][1],
            "capability_available": False,
            "capability_gap_class": gap["gap_class"],
            "capability_gap_sha256": gap["capability_gap_sha256_without_self_field"],
            "capability_specification_sha256": spec["capability_specification_sha256_without_self_field"],
            "resolution_status": resolution["resolution_status"],
            "bounded_candidate_discovered": True,
            "capability_candidate_sha256": candidate["capability_candidate_sha256_without_self_field"],
            "unrestricted_discovery_performed": False,
            "arbitrary_code_generation_performed": False,
            "global_evidence_unavailability_claimed": False,
            "new_verified_information": True,
            "scientific_status_changed": False,
        }
        expected["cycle_sha256"] = _canonical_sha(expected)
        _round11._require_json_equal(
            cycles[6], expected, "cycle 7 projection drifted from canonical capability discovery"
        )

    if len(cycles) >= 9:
        gap = _merge_gate._load(root, "capability-gap-3.json")
        spec = _merge_gate._load(root, "capability-specification-3.json")
        resolution = _merge_gate._load(root, "capability-resolution-3-derived.json")
        candidate = _mapping(resolution.get("candidate"), label="cycle-9 canonical candidate")
        expected = {
            "cycle_index": 9,
            "predecessor_cycle_sha256": _mapping(cycles[7], label="cycle 8").get("cycle_sha256"),
            "input_blocker": "candidate_acquisition_capability_not_established",
            "selected_action_class": _round11._round6._PROMOTIONS[2][1],
            "capability_available": False,
            "capability_gap_class": gap["gap_class"],
            "capability_gap_sha256": gap["capability_gap_sha256_without_self_field"],
            "capability_specification_sha256": spec["capability_specification_sha256_without_self_field"],
            "resolution_status": resolution["resolution_status"],
            "bounded_candidate_discovered": True,
            "capability_candidate_sha256": candidate["capability_candidate_sha256_without_self_field"],
            "caller_authored_url_used": False,
            "arbitrary_code_generation_performed": False,
            "global_evidence_unavailability_claimed": False,
            "new_verified_information": True,
            "scientific_status_changed": False,
        }
        expected["cycle_sha256"] = _canonical_sha(expected)
        _round11._require_json_equal(
            cycles[8], expected, "cycle 9 projection drifted from canonical capability discovery"
        )

    if len(cycles) >= 11:
        predecessor8 = _round11._reconstruct_cycle8_predecessor(root, manifest, replay)
        predecessor10 = _round11._reconstruct_cycle10_predecessor(
            root, manifest, replay, predecessor8
        )
        resolution4 = _merge_gate._load(root, "capability-resolution-4.json")
        candidate4 = _merge_gate._load(root, "capability-candidate-4.json")
        spec4 = _merge_gate._load(root, "capability-specification-4.json")
        reauthentication = _reference_extension._authenticate_predecessor_candidate(
            predecessor_resolution=resolution4,
            predecessor_candidate=candidate4,
            capability_specification=spec4,
            predecessor_manifest_sha256=predecessor10["manifest_sha256"],
        )
        metadata_path = (root / "nist-mds2-2923" / "nerdm-metadata.json").resolve(strict=True)
        try:
            metadata_path.relative_to(root)
        except ValueError as exc:
            raise AutonomousProductionFreshReviewRound12Error(
                "cycle-11 NERDm metadata escaped output root"
            ) from exc
        metadata_sha = hashlib.sha256(metadata_path.read_bytes()).hexdigest()
        candidate = _mapping(candidate4, label="cycle-11 canonical candidate")
        expected = {
            "cycle_index": 11,
            "predecessor_cycle_sha256": _mapping(cycles[9], label="cycle 10").get("cycle_sha256"),
            "input_blocker": "experiment_identity_reference_chain_capability_not_established",
            "selected_action_class": _round11._round6._PROMOTIONS[3][1],
            "capability_available": False,
            "resolution_status": reauthentication["resolution_status"],
            "bounded_candidate_discovered": False,
            "predecessor_candidate_reauthenticated": True,
            "candidate_rediscovery_performed": False,
            "capability_candidate_sha256": candidate["capability_candidate_sha256_without_self_field"],
            "predecessor_manifest_sha256": predecessor10["manifest_sha256"],
            "nerdm_metadata_sha256": metadata_sha,
            "caller_authored_url_used": False,
            "arbitrary_code_generation_performed": False,
            "global_evidence_unavailability_claimed": False,
            "new_verified_information": False,
            "scientific_status_changed": False,
        }
        expected["cycle_sha256"] = _canonical_sha(expected)
        _round11._require_json_equal(
            cycles[10], expected, "cycle 11 projection drifted from canonical candidate reauthentication"
        )


def verify_fresh_review_round12_boundaries(output_root: str | Path) -> None:
    """Apply independent replay to retained execution and partial-lifecycle authority artifacts."""
    root = Path(output_root).expanduser().resolve(strict=True)
    manifest = _merge_gate._load(root, "autonomous-production-manifest.json")
    cycles = manifest.get("cycles")
    _require(isinstance(cycles, list) and cycles, "autonomous production cycles must be a non-empty list")

    _verify_cycle1_independent_bindings(root, manifest)
    replay = _round11._strict_replay_promotions(root, manifest)
    _verify_original_cycle8_resolution(root, manifest, replay)
    _verify_discovery_cycle_projections(root, manifest, replay)
    if len(cycles) >= 10:
        _round10._verify_derived_authorization_and_bridge_assessment(root, manifest, replay)


__all__ = [
    "AutonomousProductionFreshReviewRound12Error",
    "verify_fresh_review_round12_boundaries",
]
