"""Fresh-review closure for derived artifacts that must not self-authorize.

This layer closes four remaining provenance gaps on the accepted full-success path:

* rebuild the geometry/condition mapping from canonically replayed NIST and multisource evidence;
* compare every reached pre-promotion resolver artifact with the canonical finite-factory replay;
* rebuild the derived NIST candidate authorization from trusted policy/discovery/manifest context; and
* rebuild the calibration-candidate bridge assessment from the bound acquisition and predecessor.

No new scientific interpretation is introduced here.  The authoritative producer functions are
re-executed from already authenticated inputs, and persisted outputs must match exactly.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from . import autonomous_production_exact_head_p2_round6 as _round6
from . import autonomous_production_exact_head_p2_round7 as _round7
from . import autonomous_production_merge_gate_hardening as _merge_gate
from . import autonomous_production_source_replay_hardening as _source_replay
from . import autonomous_production_trusted_replay_artifact_binding as _trusted_binding
from . import nist_ammt_calibration_candidate_acquisition as _candidate_acquisition
from . import nist_ammt_calibration_candidate_bridge_assessment as _bridge_assessment
from .autonomous_production_multisource_reviewed_witness import (
    AutonomousProductionMultisourceReviewedWitnessError,
    verify_multisource_acquisition_against_reviewed_witness,
)
from .capability_registry import CapabilityRegistryError, promote_verified_capability
from .capability_resolver import CapabilityResolverError, resolve_or_discover_capability
from .in625_geometry_condition_mapping_assessment import (
    GeometryConditionMappingAssessmentError,
    build_geometry_condition_mapping_assessment,
)
from .nist_ammt_candidate_acquisition_policy import (
    NistAmmtCandidateAcquisitionPolicyError,
    authenticate_nist_ammt_candidate_acquisition_policy,
)

AutonomousProductionFreshReviewRound10Error = (
    _merge_gate.AutonomousProductionMergeGateHardeningError
)

_TARGET_PROCESS_PATH = "data/case_studies/nist_ambench_2018_02/source_process_conditions.csv"
_TARGET_RESPONSE_PATH = "data/case_studies/nist_ambench_2018_02/source_melt_pool_measurements.csv"
_RESOLUTION_ARTIFACTS = (
    "capability-resolution.json",
    "capability-resolution-2.json",
    "capability-resolution-3-derived.json",
    "capability-resolution-4.json",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionFreshReviewRound10Error(message)


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    return value


def _verify_geometry_mapping(root: Path, manifest: Mapping[str, Any]) -> None:
    cycles_value = manifest.get("cycles")
    _require(isinstance(cycles_value, list), "autonomous production cycles must be a list")
    if len(cycles_value) < 4:
        return

    # Re-run the existing canonical source-byte replay first so the inputs below are not merely
    # attacker-rehashable JSON artifacts.
    try:
        _source_replay.verify_source_replay_boundaries(root)
    except (ValueError, OSError) as exc:
        raise AutonomousProductionFreshReviewRound10Error(
            f"geometry mapping input source replay failed: {exc}"
        ) from exc

    nist_intake = _merge_gate._load(root, "nist-scientific-intake.json")
    _merge_gate._verify_self_hash(
        nist_intake,
        "report_sha256_without_self_field",
        label="geometry mapping NIST intake",
    )
    multisource = _merge_gate._load(root, "multisource-source-acquisition.json")
    multisource_sha = _merge_gate._verify_self_hash(
        multisource,
        "report_sha256_without_self_field",
        label="geometry mapping multisource evidence",
    )
    try:
        verify_multisource_acquisition_against_reviewed_witness(multisource)
    except AutonomousProductionMultisourceReviewedWitnessError as exc:
        raise AutonomousProductionFreshReviewRound10Error(
            f"geometry mapping multisource witness replay failed: {exc}"
        ) from exc

    repository_root = _merge_gate._trusted_repository_root().resolve(strict=True)
    process_path = (repository_root / _TARGET_PROCESS_PATH).resolve(strict=True)
    response_path = (repository_root / _TARGET_RESPONSE_PATH).resolve(strict=True)
    try:
        process_path.relative_to(repository_root)
        response_path.relative_to(repository_root)
    except ValueError as exc:
        raise AutonomousProductionFreshReviewRound10Error(
            "geometry mapping tracked target escaped trusted checkout"
        ) from exc
    try:
        expected = build_geometry_condition_mapping_assessment(
            nist_intake=nist_intake,
            multisource_evidence=multisource,
            target_process_bytes=process_path.read_bytes(),
            target_response_bytes=response_path.read_bytes(),
        )
    except (GeometryConditionMappingAssessmentError, OSError) as exc:
        raise AutonomousProductionFreshReviewRound10Error(
            f"geometry mapping canonical replay failed: {exc}"
        ) from exc
    persisted = _merge_gate._load(root, "geometry-condition-mapping-assessment.json")
    _require(
        persisted == expected,
        "geometry-condition mapping drifted from canonical authenticated-input replay",
    )
    mapping_sha = expected["report_sha256_without_self_field"]
    cycle4 = _mapping(cycles_value[3], label="cycle 4")
    _require(
        cycle4.get("mapping_assessment_sha256") == mapping_sha
        and cycle4.get("source_acquisition_report_sha256") == multisource_sha,
        "cycle 4 geometry/multisource bindings drifted from canonical replay",
    )
    _require(
        manifest.get("geometry_condition_mapping_assessment_sha256") == mapping_sha
        and manifest.get("multisource_condition_source_acquisition_sha256") == multisource_sha,
        "manifest geometry/multisource bindings drifted from canonical replay",
    )


def _replay_promotions_and_resolutions(
    root: Path,
    manifest: Mapping[str, Any],
) -> dict[int, dict[str, Any]]:
    cycles_value = manifest.get("cycles")
    _require(isinstance(cycles_value, list), "autonomous production cycles must be a list")
    cycles = [
        _mapping(value, label=f"cycle {index}")
        for index, value in enumerate(cycles_value, start=1)
    ]
    if len(cycles) < 5:
        return {}

    expected_registry = _round6.build_initial_capability_registry(
        verified_action_classes=_round6._INITIAL_VERIFIED_ACTIONS,
    )
    persisted_initial = _merge_gate._load(root, "capability-registry-initial.json")
    _require(
        persisted_initial == expected_registry,
        "initial capability registry drifted before resolver replay",
    )
    replay: dict[int, dict[str, Any]] = {}

    for step, promotion in enumerate(_round6._PROMOTIONS, start=1):
        suffix, action_class, implementation_id, promotion_cycle_index, manifest_field = promotion
        # The bounded candidate resolution is produced one cycle before promotion.
        if len(cycles) < promotion_cycle_index - 1:
            break
        _gap, specification, predecessor = _round7._canonical_gap_and_specification(
            root=root,
            step=step,
            action_class=action_class,
            registry=expected_registry,
            suffix=suffix,
        )
        primitives = _round7._TRUSTED_PRIMITIVES.get(action_class)
        _require(
            primitives is not None,
            f"capability promotion {step} has no trusted primitive contract",
        )
        try:
            expected_resolution = resolve_or_discover_capability(
                registry=expected_registry,
                capability_specification=specification,
                available_verified_primitives=primitives,
            )
        except (CapabilityRegistryError, CapabilityResolverError) as exc:
            raise AutonomousProductionFreshReviewRound10Error(
                f"capability promotion {step} resolver replay failed: {exc}"
            ) from exc
        persisted_resolution = _merge_gate._load(
            root, _RESOLUTION_ARTIFACTS[step - 1]
        )
        _require(
            persisted_resolution == expected_resolution,
            f"capability promotion {step} persisted resolver output drifted from canonical replay",
        )
        candidate = _mapping(
            expected_resolution.get("candidate"),
            label=f"capability promotion {step} canonical resolver candidate",
        )
        persisted_candidate = _merge_gate._load(
            root, _round6._name("capability-candidate", suffix)
        )
        _require(
            candidate.get("implementation_id") == implementation_id
            and dict(candidate) == persisted_candidate,
            f"capability promotion {step} canonical resolver candidate drifted",
        )
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
        try:
            successor = promote_verified_capability(
                registry=expected_registry,
                candidate=replayed_candidate,
                verification_receipt=replayed_verification,
            )
        except CapabilityRegistryError as exc:
            raise AutonomousProductionFreshReviewRound10Error(
                f"capability promotion {step} canonical registry promotion failed: {exc}"
            ) from exc
        persisted_successor = _merge_gate._load(
            root, _round6._name("capability-registry-promoted", suffix)
        )
        _require(
            persisted_successor == successor,
            f"capability promotion {step} successor registry drifted during resolver replay",
        )
        replay[step] = {
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


def _trusted_step3_context(
    *,
    root: Path,
    manifest: Mapping[str, Any],
    replay: Mapping[int, Mapping[str, Any]],
) -> Mapping[str, Any]:
    step = replay.get(3)
    _require(isinstance(step, Mapping), "promotion-3 trusted replay state is missing")
    cycles_value = manifest.get("cycles")
    _require(isinstance(cycles_value, list), "autonomous production cycles must be a list")
    cycles = [
        _mapping(value, label=f"cycle {index}")
        for index, value in enumerate(cycles_value, start=1)
    ]
    _repository_root, _mission_path, mission_sha = _round7._trusted_mission_binding()
    persisted_verification = _mapping(
        step.get("verification"), label="promotion-3 trusted verification"
    )
    evidence = persisted_verification.get("real_source_smoke_replay_evidence")
    _require(
        isinstance(evidence, Mapping),
        "promotion-3 retained smoke replay evidence is missing",
    )
    try:
        _unused_fetcher, context = _round7._smoke_replay.authenticate_smoke_replay_evidence(
            evidence,
            action_class=_candidate_acquisition.ACTION_CLASS,
            capability_specification_sha256=str(
                _mapping(step.get("specification"), label="promotion-3 specification").get(
                    "capability_specification_sha256_without_self_field"
                )
            ),
            capability_candidate_sha256=str(
                _mapping(step.get("candidate"), label="promotion-3 candidate").get(
                    "capability_candidate_sha256_without_self_field"
                )
            ),
            mission_sha256=mission_sha,
        )
    except _round7._smoke_replay.CapabilitySmokeReplayEvidenceError as exc:
        raise AutonomousProductionFreshReviewRound10Error(
            f"promotion-3 retained context authentication failed: {exc}"
        ) from exc
    _require(isinstance(context, Mapping), "promotion-3 retained verifier context is missing")
    retained_discovery = context.get("discovery_report")
    retained_manifest = context.get("predecessor_manifest")
    predecessor = _mapping(step.get("predecessor"), label="promotion-3 predecessor")
    _require(
        isinstance(retained_discovery, Mapping)
        and dict(retained_discovery) == dict(predecessor),
        "promotion-3 retained discovery report drifted from authenticated predecessor",
    )
    _require(
        isinstance(retained_manifest, Mapping),
        "promotion-3 retained predecessor manifest is missing",
    )
    retained_cycles = retained_manifest.get("cycles")
    _require(
        isinstance(retained_cycles, list)
        and len(retained_cycles) == 8
        and [dict(item) for item in retained_cycles if isinstance(item, Mapping)]
        == [dict(item) for item in cycles[:8]],
        "promotion-3 retained predecessor manifest cycle snapshot drifted",
    )
    return context


def _verify_derived_authorization_and_bridge_assessment(
    root: Path,
    manifest: Mapping[str, Any],
    replay: Mapping[int, Mapping[str, Any]],
) -> None:
    cycles_value = manifest.get("cycles")
    _require(isinstance(cycles_value, list), "autonomous production cycles must be a list")
    if len(cycles_value) < 10:
        return
    context = _trusted_step3_context(root=root, manifest=manifest, replay=replay)
    discovery_report = _mapping(
        context.get("discovery_report"), label="trusted promotion-3 discovery report"
    )
    predecessor_manifest = _mapping(
        context.get("predecessor_manifest"), label="trusted promotion-3 predecessor manifest"
    )
    repository_root, mission_path, mission_sha = _round7._trusted_mission_binding()
    try:
        expected_qualification = authenticate_nist_ammt_candidate_acquisition_policy(
            repository_root=repository_root,
            mission_path=mission_path,
            expected_mission_sha256=mission_sha,
        )
    except (NistAmmtCandidateAcquisitionPolicyError, OSError) as exc:
        raise AutonomousProductionFreshReviewRound10Error(
            f"candidate-acquisition policy replay failed: {exc}"
        ) from exc
    persisted_qualification = _merge_gate._load(
        root, "nist-ammt-candidate-acquisition-policy-qualification.json"
    )
    _require(
        persisted_qualification == expected_qualification,
        "persisted candidate-acquisition qualification drifted from trusted policy replay",
    )
    try:
        expected_authorization = _candidate_acquisition.build_derived_candidate_authorization(
            qualification=expected_qualification,
            discovery_report=discovery_report,
            predecessor_manifest=predecessor_manifest,
        )
    except _candidate_acquisition.NistAmmtCalibrationCandidateAcquisitionError as exc:
        raise AutonomousProductionFreshReviewRound10Error(
            f"derived candidate authorization canonical replay failed: {exc}"
        ) from exc
    persisted_authorization = _merge_gate._load(
        root, "nist-ammt-derived-candidate-authorization.json"
    )
    _require(
        persisted_authorization == expected_authorization,
        "persisted derived candidate authorization drifted from trusted replay",
    )

    # The acquisition itself is already bound to trusted retained replay by the earlier final gate;
    # invoke that binding here before consuming it as assessment input.
    try:
        _trusted_binding.verify_trusted_replay_artifact_bindings(root)
    except (ValueError, OSError) as exc:
        raise AutonomousProductionFreshReviewRound10Error(
            f"candidate acquisition trusted binding failed: {exc}"
        ) from exc
    acquisition = _merge_gate._load(
        root, "nist-ammt-calibration-candidate-acquisition.json"
    )
    acquisition_sha = _merge_gate._verify_self_hash(
        acquisition,
        "report_sha256_without_self_field",
        label="candidate acquisition",
    )
    _require(
        acquisition.get("authorization_sha256")
        == expected_authorization.get("authorization_sha256"),
        "candidate acquisition authorization binding drifted from canonical authorization",
    )
    try:
        expected_assessment = _bridge_assessment.build_calibration_candidate_bridge_assessment(
            acquisition_report=acquisition,
            predecessor_manifest=predecessor_manifest,
        )
    except _bridge_assessment.NistAmmtCalibrationCandidateBridgeAssessmentError as exc:
        raise AutonomousProductionFreshReviewRound10Error(
            f"calibration candidate bridge assessment replay failed: {exc}"
        ) from exc
    persisted_assessment = _merge_gate._load(
        root, "nist-ammt-calibration-candidate-bridge-assessment.json"
    )
    _require(
        persisted_assessment == expected_assessment,
        "calibration candidate bridge assessment drifted from authenticated acquisition replay",
    )
    assessment_sha = expected_assessment["report_sha256_without_self_field"]
    cycle10 = _mapping(cycles_value[9], label="cycle 10")
    _require(
        cycle10.get("output_next_action_class")
        == _mapping(expected_assessment.get("next_action"), label="assessment next action").get(
            "action_class"
        )
        and cycle10.get("new_verified_information")
        is expected_assessment.get("new_verified_information"),
        "cycle 10 calibration-assessment projection drifted from canonical replay",
    )
    _require(
        manifest.get("derived_candidate_acquisition_sha256") == acquisition_sha
        and manifest.get("calibration_candidate_bridge_assessment_sha256") == assessment_sha,
        "manifest candidate-acquisition/assessment bindings drifted from canonical replay",
    )


def verify_fresh_review_round10_boundaries(output_root: str | Path) -> None:
    """Rebuild the remaining derived scientific/governance artifacts from trusted inputs."""
    root = Path(output_root).expanduser().resolve(strict=True)
    manifest = _merge_gate._load(root, "autonomous-production-manifest.json")
    cycles = manifest.get("cycles")
    _require(isinstance(cycles, list), "autonomous production cycles must be a list")
    _verify_geometry_mapping(root, manifest)
    replay = _replay_promotions_and_resolutions(root, manifest)
    _verify_derived_authorization_and_bridge_assessment(root, manifest, replay)


__all__ = [
    "AutonomousProductionFreshReviewRound10Error",
    "verify_fresh_review_round10_boundaries",
]
