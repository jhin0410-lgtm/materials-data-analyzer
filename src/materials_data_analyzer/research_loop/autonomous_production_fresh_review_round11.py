"""Final exact-head closure for stage-aware replay, type fidelity, and cycle-1 authority.

This additive verifier closes the fresh-review findings without widening scientific authority:

* capability promotion replay is stage-aware for 5/7/9/11-cycle bounded stops;
* all reached gap/spec/resolution/candidate/verification/registry objects are compared as
  canonical JSON bytes so Python numeric aliases cannot satisfy authority equality;
* cycle-6 retained reacquisition must satisfy the complete eight-source execution boundary;
* the complete retained eight-cycle predecessor manifest is reconstructed from the already
  authenticated final state and canonical cycle-8 producer contract;
* that predecessor is advanced through the canonical cycle-10 producer contract, binding the
  cycle-11 predecessor manifest digest and the derived candidate-reauthentication receipt; and
* cycle-1 network authorization, typed handoff, typed execution result, and persisted research
  state are independently reconstructed or semantically projected from tracked/retained inputs.

Operational provenance remains separate from scientific conclusions.  No check in this module
promotes direct comparability, model validity, hypothesis truth, or positive closeout.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path, PurePath, PurePosixPath
from typing import Any

from . import autonomous_production_candidate_acquisition_extension as _candidate_extension
from . import autonomous_production_exact_head_p2_round6 as _round6
from . import autonomous_production_exact_head_p2_round7 as _round7
from . import autonomous_production_fresh_review_round9 as _round9
from . import autonomous_production_fresh_review_round10 as _round10
from . import autonomous_production_merge_gate_hardening as _merge_gate
from . import autonomous_production_recursive_capability_extension as _recursive_extension
from . import autonomous_production_reference_chain_extension as _reference_extension
from . import in625_execution_verifier as _execution_verifier
from .action_registry import load_action_registry
from .capability_registry import CapabilityRegistryError, promote_verified_capability
from .capability_resolver import CapabilityResolverError, resolve_or_discover_capability
from .in625_archive_network_acquisition import (
    In625ArchiveNetworkAcquisitionError,
    build_in625_archive_network_authorization,
)
from .in625_external_evidence_action import ACTION_TYPE, ACTION_VERSION, COST_UNITS
from .kernel import ResearchLoopError, load_research_state

AutonomousProductionFreshReviewRound11Error = (
    _merge_gate.AutonomousProductionMergeGateHardeningError
)

_SOURCE_CONFIG_PATH = "configs/research/in625_zenodo_20503603_verified_source.v1.json"
_ACTION_REGISTRY_PATH = "configs/research/in625_external_evidence_action_registry.v1.json"
_POST_CYCLE8_ADDED_KEYS = {
    "calibration_candidate_bridge_assessment_sha256",
    "calibration_methodology_established",
    "dataset_to_weaver_association_established",
    "derived_candidate_acquisition_executed",
    "derived_candidate_acquisition_sha256",
    "exact_machine_setting_to_calibrated_power_relation_established",
    "exact_mds2_experiment_identity_established",
    "fifth_capability_gap_emitted",
    "fourth_candidate_reauthenticated_from_predecessor",
    "fourth_candidate_rediscovery_performed",
    "fourth_capability_candidate_discovered",
    "fourth_capability_candidate_promoted",
    "fourth_capability_candidate_sha256",
    "fourth_capability_gap_emitted",
    "fourth_research_action_resumed",
    "mds2_195_800_condition_signature_match",
    "naderi_reference_evidence_sha256",
    "naderi_to_weaver_experiment_detail_reference_established",
    "reference_chain_assessment_sha256",
    "reference_chain_policy_sha256",
    "third_capability_candidate_promoted",
    "third_capability_verification_sha256",
    "third_promoted_capability_registry_sha256",
    "third_research_action_resumed",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionFreshReviewRound11Error(message)


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    return value


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _require_json_equal(actual: object, expected: object, message: str) -> None:
    _require(_canonical_bytes(actual) == _canonical_bytes(expected), message)


def _strict_int(value: object, *, expected: int | None = None, label: str) -> int:
    _require(type(value) is int, f"{label} must be a JSON integer")
    result = int(value)
    if expected is not None:
        _require(result == expected, f"{label} drifted")
    return result


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_historical_suffix(raw: object, *, suffix: Sequence[str], label: str) -> None:
    _require(isinstance(raw, str) and bool(raw.strip()), f"{label} must be a path string")
    normalized = raw.replace("\\", "/")
    parts = tuple(part for part in PurePosixPath(normalized).parts if part not in {"/", ""})
    _require(".." not in parts and "." not in parts, f"{label} contains traversal")
    _require(tuple(parts[-len(suffix):]) == tuple(suffix), f"{label} historical suffix drifted")


def _strict_replay_promotions(
    root: Path,
    manifest: Mapping[str, Any],
) -> dict[int, dict[str, Any]]:
    """Replay reached promotion stages without requiring not-yet-produced artifacts."""
    cycles_value = manifest.get("cycles")
    _require(isinstance(cycles_value, list), "autonomous production cycles must be a list")
    cycles = [_mapping(item, label=f"cycle {i}") for i, item in enumerate(cycles_value, start=1)]
    if len(cycles) < 5:
        return {}

    expected_registry = _round6.build_initial_capability_registry(
        verified_action_classes=_round6._INITIAL_VERIFIED_ACTIONS,
    )
    persisted_initial = _merge_gate._load(root, "capability-registry-initial.json")
    _require_json_equal(
        persisted_initial,
        expected_registry,
        "initial capability registry drifted under canonical JSON comparison",
    )
    replay: dict[int, dict[str, Any]] = {}

    for step, promotion in enumerate(_round6._PROMOTIONS, start=1):
        suffix, action_class, implementation_id, promotion_cycle_index, manifest_field = promotion
        discovery_cycle_index = promotion_cycle_index - 1
        if len(cycles) < discovery_cycle_index:
            break
        expected_gap, specification, predecessor = _round7._canonical_gap_and_specification(
            root=root,
            step=step,
            action_class=action_class,
            registry=expected_registry,
            suffix=suffix,
        )
        _require_json_equal(
            _merge_gate._load(root, _round6._name("capability-gap", suffix)),
            expected_gap,
            f"capability promotion {step} gap lost JSON type fidelity",
        )
        _require_json_equal(
            _merge_gate._load(root, _round6._name("capability-specification", suffix)),
            specification,
            f"capability promotion {step} specification lost JSON type fidelity",
        )
        primitives = _round7._TRUSTED_PRIMITIVES.get(action_class)
        _require(primitives is not None, f"capability promotion {step} has no trusted primitives")
        try:
            expected_resolution = resolve_or_discover_capability(
                registry=expected_registry,
                capability_specification=specification,
                available_verified_primitives=primitives,
            )
        except (CapabilityRegistryError, CapabilityResolverError) as exc:
            raise AutonomousProductionFreshReviewRound11Error(
                f"capability promotion {step} resolver replay failed: {exc}"
            ) from exc
        resolution_name = _round10._RESOLUTION_ARTIFACTS[step - 1]
        _require_json_equal(
            _merge_gate._load(root, resolution_name),
            expected_resolution,
            f"capability promotion {step} resolver output lost JSON type fidelity",
        )
        candidate = _mapping(
            expected_resolution.get("candidate"),
            label=f"capability promotion {step} canonical candidate",
        )
        persisted_candidate = _merge_gate._load(
            root, _round6._name("capability-candidate", suffix)
        )
        _require(
            candidate.get("implementation_id") == implementation_id,
            f"capability promotion {step} implementation identity drifted",
        )
        _require_json_equal(
            persisted_candidate,
            candidate,
            f"capability promotion {step} candidate lost JSON type fidelity",
        )

        # A 5/7/9/11-cycle bounded stop has discovered this candidate but has not yet produced
        # verification or promotion artifacts.  Accept that lifecycle after the canonical
        # pre-promotion resolution/candidate checks above.
        if len(cycles) < promotion_cycle_index:
            break

        persisted_verification = _merge_gate._load(
            root, _round6._name("capability-verification", suffix)
        )
        replayed_candidate, replayed_verification = (
            _round7._replay_trusted_candidate_and_verification(
                root=root,
                step=step,
                registry=expected_registry,
                specification=specification,
                predecessor=predecessor,
                persisted_candidate=persisted_candidate,
                persisted_verification=persisted_verification,
                cycles=cycles,
            )
        )
        _require_json_equal(
            persisted_verification,
            replayed_verification,
            f"capability promotion {step} verification lost JSON type fidelity",
        )
        try:
            successor = promote_verified_capability(
                registry=expected_registry,
                candidate=replayed_candidate,
                verification_receipt=replayed_verification,
            )
        except CapabilityRegistryError as exc:
            raise AutonomousProductionFreshReviewRound11Error(
                f"capability promotion {step} registry promotion failed: {exc}"
            ) from exc
        persisted_successor = _merge_gate._load(
            root, _round6._name("capability-registry-promoted", suffix)
        )
        _require_json_equal(
            persisted_successor,
            successor,
            f"capability promotion {step} successor registry lost JSON type fidelity",
        )
        try:
            expected_post_resolution = resolve_or_discover_capability(
                registry=successor,
                capability_specification=specification,
                available_verified_primitives=[],
            )
        except (CapabilityRegistryError, CapabilityResolverError) as exc:
            raise AutonomousProductionFreshReviewRound11Error(
                f"capability promotion {step} post-promotion resolver replay failed: {exc}"
            ) from exc
        persisted_post_resolution = _merge_gate._load(
            root, _round6._name("capability-post-promotion-resolution", suffix)
        )
        _require_json_equal(
            persisted_post_resolution,
            expected_post_resolution,
            f"capability promotion {step} post-promotion resolution lost JSON type fidelity",
        )
        replay[step] = {
            "gap": expected_gap,
            "specification": specification,
            "predecessor": predecessor,
            "candidate": replayed_candidate,
            "verification": replayed_verification,
            "registry_before": expected_registry,
            "registry_after": successor,
        }
        expected_registry = successor
        if manifest_field is not None:
            _require(
                manifest.get(manifest_field)
                == successor.get("capability_registry_sha256_without_self_field"),
                f"capability promotion {step} manifest registry binding drifted",
            )
    return replay


def _verify_cycle6_execution_boundary(root: Path, manifest: Mapping[str, Any]) -> None:
    cycles = manifest.get("cycles")
    _require(isinstance(cycles, list), "autonomous production cycles must be a list")
    if len(cycles) < 6:
        return
    bridge = _merge_gate._load(root, "calibration-protocol-bridge-capability-result.json")
    reacquired = _mapping(
        bridge.get("reacquired_source_evidence"),
        label="cycle-6 retained reacquisition evidence",
    )
    _merge_gate._verify_self_hash(
        reacquired,
        "report_sha256_without_self_field",
        label="cycle-6 retained reacquisition evidence",
    )
    _round9._validate_multisource_report_boundaries(reacquired)
    _strict_int(
        reacquired.get("network_requests_performed"), expected=8, label="cycle-6 network requests"
    )
    _strict_int(
        reacquired.get("network_request_budget"), expected=8, label="cycle-6 network request budget"
    )
    _strict_int(
        reacquired.get("retained_source_bytes_count"),
        expected=8,
        label="cycle-6 retained source count",
    )
    _strict_int(reacquired.get("source_count"), expected=8, label="cycle-6 source count")
    _require(
        reacquired.get("paper_claims_promoted_to_row_level_authority") is False
        and reacquired.get("scientific_status_changed") is False,
        "cycle-6 reacquisition promoted scientific authority",
    )
    sources = reacquired.get("sources")
    _require(isinstance(sources, list) and len(sources) == 8, "cycle-6 source records drifted")
    for index, raw in enumerate(sources, start=1):
        source = _mapping(raw, label=f"cycle-6 source {index}")
        _strict_int(source.get("request_index"), expected=index, label=f"cycle-6 source {index} request index")
        _require(
            source.get("row_level_measurement_authority") is False
            and source.get("scientific_status_changed") is False
            and source.get("source_bytes_persisted") is True,
            f"cycle-6 source {index} widened scientific/provenance authority",
        )


def _reconstruct_cycle8_predecessor(
    root: Path,
    manifest: Mapping[str, Any],
    replay: Mapping[int, Mapping[str, Any]],
) -> dict[str, Any]:
    context = _round10._trusted_step3_context(root=root, manifest=manifest, replay=replay)
    retained = _mapping(
        context.get("predecessor_manifest"),
        label="promotion-3 retained eight-cycle predecessor manifest",
    )
    expected = {
        key: deepcopy(value)
        for key, value in manifest.items()
        if key not in _POST_CYCLE8_ADDED_KEYS
    }
    _require(
        set(retained) == set(expected),
        "promotion-3 retained predecessor manifest field set drifted",
    )
    cycles = manifest.get("cycles")
    _require(isinstance(cycles, list) and len(cycles) >= 10, "cycle-8 predecessor requires ten-cycle state")
    gap3 = _merge_gate._load(root, "capability-gap-3.json")
    spec3 = _merge_gate._load(root, "capability-specification-3.json")
    expected.pop("manifest_sha256", None)
    expected.update(
        {
            "schema_version": _recursive_extension.AUTONOMOUS_PRODUCTION_SCHEMA_VERSION,
            "policy_version": _recursive_extension.AUTONOMOUS_PRODUCTION_POLICY_VERSION,
            "cycles": deepcopy(cycles[:8]),
            "stop": _recursive_extension._stop(
                "capability_expansion_required",
                _round6._PROMOTIONS[2][1],
                capability_gap_class=gap3["gap_class"],
                capability_gap_sha256=gap3["capability_gap_sha256_without_self_field"],
                capability_specification_sha256=spec3[
                    "capability_specification_sha256_without_self_field"
                ],
                bounded_candidate_discovered=False,
                unrestricted_discovery_performed=False,
                arbitrary_code_generation_performed=False,
            ),
            "third_capability_candidate_discovered": False,
            "generated_next_action_class": _round6._PROMOTIONS[2][1],
            "final_blocker": "candidate_acquisition_capability_not_established",
            "scientific_status_changed": False,
            "positive_scientific_closeout_established": False,
            "global_evidence_unavailability_claimed": False,
        }
    )
    expected["manifest_sha256"] = _canonical_sha(expected)
    _require_json_equal(
        retained,
        expected,
        "promotion-3 retained predecessor manifest drifted from complete canonical reconstruction",
    )
    return expected


def _reconstruct_cycle10_predecessor(
    root: Path,
    manifest: Mapping[str, Any],
    replay: Mapping[int, Mapping[str, Any]],
    predecessor8: Mapping[str, Any],
) -> dict[str, Any]:
    cycles = manifest.get("cycles")
    _require(isinstance(cycles, list) and len(cycles) >= 11, "cycle-10 predecessor requires cycle 11")
    step3 = replay.get(3)
    _require(isinstance(step3, Mapping), "promotion-3 trusted replay state is missing")
    verification3 = _mapping(step3.get("verification"), label="promotion-3 verification")
    registry3 = _mapping(step3.get("registry_after"), label="promotion-3 promoted registry")
    acquisition = _merge_gate._load(root, "nist-ammt-calibration-candidate-acquisition.json")
    assessment = _merge_gate._load(root, "nist-ammt-calibration-candidate-bridge-assessment.json")
    gap4 = _merge_gate._load(root, "capability-gap-4.json")
    spec4 = _merge_gate._load(root, "capability-specification-4.json")
    candidate4 = _merge_gate._load(root, "capability-candidate-4.json")
    next_action = _mapping(assessment.get("next_action"), label="cycle-10 assessment next action")
    next_action_class = next_action.get("action_class")
    _require(isinstance(next_action_class, str) and bool(next_action_class), "cycle-10 next action missing")

    expected = dict(deepcopy(predecessor8))
    expected.pop("manifest_sha256", None)
    expected.update(
        {
            "schema_version": _candidate_extension.AUTONOMOUS_PRODUCTION_SCHEMA_VERSION,
            "policy_version": _candidate_extension.AUTONOMOUS_PRODUCTION_POLICY_VERSION,
            "cycles": deepcopy(cycles[:10]),
            "stop": _candidate_extension._stop(
                "capability_expansion_required",
                next_action_class,
                capability_gap_class=gap4["gap_class"],
                capability_gap_sha256=gap4["capability_gap_sha256_without_self_field"],
                capability_specification_sha256=spec4[
                    "capability_specification_sha256_without_self_field"
                ],
                bounded_candidate_discovered=True,
                capability_candidate_sha256=candidate4[
                    "capability_candidate_sha256_without_self_field"
                ],
                candidate_verified=False,
                candidate_promoted=False,
                caller_authored_url_used=False,
                arbitrary_code_generation_performed=False,
            ),
            "scientific_status_changed": False,
            "positive_scientific_closeout_established": False,
            "global_evidence_unavailability_claimed": False,
            "third_capability_candidate_discovered": True,
            "third_capability_candidate_promoted": True,
            "third_capability_verification_sha256": verification3[
                "capability_verification_sha256_without_self_field"
            ],
            "third_promoted_capability_registry_sha256": registry3[
                "capability_registry_sha256_without_self_field"
            ],
            "third_research_action_resumed": True,
            "derived_candidate_acquisition_executed": True,
            "derived_candidate_acquisition_sha256": acquisition[
                "report_sha256_without_self_field"
            ],
            "calibration_candidate_bridge_assessment_sha256": assessment[
                "report_sha256_without_self_field"
            ],
            "calibration_methodology_established": _mapping(
                assessment.get("evidence_scope"), label="cycle-10 assessment evidence scope"
            ).get("digital_camera_in_situ_calibration_methodology_established"),
            "exact_mds2_experiment_identity_established": False,
            "exact_machine_setting_to_calibrated_power_relation_established": False,
            "bridge_established": False,
            "directly_comparable_mds2_rows": 0,
            "direct_numerical_cross_source_validation_authorized": False,
            "issue_76_exact_target_cells_satisfied": 0,
            "fourth_capability_gap_emitted": True,
            "fourth_capability_candidate_discovered": True,
            "fourth_capability_candidate_sha256": candidate4[
                "capability_candidate_sha256_without_self_field"
            ],
            "fourth_capability_candidate_promoted": False,
            "fourth_research_action_resumed": False,
            "generated_next_action_class": next_action_class,
            "final_blocker": "experiment_identity_reference_chain_candidate_unverified",
        }
    )
    expected["manifest_sha256"] = _canonical_sha(expected)
    cycle11 = _mapping(cycles[10], label="cycle 11")
    _require(
        cycle11.get("predecessor_manifest_sha256") == expected["manifest_sha256"],
        "cycle 11 predecessor manifest digest drifted from canonical ten-cycle reconstruction",
    )
    return expected


def _verify_derived_reauthentication(
    root: Path,
    manifest: Mapping[str, Any],
    replay: Mapping[int, Mapping[str, Any]],
) -> None:
    cycles = manifest.get("cycles")
    _require(isinstance(cycles, list), "autonomous production cycles must be a list")
    if len(cycles) < 11:
        return
    predecessor8 = _reconstruct_cycle8_predecessor(root, manifest, replay)
    predecessor10 = _reconstruct_cycle10_predecessor(root, manifest, replay, predecessor8)
    resolution4 = _merge_gate._load(root, "capability-resolution-4.json")
    candidate4 = _merge_gate._load(root, "capability-candidate-4.json")
    spec4 = _merge_gate._load(root, "capability-specification-4.json")
    expected = _reference_extension._authenticate_predecessor_candidate(
        predecessor_resolution=resolution4,
        predecessor_candidate=candidate4,
        capability_specification=spec4,
        predecessor_manifest_sha256=predecessor10["manifest_sha256"],
    )
    persisted = _merge_gate._load(root, "capability-resolution-4-derived.json")
    _require_json_equal(
        persisted,
        expected,
        "derived predecessor-candidate reauthentication receipt drifted from canonical replay",
    )
    cycle11 = _mapping(cycles[10], label="cycle 11")
    _require(
        cycle11.get("resolution_status") == expected.get("resolution_status")
        and cycle11.get("capability_candidate_sha256")
        == expected.get("capability_candidate_sha256")
        and cycle11.get("predecessor_manifest_sha256")
        == expected.get("predecessor_manifest_sha256")
        and cycle11.get("predecessor_candidate_reauthenticated") is True
        and cycle11.get("candidate_rediscovery_performed") is False,
        "cycle 11 projection drifted from canonical predecessor reauthentication",
    )


def _find_request_by_sha(root: Path, expected_sha: object) -> Path:
    _require(isinstance(expected_sha, str) and len(expected_sha) == 64, "cycle-1 typed request SHA is missing")
    request_root = root / "machine-authored-request"
    _require(request_root.is_dir(), "cycle-1 machine-authored request directory is missing")
    matches = [path for path in request_root.rglob("*.json") if path.is_file() and _sha256_file(path) == expected_sha]
    _require(len(matches) == 1, "cycle-1 exact typed request could not be located uniquely")
    return matches[0]


def _load_plain_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AutonomousProductionFreshReviewRound11Error(f"{label} must be valid UTF-8 JSON") from exc
    _require(isinstance(value, dict), f"{label} root must be an object")
    return value


def _verify_cycle1_authority_artifacts(root: Path, manifest: Mapping[str, Any]) -> None:
    cycles = manifest.get("cycles")
    _require(isinstance(cycles, list) and cycles, "autonomous production cycle 1 is missing")
    cycle1 = _mapping(cycles[0], label="cycle 1")
    repository_root, _mission_path, _mission_sha = _round7._trusted_mission_binding()
    source_config_path = (repository_root / _SOURCE_CONFIG_PATH).resolve(strict=True)
    registry_path = (repository_root / _ACTION_REGISTRY_PATH).resolve(strict=True)
    source_config_bytes = source_config_path.read_bytes()
    source_config = _load_plain_json(source_config_path, label="tracked IN625 source config")
    zenodo = _mapping(source_config.get("zenodo"), label="tracked IN625 source config zenodo")
    readme_name = zenodo.get("readme_file")
    _require(isinstance(readme_name, str) and bool(readme_name), "tracked IN625 README name is missing")
    metadata_path = root / "record.json"
    readme_path = root / readme_name
    _require(metadata_path.is_file(), "cycle-1 retained Zenodo metadata is missing")
    _require(readme_path.is_file(), "cycle-1 retained Zenodo README bytes are missing")
    try:
        expected_authorization = build_in625_archive_network_authorization(
            config=source_config,
            config_bytes=source_config_bytes,
            metadata_bytes=metadata_path.read_bytes(),
            readme_bytes=readme_path.read_bytes(),
        )
    except (In625ArchiveNetworkAcquisitionError, OSError) as exc:
        raise AutonomousProductionFreshReviewRound11Error(
            f"cycle-1 network authorization replay failed: {exc}"
        ) from exc
    persisted_authorization = _merge_gate._load(root, "network-authorization.json")
    _require_json_equal(
        persisted_authorization,
        expected_authorization,
        "cycle-1 network authorization drifted from retained/tracked source replay",
    )
    _require(
        cycle1.get("network_authorization_sha256")
        == expected_authorization.get("authorization_sha256"),
        "cycle-1 network authorization digest binding drifted",
    )

    request_path = _find_request_by_sha(root, cycle1.get("typed_request_sha256"))
    request = _load_plain_json(request_path, label="cycle-1 typed execution request")
    _require(
        set(request) == _execution_verifier._REQUEST_KEYS,
        "cycle-1 typed execution request field set drifted",
    )
    registry = load_action_registry(registry_path, repository_root=repository_root)
    files = _mapping(zenodo.get("files"), label="tracked IN625 file policy")
    archive_name = zenodo.get("archive_file")
    archive_policy = _mapping(files.get(archive_name), label="tracked IN625 archive policy")
    expected_archive_sha = archive_policy.get("verified_sha256")
    _require(
        request.get("schema_version") == "1.0"
        and request.get("action_type") == ACTION_TYPE
        and request.get("action_version") == ACTION_VERSION
        and request.get("expected_source_config_sha256") == hashlib.sha256(source_config_bytes).hexdigest()
        and request.get("expected_archive_sha256") == expected_archive_sha
        and request.get("expected_registry_sha256") == registry.get("registry_sha256"),
        "cycle-1 typed request authority pins drifted",
    )
    _safe_historical_suffix(
        request.get("source_config"),
        suffix=tuple(PurePosixPath(_SOURCE_CONFIG_PATH).parts),
        label="cycle-1 request source_config",
    )
    _safe_historical_suffix(
        request.get("registry"),
        suffix=tuple(PurePosixPath(_ACTION_REGISTRY_PATH).parts),
        label="cycle-1 request registry",
    )
    _safe_historical_suffix(
        request.get("archive_path"),
        suffix=("outputs", "autonomous-in625-production", str(archive_name)),
        label="cycle-1 request archive_path",
    )
    _safe_historical_suffix(
        request.get("research_run"),
        suffix=("outputs", "autonomous-in625-production", "typed-research-run"),
        label="cycle-1 request research_run",
    )

    archive_manifest = _merge_gate._load(root, "archive-manifest.json")
    selected = archive_manifest.get("selected_tabular_files")
    _require(isinstance(selected, list), "cycle-1 archive manifest selected files are malformed")
    numerical = 0
    for raw in selected:
        item = _mapping(raw, label="cycle-1 selected archive member")
        path = item.get("path")
        _require(isinstance(path, str), "cycle-1 selected archive path is malformed")
        if PurePosixPath(path).suffix.lower() in {".dat", ".xlsx", ".xls", ".csv", ".tsv"}:
            numerical += 1
    _require(numerical > 0, "cycle-1 archive manifest exposes no numerical candidate")
    expected_handoff = {
        "schema_version": "1.0",
        "adapter_id": _execution_verifier.ADAPTER_ID,
        "action_type": ACTION_TYPE,
        "action_version": ACTION_VERSION,
        "request_sha256": cycle1["typed_request_sha256"],
        "research_ledger_sha256": cycle1["pre_execution_ledger_sha256"],
        "registry_sha256": registry["registry_sha256"],
        "source_config_sha256": hashlib.sha256(source_config_bytes).hexdigest(),
        "archive_sha256": expected_archive_sha,
        "archive_manifest_sha256": archive_manifest["manifest_sha256"],
        "numerical_candidate_count": numerical,
        "authorization_granted": False,
        "execution_performed": False,
        "source_provenance_verified": True,
        "direct_condition_comparability_established": False,
        "scientific_status_upgrade_authorized": False,
    }
    persisted_handoff = _merge_gate._load(root, "typed-execution-handoff.json")
    _require_json_equal(
        persisted_handoff,
        expected_handoff,
        "cycle-1 typed execution handoff drifted from independent reconstruction",
    )

    research_run = root / "typed-research-run"
    _require(research_run.is_dir(), "cycle-1 retained typed research run is missing")
    try:
        canonical_state = load_research_state(research_run)
    except (ResearchLoopError, OSError) as exc:
        raise AutonomousProductionFreshReviewRound11Error(
            f"cycle-1 retained research state could not be reconstructed: {exc}"
        ) from exc
    persisted_state = _merge_gate._load(root, "typed-research-state.json")
    _require_json_equal(
        persisted_state,
        canonical_state,
        "cycle-1 typed research state drifted from retained ledger replay",
    )
    _require(
        canonical_state.get("ledger_sha256") == cycle1.get("post_execution_ledger_sha256"),
        "cycle-1 post-execution ledger binding drifted",
    )
    actions = canonical_state.get("actions")
    _require(isinstance(actions, list) and len(actions) == 1, "cycle-1 research state action count drifted")
    action = _mapping(actions[0], label="cycle-1 research action")
    _require(
        action.get("action_type") == ACTION_TYPE
        and action.get("status") == "completed"
        and type(action.get("cost_units")) is int
        and action.get("cost_units") == COST_UNITS,
        "cycle-1 research action semantics drifted",
    )

    persisted_execution = _merge_gate._load(root, "typed-execution-result.json")
    expected_execution_keys = {
        "schema_version", "execution_policy_version", "adapter_id", "action_type",
        "action_version", "request_binding", "authorization_status", "execution_registry",
        "execution_status", "ledger_action_id", "action_report", "verified_report",
        "actions_before", "actions_after", "maximum_actions_executed_per_invocation",
        "action_executed", "transaction_recovered", "transaction_recovery_stage",
        "state_snapshot_repaired", "output_ledger_transaction", "explicit_execution_request_used",
        "verifier_request_sha256_handoff_pinned", "verifier_research_ledger_sha256_handoff_pinned",
        "generic_command_execution_available", "network_access_initiated_by_typed_action",
        "real_external_archive_consumed", "physical_experiment_execution_initiated",
        "direct_condition_comparability_established", "empirical_model_validation_established",
        "scientific_evidence_upgraded_by_orchestrator", "scientific_boundary", "request_sha256",
    }
    _require(
        set(persisted_execution) == expected_execution_keys,
        "cycle-1 typed execution result field set drifted",
    )
    request_binding = _mapping(
        persisted_execution.get("request_binding"), label="cycle-1 execution request binding"
    )
    _require(
        set(request_binding) == {"path", "sha256", "size_bytes"}
        and request_binding.get("sha256") == cycle1.get("typed_request_sha256")
        and type(request_binding.get("size_bytes")) is int
        and request_binding.get("size_bytes") == request_path.stat().st_size,
        "cycle-1 execution request binding drifted",
    )
    _safe_historical_suffix(
        request_binding.get("path"),
        suffix=tuple(request_path.relative_to(root).parts),
        label="cycle-1 execution request historical path",
    )
    execution_registry = _mapping(
        persisted_execution.get("execution_registry"), label="cycle-1 execution registry"
    )
    _require(
        set(execution_registry) == {"registry_id", "registry_sha256", "registry_path"}
        and execution_registry.get("registry_id") == registry.get("registry_id")
        and execution_registry.get("registry_sha256") == registry.get("registry_sha256"),
        "cycle-1 execution registry binding drifted",
    )
    _safe_historical_suffix(
        execution_registry.get("registry_path"),
        suffix=tuple(PurePosixPath(_ACTION_REGISTRY_PATH).parts),
        label="cycle-1 execution registry historical path",
    )
    action_id = action.get("action_id")
    _require(isinstance(action_id, str) and bool(action_id), "cycle-1 action id is missing")
    _safe_historical_suffix(
        persisted_execution.get("action_report"),
        suffix=("outputs", "autonomous-in625-production", "typed-research-run", "actions", action_id, "action_result.json"),
        label="cycle-1 action report historical path",
    )
    expected_verified_report = {
        "schema_version": "1.0",
        "action_id": action_id,
        "action_type": ACTION_TYPE,
        "action_version": ACTION_VERSION,
        "registered_outcome": "verified_external_source_archive_registered",
        "request_sha256": cycle1["typed_request_sha256"],
        "archive_sha256": expected_archive_sha,
        "archive_manifest_sha256": archive_manifest["manifest_sha256"],
        "numerical_candidate_count": numerical,
        "source_provenance_verified": True,
        "direct_condition_comparability_established": False,
        "empirical_model_validation_established": False,
        "scientific_status_changed": False,
    }
    _require_json_equal(
        persisted_execution.get("verified_report"),
        expected_verified_report,
        "cycle-1 execution verified report drifted from retained/tracked provenance",
    )
    expected_scalars = {
        "schema_version": "1.0",
        "execution_policy_version": "1.8+in625-external-evidence-1.0",
        "adapter_id": _execution_verifier.ADAPTER_ID,
        "action_type": ACTION_TYPE,
        "action_version": ACTION_VERSION,
        "authorization_status": "ready_for_explicit_execution_request",
        "execution_status": "completed_or_structured_rejection",
        "ledger_action_id": action_id,
        "actions_before": 0,
        "actions_after": 1,
        "maximum_actions_executed_per_invocation": 1,
        "action_executed": True,
        "transaction_recovered": False,
        "transaction_recovery_stage": None,
        "state_snapshot_repaired": False,
        "output_ledger_transaction": "cleaned",
        "explicit_execution_request_used": True,
        "verifier_request_sha256_handoff_pinned": True,
        "verifier_research_ledger_sha256_handoff_pinned": True,
        "generic_command_execution_available": False,
        "network_access_initiated_by_typed_action": False,
        "real_external_archive_consumed": True,
        "physical_experiment_execution_initiated": False,
        "direct_condition_comparability_established": False,
        "empirical_model_validation_established": False,
        "scientific_evidence_upgraded_by_orchestrator": False,
        "request_sha256": cycle1["typed_request_sha256"],
    }
    for key, expected_value in expected_scalars.items():
        actual = persisted_execution.get(key)
        if type(expected_value) is int:
            _strict_int(actual, expected=expected_value, label=f"cycle-1 execution {key}")
        else:
            _require(actual is expected_value if isinstance(expected_value, bool) or expected_value is None else actual == expected_value,
                     f"cycle-1 execution {key} drifted")
    boundary = persisted_execution.get("scientific_boundary")
    _require(
        isinstance(boundary, str)
        and "does not establish measurement semantics" in boundary
        and "hypothesis truth" in boundary
        and "positive scientific closeout" in boundary,
        "cycle-1 execution scientific boundary text drifted",
    )


def verify_fresh_review_round11_boundaries(output_root: str | Path) -> None:
    """Apply final stage-aware, type-sensitive provenance closure."""
    root = Path(output_root).expanduser().resolve(strict=True)
    manifest = _merge_gate._load(root, "autonomous-production-manifest.json")
    cycles = manifest.get("cycles")
    _require(isinstance(cycles, list) and cycles, "autonomous production cycles must be a non-empty list")

    _verify_cycle1_authority_artifacts(root, manifest)
    _verify_cycle6_execution_boundary(root, manifest)
    replay = _strict_replay_promotions(root, manifest)
    if len(cycles) >= 10:
        predecessor8 = _reconstruct_cycle8_predecessor(root, manifest, replay)
        if len(cycles) >= 11:
            _reconstruct_cycle10_predecessor(root, manifest, replay, predecessor8)
            _verify_derived_reauthentication(root, manifest, replay)


__all__ = [
    "AutonomousProductionFreshReviewRound11Error",
    "verify_fresh_review_round11_boundaries",
]
