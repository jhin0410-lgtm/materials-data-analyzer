"""Authenticate finite multi-source evidence authority for IN625 condition mapping."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

POLICY_ID = "in625-geometry-condition-multisource-acquisition-v1"
ACTION_CLASS = "reviewed_geometry_condition_mapping_assessment"
REGISTRY_PATH = "configs/research/in625_geometry_condition_source_reconnaissance.v1.json"
REGISTRY_BLOB_SHA1 = "d117162543a8e0c01328d65acadbe482172b16dd"
RECONNAISSANCE_ID = "in625-geometry-condition-multisource-recon-v1"
ALLOWED_HOSTS = ("www.nist.gov", "tsapps.nist.gov")
MAX_REQUESTS = 8
MAX_SOURCE_BYTES = 33_554_432
MAX_TOTAL_BYTES = 100_663_296
TIMEOUT_SECONDS = 180

_EXPECTED_SOURCES: dict[str, dict[str, Any]] = {
    "nist-official-amb2018-02-description": {
        "source_class": "official_web_document",
        "url": "https://www.nist.gov/ambench/amb2018-02-description",
        "media_type": "html",
        "doi": None,
        "claim_ids": (
            "amb2018-ammt-actual-power-correction",
            "amb2018-programmed-cases-and-replications",
        ),
    },
    "nist-official-amb2018-benchmark-test-data": {
        "source_class": "official_web_document",
        "url": "https://www.nist.gov/ambench/benchmark-test-data",
        "media_type": "html",
        "doi": None,
        "claim_ids": ("benchmark-ammt-calibration-note",),
    },
    "nist-official-amb2018-challenges-description": {
        "source_class": "official_web_document",
        "url": "https://www.nist.gov/ambench/challenges-and-descriptions",
        "media_type": "html",
        "doi": None,
        "claim_ids": ("benchmark-later-spot-size-correction-note",),
    },
    "ricker-2019-topographic-tracks": {
        "source_class": "primary_paper",
        "url": "https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=928240",
        "media_type": "pdf",
        "doi": "10.1007/s40192-019-00157-0",
        "claim_ids": ("ricker-two-machine-bare-plate-design",),
    },
    "lane-2020-melt-pool-geometry": {
        "source_class": "primary_paper",
        "url": "https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=927485",
        "media_type": "pdf",
        "doi": "10.1007/s40192-020-00169-1",
        "claim_ids": (
            "lane-surface-preparation-320-grit",
            "lane-ammt-cbm-spot-diameters",
            "lane-machine-environment",
            "lane-ammt-corrected-cases",
            "lane-cross-section-uncertainty-exists",
        ),
    },
    "weaver-2021-spot-size-scaling-metadata": {
        "source_class": "primary_paper_metadata",
        "url": (
            "https://www.nist.gov/publications/"
            "laser-spot-size-and-scaling-laws-laser-beam-additive-manufacturing"
        ),
        "media_type": "html",
        "doi": "10.1016/j.jmapro.2021.10.053",
        "claim_ids": ("weaver-spot-size-range-abstract",),
    },
    "naderi-2022-scaling-fidelity": {
        "source_class": "primary_paper",
        "url": "https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=935135",
        "media_type": "pdf",
        "doi": "10.1007/s40192-022-00289-w",
        "claim_ids": (
            "naderi-eos-m270-condition-space",
            "naderi-ammt-spot-range",
            "naderi-spot-measurement-authority",
        ),
    },
    "nist-2026-ambench-uncertainty-synthesis": {
        "source_class": "official_technical_paper_metadata",
        "url": (
            "https://www.nist.gov/publications/"
            "enabling-modelers-test-their-simulations-against-rigorous-highly-controlled-additive"
        ),
        "media_type": "html",
        "doi": None,
        "claim_ids": (
            "nist-2026-machine-parameter-uncertainty",
            "nist-2026-cross-section-uncertainty",
        ),
    },
}


class GeometryConditionMultisourcePolicyError(ValueError):
    """Raised when multi-source acquisition authority drifts or cannot authenticate."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise GeometryConditionMultisourcePolicyError(
                f"duplicate JSON key is not allowed: {key}"
            )
        value[key] = item
    return value


