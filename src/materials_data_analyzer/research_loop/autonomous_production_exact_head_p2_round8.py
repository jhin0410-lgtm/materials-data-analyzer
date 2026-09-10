"""Bind mutable capability-smoke replay bytes to independently pinned live source versions.

Round 7 proves that persisted capability artifacts are reproduced by the trusted candidate factory
and authoritative verifier.  A retained replay packet is still only self-consistent, however: a
producer regression could replace a mutable network response, recompute every local hash, and then
obtain the same trusted-verifier replay over the forged bytes.

Promotion 1 already closes that gap with an exact static NIST PDF witness, and promotion 4's Naderi
adapter enforces its own exact source SHA-256/size.  This gate closes the remaining production
promotions 2 and 3 by pinning the exact source versions observed in the independently retained
GitHub Actions live artifact from run 34430156288 (artifact 10134264310, digest
sha256:b895422a03bf1eedb3009695fa177e3fceae61f15d722970515a7ff383df0a9b).

The NIST CMS HTML resources are mutable.  Therefore these pins are explicit source-version
witnesses, not claims that the resources are immutable.  Any future drift must fail closed and be
reviewed as a new source version instead of silently redefining historical verification.
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple

from . import autonomous_production_exact_head_p2_round6 as _round6
from . import autonomous_production_exact_head_p2_round7 as _round7
from . import autonomous_production_merge_gate_hardening as _merge_gate
from . import capability_smoke_replay_evidence as _smoke_replay
from . import nist_ammt_candidate_acquisition_policy as _candidate_policy
from . import nist_ammt_source_discovery_policy as _discovery_policy

AutonomousProductionExactHeadRound8Error = (
    _merge_gate.AutonomousProductionMergeGateHardeningError
)

WITNESS_ORIGIN_RUN_ID = 34_430_156_288
WITNESS_ORIGIN_ARTIFACT_ID = 10_134_264_310
WITNESS_ORIGIN_ARTIFACT_DIGEST = (
    "sha256:b895422a03bf1eedb3009695fa177e3fceae61f15d722970515a7ff383df0a9b"
)


class SourceVersionWitness(NamedTuple):
    """Exact request contract plus independently pinned response version."""

    requested_url: str
    allowed_hosts: tuple[str, ...]
    max_bytes: int
    timeout_seconds: int
    final_url: str
    source_sha256: str
    source_size_bytes: int


DISCOVERY_SOURCE_WITNESSES: tuple[SourceVersionWitness, ...] = (
    SourceVersionWitness(
        requested_url=_discovery_policy.SOURCE_URL,
        allowed_hosts=_discovery_policy.ALLOWED_HOSTS,
        max_bytes=min(
            _discovery_policy.MAX_SOURCE_BYTES,
            _discovery_policy.MAX_TOTAL_BYTES,
        ),
        timeout_seconds=_discovery_policy.TIMEOUT_SECONDS,
        final_url=_discovery_policy.SOURCE_URL,
        source_sha256="179235d723ea91905d8f6e6ce573545cfcf1f92be4a3ea4d9358c8feac46be4c",
        source_size_bytes=98_790,
    ),
)

_CANDIDATE_PAGE_URL = (
    "https://www.nist.gov/publications/"
    "laser-calibration-powder-bed-fusion-additive-manufacturing-process"
)
_CANDIDATE_FULL_TEXT_URL = (
    "https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=935350"
)
_CANDIDATE_PAGE_SIZE_BYTES = 82_335

CANDIDATE_SOURCE_WITNESSES: tuple[SourceVersionWitness, ...] = (
    SourceVersionWitness(
        requested_url=_CANDIDATE_PAGE_URL,
        allowed_hosts=_candidate_policy.CANDIDATE_PAGE_ALLOWED_HOSTS,
        max_bytes=_candidate_policy.MAX_CANDIDATE_PAGE_BYTES,
        timeout_seconds=_candidate_policy.TIMEOUT_SECONDS,
        final_url=_CANDIDATE_PAGE_URL,
        source_sha256="4443eebf40ebcb03c32f3af9ae031165141fe4bf19d9214a474acc88cc1584f9",
        source_size_bytes=_CANDIDATE_PAGE_SIZE_BYTES,
    ),
    SourceVersionWitness(
        requested_url=_CANDIDATE_FULL_TEXT_URL,
        allowed_hosts=_candidate_policy.FULL_TEXT_ALLOWED_HOSTS,
        max_bytes=min(
            _candidate_policy.MAX_FULL_TEXT_BYTES,
            _candidate_policy.MAX_TOTAL_BYTES - _CANDIDATE_PAGE_SIZE_BYTES,
        ),
        timeout_seconds=_candidate_policy.TIMEOUT_SECONDS,
        final_url=_CANDIDATE_FULL_TEXT_URL,
        source_sha256="76a95c1ce41240db355752cd537cca66467999e20b260e263a4e83af19f1b8d7",
        source_size_bytes=2_264_822,
    ),
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionExactHeadRound8Error(message)


def verify_retained_source_witness(
    evidence: Mapping[str, Any],
    *,
    action_class: str,
    capability_specification_sha256: str,
    capability_candidate_sha256: str,
    mission_sha256: str,
    expected_records: Sequence[SourceVersionWitness],
    label: str,
) -> None:
    """Reject locally valid replay packets whose response bytes are not externally pinned."""

    _require(bool(expected_records), f"{label} source-version witness set is empty")
    try:
        fetcher, _context = _smoke_replay.authenticate_smoke_replay_evidence(
            evidence,
            action_class=action_class,
            capability_specification_sha256=capability_specification_sha256,
            capability_candidate_sha256=capability_candidate_sha256,
            mission_sha256=mission_sha256,
        )
        for index, witness in enumerate(expected_records, start=1):
            fetched = fetcher(
                witness.requested_url,
                allowed_hosts=witness.allowed_hosts,
                max_bytes=witness.max_bytes,
                timeout_seconds=witness.timeout_seconds,
            )
            _require(
                fetched.final_url == witness.final_url,
                f"{label} source {index} final URL drifted from pinned live witness",
            )
            _require(
                len(fetched.body) == witness.source_size_bytes,
                f"{label} source {index} size drifted from pinned live witness",
            )
            _require(
                hashlib.sha256(fetched.body).hexdigest() == witness.source_sha256,
                f"{label} source {index} SHA-256 drifted from pinned live witness",
            )
        fetcher.assert_consumed()
    except _smoke_replay.CapabilitySmokeReplayEvidenceError as exc:
        raise AutonomousProductionExactHeadRound8Error(
            f"{label} retained source-version replay failed: {exc}"
        ) from exc


def _verify_promotion_source_versions(
    *,
    root: Path,
    step: int,
    expected_records: Sequence[SourceVersionWitness],
) -> None:
    suffix, action_class, _implementation_id, _cycle_index, _manifest_field = (
        _round6._PROMOTIONS[step - 1]
    )
    specification = _merge_gate._load(
        root,
        _round6._name("capability-specification", suffix),
    )
    specification_sha = _merge_gate._verify_self_hash(
        specification,
        "capability_specification_sha256_without_self_field",
        label=f"capability promotion {step} specification",
    )
    candidate = _merge_gate._load(
        root,
        _round6._name("capability-candidate", suffix),
    )
    candidate_sha = _merge_gate._verify_self_hash(
        candidate,
        "capability_candidate_sha256_without_self_field",
        label=f"capability promotion {step} candidate",
    )
    verification = _merge_gate._load(
        root,
        _round6._name("capability-verification", suffix),
    )
    _merge_gate._verify_self_hash(
        verification,
        "capability_verification_sha256_without_self_field",
        label=f"capability promotion {step} verification",
    )
    evidence = verification.get("real_source_smoke_replay_evidence")
    _require(
        isinstance(evidence, Mapping),
        f"capability promotion {step} retained smoke replay evidence is missing",
    )
    evidence_sha = evidence.get("smoke_replay_evidence_sha256_without_self_field")
    _require(
        isinstance(evidence_sha, str)
        and verification.get("real_source_smoke_replay_evidence_sha256") == evidence_sha,
        f"capability promotion {step} verification/replay-evidence binding drifted",
    )
    _repository_root, _mission_path, mission_sha = _round7._trusted_mission_binding()
    verify_retained_source_witness(
        evidence,
        action_class=action_class,
        capability_specification_sha256=specification_sha,
        capability_candidate_sha256=candidate_sha,
        mission_sha256=mission_sha,
        expected_records=expected_records,
        label=f"capability promotion {step}",
    )


def verify_exact_head_round8_boundaries(output_root: str | Path) -> None:
    """Bind reached promotion-2/3 network smoke packets to exact reviewed source versions."""

    root = Path(output_root).expanduser().resolve(strict=True)
    manifest = _merge_gate._load(root, "autonomous-production-manifest.json")
    cycles = manifest.get("cycles")
    _require(isinstance(cycles, list), "autonomous production cycles must be a list")

    if len(cycles) >= _round6._PROMOTIONS[1][3]:
        _verify_promotion_source_versions(
            root=root,
            step=2,
            expected_records=DISCOVERY_SOURCE_WITNESSES,
        )
    if len(cycles) >= _round6._PROMOTIONS[2][3]:
        _verify_promotion_source_versions(
            root=root,
            step=3,
            expected_records=CANDIDATE_SOURCE_WITNESSES,
        )


__all__ = [
    "AutonomousProductionExactHeadRound8Error",
    "CANDIDATE_SOURCE_WITNESSES",
    "DISCOVERY_SOURCE_WITNESSES",
    "SourceVersionWitness",
    "WITNESS_ORIGIN_ARTIFACT_DIGEST",
    "WITNESS_ORIGIN_ARTIFACT_ID",
    "WITNESS_ORIGIN_RUN_ID",
    "verify_exact_head_round8_boundaries",
    "verify_retained_source_witness",
]
