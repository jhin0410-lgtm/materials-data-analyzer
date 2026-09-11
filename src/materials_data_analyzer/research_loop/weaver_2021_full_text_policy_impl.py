"""Authenticate exact derived full-text authority for the Weaver 2021 IN625 paper."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

POLICY_ID = "weaver-2021-full-text-derived-acquisition-v1"
ACTION_CLASS = "weaver_2021_spot_size_full_text_derived_acquisition"
POLICY_PATH = "configs/research/weaver_2021_full_text_derived_acquisition_policy.v1.json"
POLICY_SHA256 = "ca245cdfd6c8a0df1f6e485e5c5aea55ac94ba40896395868e754bf3763cfae0"
AUTHORITY_EXTENSION_ID = "autonomous-in625-production-weaver-authority-extension-v1"
AUTHORITY_EXTENSION_PATH = "configs/research/autonomous_in625_weaver_authority_extension.v1.json"
AUTHORITY_EXTENSION_SHA256 = "e8954d0b2f9af071db928b9750ca87eff3fe950c0753a79daf23567a7e833fc6"
BASE_MISSION_ID = "autonomous-in625-production-v1"
BASE_MISSION_SHA256 = "98d8730a4ba1221685267ed56cd7ae75f2ce60fcfdd8f8bb426a3825986c70ea"
PREDECESSOR_ACTION_CLASS = "mds2_2923_experiment_identity_reference_chain_assessment"
SOURCE_ID = "weaver-2021-pmc-bioc-full-text"
SOURCE_DOI = "10.1016/j.jmapro.2021.10.053"
SOURCE_PMCID = "PMC9890508"
SOURCE_PMID = "36733901"
SOURCE_TITLE = "Laser spot size and scaling laws for laser beam additive manufacturing"
SOURCE_AUTHORS = ("Jordan S. Weaver", "Jarred C. Heigel", "Brandon M. Lane")
SOURCE_URL = (
    "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/"
    "BioC_json/PMC9890508/unicode"
)
SOURCE_PATH = "/research/bionlp/RESTful/pmcoa.cgi/BioC_json/PMC9890508/unicode"
ALLOWED_HOSTS = ("www.ncbi.nlm.nih.gov",)
MAX_REQUESTS = 1
MAX_SOURCE_BYTES = 8_388_608
MAX_TOTAL_BYTES = 8_388_608
TIMEOUT_SECONDS = 120
CLAIMS = (
    (
        "weaver-primary-condition",
        ("primary laser power and speed combination", "195 W", "800 mm", "D4", "50", "322"),
        "The Weaver paper states the primary IN625 single-track condition and overall D4sigma spot-size range.",
    ),
    (
        "weaver-ammt-machine-condition",
        ("AMMT machine", "fixed laser power and scan speed", "195 W", "800 mm", "increasing spot diameter"),
        "The Weaver paper identifies AMMT single-track scans at fixed 195 W and 800 mm/s with increasing spot diameter.",
    ),
    (
        "weaver-d4sigma-definition",
        ("spot size", "rotationally-symmetric Gaussian", "beam diameter", "D4sigma definition", "D4sigma = 4sigma"),
        "The paper defines the rotationally symmetric Gaussian beam diameter using D4sigma = 4sigma.",
    ),
    (
        "weaver-cross-section-protocol",
        ("Single scan laser tracks", "IN625", "cross-sectioned", "metallographically prepared", "Aqua Regia", "melt pool depth"),
        "The paper states the single-track IN625 cross-section and metallographic measurement protocol.",
    ),
    (
        "weaver-dataset-size",
        ("data set contains", "80 single track laser scans"),
        "The paper states the total single-track dataset size.",
    ),
    (
        "weaver-explicit-mds2-id",
        ("mds2-2923",),
        "Direct explicit mds2-2923 identifier, if present.",
    ),
    (
        "weaver-explicit-power-conversion",
        ("commanded", "195 W", "actual", "179.2 W"),
        "Explicit experiment-scoped commanded 195 W to actual 179.2 W conversion, if present.",
    ),
)


class Weaver2021FullTextPolicyError(ValueError):
    """Raised when Weaver full-text authority cannot be authenticated exactly."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise Weaver2021FullTextPolicyError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _load(path: Path, field: str) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Weaver2021FullTextPolicyError(f"{field} must be UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise Weaver2021FullTextPolicyError(f"{field} root must be an object")
    return value, raw


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Weaver2021FullTextPolicyError(message)


