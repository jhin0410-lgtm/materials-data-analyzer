"""Fresh exact-head fail-closed closures for late authority-bearing provenance.

This gate is deliberately additive.  It reconstructs policy qualifications from the trusted
checkout instead of trusting persisted, attacker-rehashable summaries; requires mutable discovery
fingerprints to exist before their values may be projected away; pins the PDF parser environment
used by retained multisource replay; and enforces the complete no-unrestricted-network execution
boundary of the cycle-4 acquisition report.
"""
from __future__ import annotations

import importlib.metadata
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from . import autonomous_production_exact_head_p2_round7 as _round7
from . import autonomous_production_exact_head_p2_round8 as _round8
from . import autonomous_production_merge_gate_hardening as _merge_gate
from . import in625_geometry_condition_multisource_policy as _multisource_policy
from . import nist_ammt_candidate_acquisition_policy as _candidate_policy
from . import nist_ammt_source_discovery_policy as _discovery_policy
from . import nist_mds2_2923_reference_chain_policy as _reference_policy

AutonomousProductionFreshReviewRound9Error = (
    _merge_gate.AutonomousProductionMergeGateHardeningError
)

_EXPECTED_PYPDF_VERSION = "6.18.1"
_MULTISOURCE_POLICY_PATH = (
    "configs/research/in625_geometry_condition_multisource_acquisition_policy.v1.json"
)
_MULTISOURCE_REGISTRY_PATH = (
    "configs/research/in625_geometry_condition_source_reconnaissance.v1.json"
)
_DISCOVERY_FINGERPRINT_FIELDS = (
    "source_sha256",
    "source_size_bytes",
    "http_content_type",
    "visible_text_sha256",
    "visible_text_utf8_bytes",
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_NETWORK_FALSE_FIELDS = (
    "unrestricted_network_search_performed",
    "caller_authored_url_used",
    "arbitrary_url_fetch_performed",
    "network_failure_interpreted_as_negative_scientific_evidence",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionFreshReviewRound9Error(message)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    return value


def _validate_discovery_fingerprints(report: Mapping[str, Any], *, label: str) -> None:
    source = _mapping(report.get("source_index"), label=f"{label} source_index")
    for field in _DISCOVERY_FINGERPRINT_FIELDS:
        _require(field in source, f"{label} mutable fingerprint is missing: {field}")
    for field in ("source_sha256", "visible_text_sha256"):
        value = source.get(field)
        _require(
            isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None,
            f"{label} mutable fingerprint is malformed: {field}",
        )
    for field in ("source_size_bytes", "visible_text_utf8_bytes"):
        value = source.get(field)
        _require(
            isinstance(value, int) and not isinstance(value, bool) and value > 0,
            f"{label} mutable fingerprint is malformed: {field}",
        )
    content_type = source.get("http_content_type")
    _require(
        content_type is None
        or (isinstance(content_type, str) and bool(content_type.strip())),
        f"{label} mutable fingerprint is malformed: http_content_type",
    )


def _validate_multisource_report_boundaries(report: Mapping[str, Any]) -> None:
    extractor = _mapping(report.get("pdf_extractor"), label="multisource PDF extractor")
    _require(
        extractor.get("package") == "pypdf"
        and extractor.get("version") == _EXPECTED_PYPDF_VERSION
        and extractor.get("strict") is False,
        "multisource PDF extractor environment drifted from pinned replay contract",
    )
    try:
        installed = importlib.metadata.version("pypdf")
    except importlib.metadata.PackageNotFoundError as exc:
        raise AutonomousProductionFreshReviewRound9Error(
            "pypdf is missing from the historical replay environment"
        ) from exc
    _require(
        installed == _EXPECTED_PYPDF_VERSION,
        "installed pypdf version drifted from historical replay contract",
    )
    for field in _NETWORK_FALSE_FIELDS:
        _require(
            report.get(field) is False,
            f"multisource acquisition widened network/scientific execution boundary: {field}",
        )
    _require(
        report.get("network_requests_performed") == 8
        and report.get("network_request_budget") == 8,
        "multisource network request execution/budget drifted",
    )
    _require(
        report.get("source_bytes_persisted") is True
        and report.get("retained_source_bytes_count") == 8,
        "multisource retained-source execution provenance is incomplete",
    )


def _require_exact_qualification(
    *,
    root: Path,
    filename: str,
    expected: Mapping[str, Any],
    label: str,
) -> None:
    persisted = _merge_gate._load(root, filename)
    _require(
        _canonical_bytes(persisted) == _canonical_bytes(expected),
        f"{label} drifted from trusted checkout reconstruction",
    )


def _rebuild_qualification(
    builder: Callable[..., dict[str, Any]],
    *,
    repository_root: Path,
    mission_path: Path,
    mission_sha: str,
    label: str,
    **kwargs: object,
) -> dict[str, Any]:
    try:
        return builder(
            repository_root=repository_root,
            mission_path=mission_path,
            expected_mission_sha256=mission_sha,
            **kwargs,
        )
    except ValueError as exc:
        raise AutonomousProductionFreshReviewRound9Error(
            f"{label} could not be reconstructed from trusted checkout inputs: {exc}"
        ) from exc


def _verify_late_policy_qualifications(root: Path, *, cycle_count: int) -> None:
    repository_root, mission_path, mission_sha = _round7._trusted_mission_binding()

    if cycle_count >= 4:
        expected_multisource = _rebuild_qualification(
            _multisource_policy.authenticate_geometry_condition_multisource_policy,
            repository_root=repository_root,
            mission_path=mission_path,
            mission_sha=mission_sha,
            label="multisource policy qualification",
            policy_path=(repository_root / _MULTISOURCE_POLICY_PATH).resolve(strict=True),
            registry_path=(repository_root / _MULTISOURCE_REGISTRY_PATH).resolve(strict=True),
        )
        _require_exact_qualification(
            root=root,
            filename="multisource-policy-qualification.json",
            expected=expected_multisource,
            label="multisource policy qualification",
        )

    late_specs: tuple[tuple[str, Callable[..., dict[str, Any]], str], ...] = (
        (
            "nist-ammt-source-discovery-policy-qualification.json",
            _discovery_policy.authenticate_nist_ammt_source_discovery_policy,
            "NIST AMMT source-discovery policy qualification",
        ),
        (
            "nist-ammt-candidate-acquisition-policy-qualification.json",
            _candidate_policy.authenticate_nist_ammt_candidate_acquisition_policy,
            "NIST AMMT candidate-acquisition policy qualification",
        ),
        (
            "nist-mds2-2923-reference-chain-policy-qualification.json",
            _reference_policy.authenticate_nist_mds2_2923_reference_chain_policy,
            "NIST mds2-2923 reference-chain policy qualification",
        ),
    )
    for filename, builder, label in late_specs:
        path = root / filename
        if cycle_count >= 12:
            _require(path.is_file(), f"{label} is missing from full-success provenance")
        if not path.is_file():
            continue
        expected = _rebuild_qualification(
            builder,
            repository_root=repository_root,
            mission_path=mission_path,
            mission_sha=mission_sha,
            label=label,
        )
        _require_exact_qualification(
            root=root,
            filename=filename,
            expected=expected,
            label=label,
        )


def verify_fresh_review_round9_boundaries(output_root: str | Path) -> None:
    root = Path(output_root).expanduser().resolve(strict=True)
    manifest = _merge_gate._load(root, "autonomous-production-manifest.json")
    cycles = manifest.get("cycles")
    _require(isinstance(cycles, list), "autonomous production cycles must be a list")
    cycle_count = len(cycles)

    if cycle_count >= 4:
        multisource = _merge_gate._load(root, "multisource-source-acquisition.json")
        _merge_gate._verify_self_hash(
            multisource,
            "report_sha256_without_self_field",
            label="multisource source acquisition",
        )
        _validate_multisource_report_boundaries(multisource)

    discovery_path = root / "calibration-record-source-discovery.json"
    if cycle_count >= 12:
        _require(discovery_path.is_file(), "full-success provenance is missing discovery report")
    if discovery_path.is_file():
        persisted_discovery = _merge_gate._load(root, discovery_path.name)
        _validate_discovery_fingerprints(
            persisted_discovery,
            label="persisted calibration discovery report",
        )
        trusted_discovery = _round8._trusted_smoke_receipt(root, step=2)
        _validate_discovery_fingerprints(
            trusted_discovery,
            label="trusted promotion-2 discovery replay",
        )

    _verify_late_policy_qualifications(root, cycle_count=cycle_count)


__all__ = [
    "AutonomousProductionFreshReviewRound9Error",
    "verify_fresh_review_round9_boundaries",
]
