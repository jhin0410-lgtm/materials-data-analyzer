"""Authenticate the finite Naderi evidence authority for mds2-2923 reference-chain analysis."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

POLICY_ID = "nist-mds2-2923-reference-chain-naderi-evidence-v1"
ACTION_CLASS = "mds2_2923_experiment_identity_reference_chain_assessment"
POLICY_PATH = "configs/research/nist_mds2_2923_reference_chain_naderi_evidence_policy.v1.json"
POLICY_SHA256 = "f57ff93cf18d38c72ddf27f71028c28309fb2eae8476a1381931c6eab4028815"
SOURCE_ID = "naderi-2022-scaling-fidelity-reference-chain"
SOURCE_URL = "https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=935135"
SOURCE_DOI = "10.1007/s40192-022-00289-w"
SOURCE_SHA256 = "c35a62f9f3b9346af2e0fa99de46710b3017c915e3c792dbf01c83b920a53e81"
SOURCE_SIZE_BYTES = 4_597_480
ALLOWED_HOSTS = ("tsapps.nist.gov",)
MAX_REQUESTS = 1
MAX_SOURCE_BYTES = 8_388_608
MAX_TOTAL_BYTES = 8_388_608
TIMEOUT_SECONDS = 120
MATCH_MODE = "ordered_same_page_fragments"
MAX_CLAIM_SPAN_UTF8_BYTES = 4096
CLAIMS = (
    (
        "naderi-ammt-in625-weaver-detail-reference",
        (
            "AMMT",
            "195 W",
            "800 mm/s",
            "spot diameters ranging from 50",
            "256",
            "AMMT laser spot size",
            "Single tracks on IN625 substrates",
            "More details are provided",
            "Weaver",
            "[7]",
        ),
        "Naderi identifies the IN625 AMMT 195 W / 800 mm/s spot-size experiment and delegates experiment details to Weaver et al. reference 7",
    ),
    (
        "naderi-reference-7-weaver-spot-size-paper",
        (
            "7. Weaver",
            "Heigel JC",
            "Lane BM",
            "Laser spot size",
            "J Manuf Process",
            "73:26",
        ),
        "Naderi bibliography resolves reference 7 to the Weaver/Heigel/Lane IN625 spot-size paper",
    ),
    (
        "naderi-reference-31-ammt-design",
        (
            "31. Lane",
            "Mekhontsev S",
            "Grantham S",
            "Vlasea ML",
            "Design, developments, and results",
            "NIST additive",
            "metrology testbed (AMMT)",
            "2016 International solid",
            "freeform fabrication symposium",
        ),
        "Naderi bibliography resolves AMMT platform reference 31 to the 2016 NIST AMMT design paper",
    ),
    (
        "naderi-reference-32-lane-in625-protocol",
        (
            "32. Lane",
            "Heigel J",
            "Ricker R",
            "Zhirnov I",
            "Weaver J",
            "(2020)",
            "melt pool geometry and cooling rates",
            "individual laser traces",
            "IN625 bare plates",
            "Integr Mater Manuf Innov",
            "9(1):16",
        ),
        "Naderi bibliography resolves reference 32 to the Lane 2020 IN625 cross-section protocol paper",
    ),
)


class NistMds22923ReferenceChainPolicyError(ValueError):
    """Raised when reference-chain source authority cannot be authenticated exactly."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise NistMds22923ReferenceChainPolicyError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _load(path: Path, field: str) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NistMds22923ReferenceChainPolicyError(f"{field} must be UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise NistMds22923ReferenceChainPolicyError(f"{field} root must be an object")
    return value, raw


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise NistMds22923ReferenceChainPolicyError(message)