def authenticate_weaver_2021_full_text_policy(
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    policy_path: str | Path | None = None,
    authority_extension_path: str | Path | None = None,
) -> dict[str, Any]:
    """Authenticate immutable base mission, exact authority extension and exact source policy."""
    root = Path(repository_root).expanduser().resolve(strict=True)
    mission_file = Path(mission_path).expanduser().resolve(strict=True)
    policy_file = (
        Path(policy_path).expanduser().resolve(strict=True)
        if policy_path is not None
        else (root / POLICY_PATH).resolve(strict=True)
    )
    extension_file = (
        Path(authority_extension_path).expanduser().resolve(strict=True)
        if authority_extension_path is not None
        else (root / AUTHORITY_EXTENSION_PATH).resolve(strict=True)
    )
    for path, field in (
        (mission_file, "mission"),
        (extension_file, "authority extension"),
        (policy_file, "policy"),
    ):
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise Weaver2021FullTextPolicyError(f"{field} path escaped repository root") from exc

    mission, mission_raw = _load(mission_file, "mission")
    extension, extension_raw = _load(extension_file, "authority extension")
    policy, policy_raw = _load(policy_file, "policy")
    mission_sha = hashlib.sha256(mission_raw).hexdigest()
    _require(
        mission_sha == expected_mission_sha256 == BASE_MISSION_SHA256,
        "mission bytes do not match immutable base mission SHA-256",
    )
    _require(
        mission.get("mission_id") == BASE_MISSION_ID,
        "base mission identity drifted",
    )
    extension_sha = hashlib.sha256(extension_raw).hexdigest()
    _require(
        extension_sha == AUTHORITY_EXTENSION_SHA256,
        "Weaver authority extension exact bytes drifted",
    )
    policy_sha = hashlib.sha256(policy_raw).hexdigest()
    _require(policy_sha == POLICY_SHA256, "Weaver full-text policy exact bytes drifted")

    expected_extension = {
        "schema_version": "1.0",
        "extension_id": AUTHORITY_EXTENSION_ID,
        "base_mission_id": BASE_MISSION_ID,
        "base_mission_sha256": BASE_MISSION_SHA256,
        "authorized_action_class": ACTION_CLASS,
        "predecessor_action_class": PREDECESSOR_ACTION_CLASS,
        "source_trust_policy_pin": {
            "policy_id": POLICY_ID,
            "sha256": POLICY_SHA256,
        },
        "source_identity": {
            "doi": SOURCE_DOI,
            "pmcid": SOURCE_PMCID,
            "pmid": SOURCE_PMID,
        },
        "authority": {
            "base_mission_mutation_required": False,
            "caller_authored_url_allowed": False,
            "caller_authored_pmcid_allowed": False,
            "unrestricted_search_allowed": False,
            "authority_may_be_reused_for_other_action_classes": False,
            "acquisition_may_change_scientific_status": False,
            "literature_may_be_promoted_to_row_level_measurement_authority": False,
            "ambench_power_conversion_may_be_transferred_without_experiment_scoped_evidence": False,
        },
    }
    _require(
        extension == expected_extension,
        "Weaver authority extension semantics drifted or widened",
    )

    expected_policy = {
        "schema_version": "1.0",
        "policy_id": POLICY_ID,
        "action_class": ACTION_CLASS,
        "source": {
            "source_id": SOURCE_ID,
            "doi": SOURCE_DOI,
            "pmcid": SOURCE_PMCID,
            "pmid": SOURCE_PMID,
            "title": SOURCE_TITLE,
            "authors": list(SOURCE_AUTHORS),
            "url": SOURCE_URL,
            "source_class": "primary_paper_full_text",
            "media_type": "application/json",
        },
        "network": {
            "scheme": "https",
            "allowed_hosts": list(ALLOWED_HOSTS),
            "exact_path": SOURCE_PATH,
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
                "required_fragments": list(fragments),
                "scope": scope,
            }
            for claim_id, fragments, scope in CLAIMS
        ],
        "authority": {
            "doi_and_pmcid_are_locator_identity_not_scientific_truth": True,
            "full_text_may_establish_experiment_details": True,
            "full_text_may_establish_row_identity_without_explicit_row_binding": False,
            "full_text_may_establish_power_conversion_without_explicit_experiment_scoped_relation": False,
            "literature_may_be_row_level_measurement_authority": False,
            "scientific_status_change_authorized_by_acquisition": False,
            "global_evidence_unavailability_may_be_claimed_from_failure": False,
        },
    }
    _require(policy == expected_policy, "Weaver full-text policy semantics drifted or widened")
    return {
        "schema_version": "1.0",
        "qualification_status": "exact_weaver_2021_full_text_policy_authenticated",
        "policy_id": POLICY_ID,
        "policy_sha256": policy_sha,
        "authority_extension_id": AUTHORITY_EXTENSION_ID,
        "authority_extension_sha256": extension_sha,
        "base_mission_id": BASE_MISSION_ID,
        "mission_sha256": mission_sha,
        "action_class": ACTION_CLASS,
        "source_id": SOURCE_ID,
        "source_url": SOURCE_URL,
        "source_doi": SOURCE_DOI,
        "source_pmcid": SOURCE_PMCID,
        "source_pmid": SOURCE_PMID,
        "source_title": SOURCE_TITLE,
        "allowed_hosts": list(ALLOWED_HOSTS),
        "max_requests": MAX_REQUESTS,
        "max_source_bytes": MAX_SOURCE_BYTES,
        "max_total_bytes": MAX_TOTAL_BYTES,
        "timeout_seconds": TIMEOUT_SECONDS,
        "network_access_performed": False,
        "caller_authored_url_used": False,
        "unrestricted_search_performed": False,
        "scientific_status_changed": False,
    }


__all__ = [
    "ACTION_CLASS",
    "ALLOWED_HOSTS",
    "AUTHORITY_EXTENSION_ID",
    "AUTHORITY_EXTENSION_PATH",
    "AUTHORITY_EXTENSION_SHA256",
    "BASE_MISSION_ID",
    "BASE_MISSION_SHA256",
    "CLAIMS",
    "MAX_REQUESTS",
    "MAX_SOURCE_BYTES",
    "MAX_TOTAL_BYTES",
    "POLICY_ID",
    "POLICY_PATH",
    "POLICY_SHA256",
    "SOURCE_DOI",
    "SOURCE_ID",
    "SOURCE_PMCID",
    "SOURCE_PMID",
    "SOURCE_TITLE",
    "SOURCE_URL",
    "TIMEOUT_SECONDS",
    "Weaver2021FullTextPolicyError",
    "authenticate_weaver_2021_full_text_policy",
]
