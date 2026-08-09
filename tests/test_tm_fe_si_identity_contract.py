from __future__ import annotations

from materials_data_analyzer import tm_fe_si_cross_repo as tm_case


def test_tm_fe_si_identity_contract_matches_merged_mca_producer() -> None:
    assert tm_case.PREPARATION_FAMILY_ID == (
        "tm-fe-si-arc-melt-remelt-1050c-1d-air-cool"
    )
    assert [item.sample_id for item in tm_case.MAGNETIC_SOURCES] == [
        "tm-fe-si-ti7fe52si41-1050c-1d",
        "tm-fe-si-zr7fe52si41-1050c-1d",
        "tm-fe-si-hf7fe52si41-1050c-1d",
        "tm-fe-si-v7fe52si41-1050c-1d",
        "tm-fe-si-nb7fe52si41-1050c-1d",
        "tm-fe-si-ta7fe52si41-1050c-1d",
    ]
    assert [item.nominal_composition for item in tm_case.MAGNETIC_SOURCES] == [
        "Ti7Fe52Si41",
        "Zr7Fe52Si41",
        "Hf7Fe52Si41",
        "V7Fe52Si41",
        "Nb7Fe52Si41",
        "Ta7Fe52Si41",
    ]