def authenticate_nist_mds2_2923_reference_chain_policy(
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    policy_path: str | Path | None = None,
) -> dict[str, Any]:
    """Authenticate exact mission/policy bytes without performing network access."""
    root = Path(repository_root).expanduser().resolve(strict=True)
    mission_file = Path(mission_path).expanduser().resolve(strict=True)
    policy_file = (
        Path(policy_path).expanduser().resolve(strict=True)
        if policy_path is not None
        else (root / POLICY_PATH).resolve(strict=True)
    )
    for path, field in ((mission_file, "mission"), (policy_file, "policy")):
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise NistMds22923ReferenceChainPolicyError(
                f"{field} path escaped repository root"
            ) from exc

    mission, mission_raw = _load(mission_file, "mission")
    policy, policy_raw = _load(policy_file, "policy")
    mission_sha = hashlib.sha256(mission_raw).hexdigest()
    _require(
        mission_sha == expected_mission_sha256,
        "mission bytes do not match independently supplied mission SHA-256",
    )
    policy_sha = hashlib.sha256(policy_raw).hexdigest()
    _require(policy_sha == POLICY_SHA256, "reference-chain policy exact bytes drifted")

    pins = mission.get("source_trust_policy_pins")
    _require(isinstance(pins, list), "mission source-trust pins are missing")
    matches = [
        item for item in pins
        if isinstance(item, dict) and item.get("policy_id") == POLICY_ID
    ]
    _require(
        len(matches) == 1 and matches[0].get("sha256") == policy_sha,
        "mission reference-chain policy pin does not match exact policy bytes",
    )

    expected_policy = {
        "schema_version": "1.1",
        "policy_id": POLICY_ID,
        "action_class": ACTION_CLASS,
        "source": {
            "source_id": SOURCE_ID,
            "url": SOURCE_URL,
            "source_class": "primary_paper",
            "media_type": "pdf",
            "doi": SOURCE_DOI,
            "expected_sha256": SOURCE_SHA256,
            "expected_size_bytes": SOURCE_SIZE_BYTES,
        },
        "network": {
            "scheme": "https",
            "allowed_hosts": list(ALLOWED_HOSTS),
            "max_requests": MAX_REQUESTS,
            "max_source_bytes": MAX_SOURCE_BYTES,
            "max_total_bytes": MAX_TOTAL_BYTES,
            "timeout_seconds": TIMEOUT_SECONDS,
            "unrestricted_search_allowed": False,
            "caller_authored_urls_allowed": False,
            "same_host_redirects_only": True,
        },
        "claims": [
            {
                "claim_id": claim_id,
                "match_mode": MATCH_MODE,
                "max_span_utf8_bytes": MAX_CLAIM_SPAN_UTF8_BYTES,
                "required_fragments": list(fragments),
                "scope": scope,
            }
            for claim_id, fragments, scope in CLAIMS
        ],
        "authority": {
            "reference_claims_may_establish_dataset_row_identity": False,
            "same_platform_may_establish_experiment_identity": False,
            "reference_chain_may_establish_power_conversion_without_explicit_edge": False,
            "literature_may_be_row_level_measurement_authority": False,
            "scientific_status_change_authorized_by_acquisition": False,
            "global_evidence_unavailability_may_be_claimed_from_failure": False,
        },
    }
    _require(policy == expected_policy, "reference-chain policy semantics drifted or widened")
    return {
        "schema_version": "1.1",
        "qualification_status": "exact_nist_mds2_2923_reference_chain_policy_authenticated",
        "policy_id": POLICY_ID,
        "policy_sha256": policy_sha,
        "mission_sha256": mission_sha,
        "action_class": ACTION_CLASS,
        "source_id": SOURCE_ID,
        "source_url": SOURCE_URL,
        "source_doi": SOURCE_DOI,
        "source_sha256": SOURCE_SHA256,
        "source_size_bytes": SOURCE_SIZE_BYTES,
        "allowed_hosts": list(ALLOWED_HOSTS),
        "max_requests": MAX_REQUESTS,
        "max_source_bytes": MAX_SOURCE_BYTES,
        "max_total_bytes": MAX_TOTAL_BYTES,
        "timeout_seconds": TIMEOUT_SECONDS,
        "claim_match_mode": MATCH_MODE,
        "max_claim_span_utf8_bytes": MAX_CLAIM_SPAN_UTF8_BYTES,
        "network_access_performed": False,
        "caller_authored_url_used": False,
        "scientific_status_changed": False,
    }


__all__ = [
    "ACTION_CLASS",
    "ALLOWED_HOSTS",
    "CLAIMS",
    "MATCH_MODE",
    "MAX_CLAIM_SPAN_UTF8_BYTES",
    "MAX_REQUESTS",
    "MAX_SOURCE_BYTES",
    "MAX_TOTAL_BYTES",
    "NistMds22923ReferenceChainPolicyError",
    "POLICY_ID",
    "POLICY_PATH",
    "POLICY_SHA256",
    "SOURCE_DOI",
    "SOURCE_ID",
    "SOURCE_SHA256",
    "SOURCE_SIZE_BYTES",
    "SOURCE_URL",
    "TIMEOUT_SECONDS",
    "authenticate_nist_mds2_2923_reference_chain_policy",
]
