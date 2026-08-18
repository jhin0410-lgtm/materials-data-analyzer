from __future__ import annotations

import json

import pytest

from materials_data_analyzer.research_loop.nist_amb2025_03_metadata_contract import (
    NistAmb202503MetadataContractError,
    validate_amb2025_03_metadata,
)


DESCRIPTION = (
    "Specimens from one build of laser powder bed fusion (PBF-L) titanium alloy (Ti-6Al-4V) "
    "were split equally into two heat treatment conditions. The first condition will be referred "
    "to as 800HIP. The second condition will be referred to as 800VAC. Approximately 25 specimens "
    "per condition were tested in high-cycle fully reversed 4-point rotating bending fatigue "
    "(RBF, R = -1) according to ISO 1143. All fatigue data (S-N curve) for the 800HIP condition "
    "will also be given as calibration data."
)


def _metadata(description: str = DESCRIPTION) -> bytes:
    return (
        json.dumps(
            {
                "@id": "ark:/88434/mds2-3734",
                "ediid": "ark:/88434/mds2-3734",
                "doi": "doi:10.18434/mds2-3734",
                "accessLevel": "public",
                "version": "1.1.1",
                "description": [description],
            },
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def test_metadata_binds_one_build_two_treatments_and_hip_fatigue_scope() -> None:
    report = validate_amb2025_03_metadata(_metadata())
    assert report["source_version"] == "1.1.1"
    assert report["one_build_declared"] is True
    assert report["post_build_conditions"] == ["800HIP", "800VAC"]
    assert report["hip_fatigue_calibration_data_declared"] is True
    assert report["vac_fatigue_calibration_data_declared"] is False
    assert report["scientific_status_changed"] is False


def test_missing_one_build_scope_fails_closed() -> None:
    changed = DESCRIPTION.replace("Specimens from one build", "Specimens")
    with pytest.raises(NistAmb202503MetadataContractError, match="experiment scope"):
        validate_amb2025_03_metadata(_metadata(changed))


def test_nonpublic_metadata_fails_closed() -> None:
    payload = json.loads(_metadata())
    payload["accessLevel"] = "restricted"
    with pytest.raises(NistAmb202503MetadataContractError, match="not explicitly public"):
        validate_amb2025_03_metadata((json.dumps(payload) + "\n").encode("utf-8"))