def _load_object(path: Path, field: str) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GeometryConditionMultisourcePolicyError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise GeometryConditionMultisourcePolicyError(f"{field} root must be an object")
    return value, raw


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GeometryConditionMultisourcePolicyError(message)


def _git_blob_sha1(raw: bytes) -> str:
    header = b"blob " + str(len(raw)).encode("ascii") + b"\0"
    return hashlib.sha1(header + raw, usedforsecurity=False).hexdigest()


def authenticate_geometry_condition_multisource_policy(
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    policy_path: str | Path,
    registry_path: str | Path,
) -> dict[str, Any]:
    """Authenticate mission, policy and exact source registry without network access."""
    root = Path(repository_root).expanduser().resolve(strict=True)
    mission_file = Path(mission_path).expanduser().resolve(strict=True)
    policy_file = Path(policy_path).expanduser().resolve(strict=True)
    registry_file = Path(registry_path).expanduser().resolve(strict=True)
    for path, field in (
        (mission_file, "mission"),
        (policy_file, "policy"),
        (registry_file, "source registry"),
    ):
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise GeometryConditionMultisourcePolicyError(
                f"{field} path escaped repository root"
            ) from exc

    mission, mission_raw = _load_object(mission_file, "mission")
    policy, policy_raw = _load_object(policy_file, "policy")
    registry, registry_raw = _load_object(registry_file, "source registry")
    observed_mission_sha = hashlib.sha256(mission_raw).hexdigest()
    _require(
        observed_mission_sha == expected_mission_sha256,
        "mission bytes do not match independently supplied mission SHA-256",
    )

    observed_policy_sha = hashlib.sha256(policy_raw).hexdigest()
    pins = mission.get("source_trust_policy_pins")
    _require(isinstance(pins, list), "mission source-trust pins are missing")
    matches = [
        item
        for item in pins
        if isinstance(item, dict) and item.get("policy_id") == POLICY_ID
    ]
    _require(
        len(matches) == 1,
        "mission must contain exactly one multi-source policy pin",
    )
    _require(
        matches[0].get("sha256") == observed_policy_sha,
        "mission multi-source policy pin does not match exact policy bytes",
    )

    _require(policy.get("schema_version") == "1.0", "policy schema drifted")
    _require(policy.get("policy_id") == POLICY_ID, "policy identity drifted")
    _require(policy.get("action_class") == ACTION_CLASS, "policy action class drifted")
    source_binding = policy.get("source_registry")
    _require(
        isinstance(source_binding, dict),
        "policy source registry binding is missing",
    )
    _require(
        source_binding
        == {
            "path": REGISTRY_PATH,
            "git_blob_sha1": REGISTRY_BLOB_SHA1,
            "schema_version": "1.0",
            "reconnaissance_id": RECONNAISSANCE_ID,
        },
        "source-registry binding drifted or widened",
    )
    observed_registry_blob_sha = _git_blob_sha1(registry_raw)
    _require(
        observed_registry_blob_sha == REGISTRY_BLOB_SHA1,
        "source-registry exact Git blob identity drifted",
    )

    network = policy.get("network")
    _require(
        network
        == {
            "scheme": "https",
            "allowed_hosts": list(ALLOWED_HOSTS),
            "max_requests": MAX_REQUESTS,
            "max_source_bytes": MAX_SOURCE_BYTES,
            "max_total_bytes": MAX_TOTAL_BYTES,
            "timeout_seconds": TIMEOUT_SECONDS,
            "unrestricted_search_allowed": False,
            "caller_authored_urls_allowed": False,
        },
        "multi-source network authority widened or drifted",
    )
    authority = policy.get("authority")
    _require(
        authority
        == {
            "source_count": 8,
            "paper_claims_may_be_row_level_measurement_authority": False,
            "source_bytes_may_be_committed": False,
            "claim_anchor_match_required": True,
            "scientific_status_change_authorized_by_acquisition": False,
        },
        "multi-source scientific authority drifted",
    )

    _require(registry.get("schema_version") == "1.0", "registry schema drifted")
    _require(
        registry.get("reconnaissance_id") == RECONNAISSANCE_ID,
        "registry identity drifted",
    )
    registry_network = registry.get("network_policy")
    _require(isinstance(registry_network, dict), "registry network policy missing")
    _require(
        registry_network.get("scheme") == "https"
        and registry_network.get("allowed_hosts") == list(ALLOWED_HOSTS)
        and registry_network.get("max_source_bytes") == MAX_SOURCE_BYTES
        and registry_network.get("max_total_bytes") == MAX_TOTAL_BYTES
        and registry_network.get("timeout_seconds") == TIMEOUT_SECONDS
        and registry_network.get("unrestricted_search") is False
        and registry_network.get("arbitrary_url_fetch") is False,
        "registry network authority widened or drifted",
    )
    sources = registry.get("sources")
    _require(
        isinstance(sources, list) and len(sources) == 8,
        "registry source count drifted",
    )
    by_id: dict[str, dict[str, Any]] = {}
    for raw in sources:
        _require(isinstance(raw, dict), "registry source entries must be objects")
        source_id = raw.get("source_id")
        _require(isinstance(source_id, str), "registry source_id missing")
        _require(
            source_id not in by_id,
            "registry source_id values must be unique",
        )
        by_id[source_id] = raw
    _require(
        set(by_id) == set(_EXPECTED_SOURCES),
        "registry source universe drifted",
    )

    for source_id, expected in _EXPECTED_SOURCES.items():
        source = by_id[source_id]
        _require(
            source.get("source_class") == expected["source_class"],
            f"{source_id} source class drifted",
        )
        _require(source.get("url") == expected["url"], f"{source_id} URL drifted")
        _require(
            source.get("media_type") == expected["media_type"],
            f"{source_id} media type drifted",
        )
        _require(source.get("doi") == expected["doi"], f"{source_id} DOI drifted")
        claims = source.get("claims_under_review")
        _require(isinstance(claims, list), f"{source_id} claims are missing")
        claim_ids = tuple(
            item.get("claim_id") for item in claims if isinstance(item, dict)
        )
        _require(
            len(claim_ids) == len(claims) and claim_ids == expected["claim_ids"],
            f"{source_id} claim contract drifted",
        )
        for claim in claims:
            _require(
                isinstance(claim.get("anchor_regex"), str)
                and claim["anchor_regex"].strip(),
                f"{source_id} claim anchor missing",
            )
            _require(
                isinstance(claim.get("scope"), str) and claim["scope"].strip(),
                f"{source_id} claim scope missing",
            )

    return {
        "schema_version": "1.0",
        "qualification_status": (
            "exact_multisource_condition_evidence_policy_authenticated"
        ),
        "policy_id": POLICY_ID,
        "action_class": ACTION_CLASS,
        "mission_sha256": observed_mission_sha,
        "policy_sha256": observed_policy_sha,
        "registry_git_blob_sha1": observed_registry_blob_sha,
        "registry_sha256": hashlib.sha256(registry_raw).hexdigest(),
        "source_count": len(sources),
        "source_ids": list(_EXPECTED_SOURCES),
        "allowed_hosts": list(ALLOWED_HOSTS),
        "max_requests": MAX_REQUESTS,
        "max_source_bytes": MAX_SOURCE_BYTES,
        "max_total_bytes": MAX_TOTAL_BYTES,
        "network_access_performed": False,
        "paper_claims_promoted_to_row_level_authority": False,
        "metadata_or_abstract_sources_promoted_to_full_text": False,
        "scientific_status_changed": False,
    }


__all__ = [
    "ACTION_CLASS",
    "ALLOWED_HOSTS",
    "GeometryConditionMultisourcePolicyError",
    "MAX_REQUESTS",
    "MAX_SOURCE_BYTES",
    "MAX_TOTAL_BYTES",
    "POLICY_ID",
    "REGISTRY_BLOB_SHA1",
    "REGISTRY_PATH",
    "RECONNAISSANCE_ID",
    "TIMEOUT_SECONDS",
    "authenticate_geometry_condition_multisource_policy",
]
