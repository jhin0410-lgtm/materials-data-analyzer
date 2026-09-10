"""Bind mutable capability-smoke evidence to independently reviewed authority semantics.

Round 7 proves that persisted capability artifacts are reproduced by trusted candidate factories and
authoritative verifiers. A retained replay packet is still locally self-consistent, however: response
bytes and every downstream hash could be rewritten together.

For immutable/static sources, exact response bytes are the appropriate external witness. For the NIST
CMS HTML used by promotions 2 and 3, they are not: independent live runs (and even repeated requests
inside one run) showed Cloudflare/New Relic runtime bytes changing while the trusted parser's visible
text, ranked discovery candidates, derived full-text URL, and static primary PDF stayed identical.

This gate therefore authenticates the authority-bearing semantic projection of mutable HTML and keeps
an exact-byte witness for the static primary PDF. The witness values originate from the independently
retained GitHub Actions artifact from run 34430156288 (artifact 10134264310, digest
sha256:b895422a03bf1eedb3009695fa177e3fceae61f15d722970515a7ff383df0a9b).

This is deliberately narrower than a generic historical-event attestation. It prevents rewritten
mutable HTML from changing the authority-bearing discovery/acquisition semantics while allowing
provider-injected non-visible runtime noise. Generic external event/source trust remains a separate
architecture concern.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NamedTuple

from . import autonomous_production_exact_head_p2_round6 as _round6
from . import autonomous_production_exact_head_p2_round7 as _round7
from . import autonomous_production_merge_gate_hardening as _merge_gate
from . import capability_smoke_replay_evidence as _smoke_replay
from . import nist_ammt_calibration_candidate_acquisition as _candidate_acquisition
from . import nist_ammt_calibration_source_discovery as _source_discovery
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


class SemanticHtmlWitness(NamedTuple):
    """Exact request contract plus trusted parser semantic projection."""

    requested_url: str
    allowed_hosts: tuple[str, ...]
    max_bytes: int
    timeout_seconds: int
    final_url: str
    visible_text_sha256: str
    visible_text_utf8_bytes: int


class ExactSourceWitness(NamedTuple):
    """Exact request contract plus immutable/static source bytes."""

    requested_url: str
    allowed_hosts: tuple[str, ...]
    max_bytes: int
    timeout_seconds: int
    final_url: str
    source_sha256: str
    source_size_bytes: int


DISCOVERY_HTML_WITNESS = SemanticHtmlWitness(
    requested_url=_discovery_policy.SOURCE_URL,
    allowed_hosts=_discovery_policy.ALLOWED_HOSTS,
    max_bytes=min(
        _discovery_policy.MAX_SOURCE_BYTES,
        _discovery_policy.MAX_TOTAL_BYTES,
    ),
    timeout_seconds=_discovery_policy.TIMEOUT_SECONDS,
    final_url=_discovery_policy.SOURCE_URL,
    visible_text_sha256="f6c5ebe90021efaae19146480b48e40ec8c41de2c5e0aab01cae648a0a786ed7",
    visible_text_utf8_bytes=15_535,
)
DISCOVERY_CANDIDATES_SHA256 = (
    "f915580b047dbd95e5bd47b44aeeefc2e706b439d0e016ff3ce64bbadb0845f8"
)

_CANDIDATE_PAGE_URL = (
    "https://www.nist.gov/publications/"
    "laser-calibration-powder-bed-fusion-additive-manufacturing-process"
)
_CANDIDATE_FULL_TEXT_URL = (
    "https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=935350"
)

CANDIDATE_HTML_WITNESS = SemanticHtmlWitness(
    requested_url=_CANDIDATE_PAGE_URL,
    allowed_hosts=_candidate_policy.CANDIDATE_PAGE_ALLOWED_HOSTS,
    max_bytes=_candidate_policy.MAX_CANDIDATE_PAGE_BYTES,
    timeout_seconds=_candidate_policy.TIMEOUT_SECONDS,
    final_url=_CANDIDATE_PAGE_URL,
    visible_text_sha256="29652d89ebe37d973d351015a3d0ba2b29f3f974dc39cc678e5f9a9205bafddb",
    visible_text_utf8_bytes=4_625,
)
CANDIDATE_FULL_TEXT_WITNESS = ExactSourceWitness(
    requested_url=_CANDIDATE_FULL_TEXT_URL,
    allowed_hosts=_candidate_policy.FULL_TEXT_ALLOWED_HOSTS,
    max_bytes=_candidate_policy.MAX_FULL_TEXT_BYTES,
    timeout_seconds=_candidate_policy.TIMEOUT_SECONDS,
    final_url=_CANDIDATE_FULL_TEXT_URL,
    source_sha256="76a95c1ce41240db355752cd537cca66467999e20b260e263a4e83af19f1b8d7",
    source_size_bytes=2_264_822,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionExactHeadRound8Error(message)


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _visible_text_binding(text: str) -> tuple[str, int]:
    raw = text.encode("utf-8")
    return hashlib.sha256(raw).hexdigest(), len(raw)


def _authenticated_replay_fetcher(
    evidence: Mapping[str, Any],
    *,
    action_class: str,
    capability_specification_sha256: str,
    capability_candidate_sha256: str,
    mission_sha256: str,
    label: str,
):
    try:
        return _smoke_replay.authenticate_smoke_replay_evidence(
            evidence,
            action_class=action_class,
            capability_specification_sha256=capability_specification_sha256,
            capability_candidate_sha256=capability_candidate_sha256,
            mission_sha256=mission_sha256,
        )
    except _smoke_replay.CapabilitySmokeReplayEvidenceError as exc:
        raise AutonomousProductionExactHeadRound8Error(
            f"{label} retained semantic replay failed: {exc}"
        ) from exc


def verify_discovery_semantic_witness(
    evidence: Mapping[str, Any],
    *,
    action_class: str,
    capability_specification_sha256: str,
    capability_candidate_sha256: str,
    mission_sha256: str,
    witness: SemanticHtmlWitness = DISCOVERY_HTML_WITNESS,
    expected_candidates_sha256: str = DISCOVERY_CANDIDATES_SHA256,
    label: str = "capability promotion 2",
) -> None:
    """Authenticate mutable discovery HTML by its trusted authority-bearing projection."""

    fetcher, _context = _authenticated_replay_fetcher(
        evidence,
        action_class=action_class,
        capability_specification_sha256=capability_specification_sha256,
        capability_candidate_sha256=capability_candidate_sha256,
        mission_sha256=mission_sha256,
        label=label,
    )
    try:
        fetched = fetcher(
            witness.requested_url,
            allowed_hosts=witness.allowed_hosts,
            max_bytes=witness.max_bytes,
            timeout_seconds=witness.timeout_seconds,
        )
        _require(
            fetched.final_url == witness.final_url,
            f"{label} discovery final URL drifted from reviewed witness",
        )
        candidates, visible_text = _source_discovery._candidate_records(fetched.body)
        visible_sha, visible_size = _visible_text_binding(visible_text)
        _require(
            visible_sha == witness.visible_text_sha256,
            f"{label} discovery visible-text SHA-256 drifted from reviewed witness",
        )
        _require(
            visible_size == witness.visible_text_utf8_bytes,
            f"{label} discovery visible-text size drifted from reviewed witness",
        )
        _require(
            _canonical_sha(candidates) == expected_candidates_sha256,
            f"{label} ranked discovery candidate projection drifted from reviewed witness",
        )
        fetcher.assert_consumed()
    except _smoke_replay.CapabilitySmokeReplayEvidenceError as exc:
        raise AutonomousProductionExactHeadRound8Error(
            f"{label} retained semantic replay failed: {exc}"
        ) from exc
    except _source_discovery.NistAmmtCalibrationSourceDiscoveryError as exc:
        raise AutonomousProductionExactHeadRound8Error(
            f"{label} discovery semantic projection failed: {exc}"
        ) from exc


def verify_candidate_semantic_and_static_witness(
    evidence: Mapping[str, Any],
    *,
    action_class: str,
    capability_specification_sha256: str,
    capability_candidate_sha256: str,
    mission_sha256: str,
    html_witness: SemanticHtmlWitness = CANDIDATE_HTML_WITNESS,
    pdf_witness: ExactSourceWitness = CANDIDATE_FULL_TEXT_WITNESS,
    label: str = "capability promotion 3",
) -> None:
    """Authenticate mutable candidate-page semantics and exact static primary PDF bytes."""

    fetcher, _context = _authenticated_replay_fetcher(
        evidence,
        action_class=action_class,
        capability_specification_sha256=capability_specification_sha256,
        capability_candidate_sha256=capability_candidate_sha256,
        mission_sha256=mission_sha256,
        label=label,
    )
    try:
        page = fetcher(
            html_witness.requested_url,
            allowed_hosts=html_witness.allowed_hosts,
            max_bytes=html_witness.max_bytes,
            timeout_seconds=html_witness.timeout_seconds,
        )
        _require(
            page.final_url == html_witness.final_url,
            f"{label} candidate-page final URL drifted from reviewed witness",
        )
        visible_text, derived_full_text_url = _candidate_acquisition._parse_candidate_page(
            page.body,
            html_witness.requested_url,
        )
        visible_sha, visible_size = _visible_text_binding(visible_text)
        _require(
            visible_sha == html_witness.visible_text_sha256,
            f"{label} candidate-page visible-text SHA-256 drifted from reviewed witness",
        )
        _require(
            visible_size == html_witness.visible_text_utf8_bytes,
            f"{label} candidate-page visible-text size drifted from reviewed witness",
        )
        _require(
            derived_full_text_url == pdf_witness.requested_url,
            f"{label} candidate-page derived full-text URL drifted from reviewed witness",
        )

        pdf = fetcher(
            pdf_witness.requested_url,
            allowed_hosts=pdf_witness.allowed_hosts,
            max_bytes=pdf_witness.max_bytes,
            timeout_seconds=pdf_witness.timeout_seconds,
        )
        _require(
            pdf.final_url == pdf_witness.final_url,
            f"{label} primary PDF final URL drifted from reviewed witness",
        )
        _require(
            len(pdf.body) == pdf_witness.source_size_bytes,
            f"{label} primary PDF size drifted from reviewed witness",
        )
        _require(
            hashlib.sha256(pdf.body).hexdigest() == pdf_witness.source_sha256,
            f"{label} primary PDF SHA-256 drifted from reviewed witness",
        )
        fetcher.assert_consumed()
    except _smoke_replay.CapabilitySmokeReplayEvidenceError as exc:
        raise AutonomousProductionExactHeadRound8Error(
            f"{label} retained semantic replay failed: {exc}"
        ) from exc
    except _candidate_acquisition.NistAmmtCalibrationCandidateAcquisitionError as exc:
        raise AutonomousProductionExactHeadRound8Error(
            f"{label} candidate-page semantic projection failed: {exc}"
        ) from exc


def _promotion_replay_context(
    *,
    root: Path,
    step: int,
) -> tuple[Mapping[str, Any], str, str, str, str]:
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
    return evidence, action_class, specification_sha, candidate_sha, mission_sha


def verify_exact_head_round8_boundaries(output_root: str | Path) -> None:
    """Bind promotions 2/3 to reviewed semantic authority and immutable source witnesses."""

    root = Path(output_root).expanduser().resolve(strict=True)
    manifest = _merge_gate._load(root, "autonomous-production-manifest.json")
    cycles = manifest.get("cycles")
    _require(isinstance(cycles, list), "autonomous production cycles must be a list")

    if len(cycles) >= _round6._PROMOTIONS[1][3]:
        evidence, action_class, specification_sha, candidate_sha, mission_sha = (
            _promotion_replay_context(root=root, step=2)
        )
        verify_discovery_semantic_witness(
            evidence,
            action_class=action_class,
            capability_specification_sha256=specification_sha,
            capability_candidate_sha256=candidate_sha,
            mission_sha256=mission_sha,
        )

    if len(cycles) >= _round6._PROMOTIONS[2][3]:
        evidence, action_class, specification_sha, candidate_sha, mission_sha = (
            _promotion_replay_context(root=root, step=3)
        )
        verify_candidate_semantic_and_static_witness(
            evidence,
            action_class=action_class,
            capability_specification_sha256=specification_sha,
            capability_candidate_sha256=candidate_sha,
            mission_sha256=mission_sha,
        )


__all__ = [
    "AutonomousProductionExactHeadRound8Error",
    "CANDIDATE_FULL_TEXT_WITNESS",
    "CANDIDATE_HTML_WITNESS",
    "DISCOVERY_CANDIDATES_SHA256",
    "DISCOVERY_HTML_WITNESS",
    "ExactSourceWitness",
    "SemanticHtmlWitness",
    "WITNESS_ORIGIN_ARTIFACT_DIGEST",
    "WITNESS_ORIGIN_ARTIFACT_ID",
    "WITNESS_ORIGIN_RUN_ID",
    "verify_candidate_semantic_and_static_witness",
    "verify_discovery_semantic_witness",
    "verify_exact_head_round8_boundaries",
]
