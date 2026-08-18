"""Exact NERDm scope contract for NIST AMB2025-03 fatigue intake."""

from __future__ import annotations

import hashlib
import json
from typing import Any

PRODUCT_ID = "mds2-3734"

_REQUIRED_DESCRIPTION_TOKENS = (
    "Specimens from one build of laser powder bed fusion (PBF-L) titanium alloy (Ti-6Al-4V)",
    "were split equally into two heat treatment conditions",
    "will be referred to as 800HIP",
    "will be referred to as 800VAC",
    "Approximately 25 specimens per condition were tested in high-cycle fully reversed 4-point rotating bending fatigue",
    "RBF, R = -1",
    "according to ISO 1143",
    "All fatigue data (S-N curve) for the 800HIP condition will also be given as calibration data",
)


class NistAmb202503MetadataContractError(ValueError):
    """Raised when exact NERDm bytes no longer support the declared source scope."""


def _json_object(raw: bytes) -> dict[str, Any]:
    if not isinstance(raw, bytes):
        raise NistAmb202503MetadataContractError("NERDm metadata must be exact bytes")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise NistAmb202503MetadataContractError(
                    f"NERDm metadata repeats JSON key {key!r}"
                )
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NistAmb202503MetadataContractError(
            "NERDm metadata must be UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise NistAmb202503MetadataContractError("NERDm root must be an object")
    return value


def validate_amb2025_03_metadata(metadata_bytes: bytes) -> dict[str, Any]:
    """Prove the one-build/two-treatment/HIP-calibration scope from exact metadata."""

    metadata = _json_object(metadata_bytes)
    identifiers = [
        value
        for key in ("@id", "ediid", "doi")
        if isinstance((value := metadata.get(key)), str)
    ]
    if not any(PRODUCT_ID.lower() in value.lower() for value in identifiers):
        raise NistAmb202503MetadataContractError(
            "NERDm identifiers do not bind mds2-3734"
        )
    if metadata.get("accessLevel") != "public":
        raise NistAmb202503MetadataContractError(
            "AMB2025-03 metadata is not explicitly public"
        )
    version = metadata.get("version")
    if not isinstance(version, str) or not version.strip() or version != version.strip():
        raise NistAmb202503MetadataContractError(
            "AMB2025-03 metadata lacks an exact source version"
        )

    description = metadata.get("description")
    if isinstance(description, str):
        description_text = description
    elif isinstance(description, list) and all(isinstance(item, str) for item in description):
        description_text = "\n".join(description)
    else:
        raise NistAmb202503MetadataContractError(
            "AMB2025-03 metadata description must be text"
        )
    missing = [token for token in _REQUIRED_DESCRIPTION_TOKENS if token not in description_text]
    if missing:
        raise NistAmb202503MetadataContractError(
            f"AMB2025-03 metadata no longer supports declared experiment scope: {missing}"
        )

    return {
        "product_id": PRODUCT_ID,
        "source_version": version,
        "metadata_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
        "one_build_declared": True,
        "post_build_conditions": ["800HIP", "800VAC"],
        "fatigue_mode": "high_cycle_fully_reversed_four_point_rotating_bending",
        "load_ratio_R": -1,
        "standard": "ISO 1143",
        "hip_fatigue_calibration_data_declared": True,
        "vac_fatigue_calibration_data_declared": False,
        "scientific_status_changed": False,
    }


__all__ = [
    "NistAmb202503MetadataContractError",
    "PRODUCT_ID",
    "validate_amb2025_03_metadata",
]
