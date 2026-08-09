from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from materials_data_analyzer import tm_fe_si_cross_repo as tm_case


def _cells(contract: tm_case.MagneticSourceContract, first_field: float = 30.0) -> dict[str, str | float]:
    cells: dict[str, str | float] = {
        "G1": contract.title_300k,
        "G2": tm_case.EXPECTED_FIELD_HEADER,
        "H2": tm_case.EXPECTED_MAGNETIZATION_HEADER,
    }
    fields = [first_field]
    if contract.point_count > 2:
        middle_count = contract.point_count - 2
        fields.extend(
            -30.0 + 60.0 * index / max(middle_count - 1, 1)
            for index in range(middle_count)
        )
    fields.append(30.0)
    fields[1] = -30.0
    for offset, field in enumerate(fields, start=3):
        cells[f"G{offset}"] = float(field)
        cells[f"H{offset}"] = float(10.0 + 0.001 * offset)
    return cells


def test_trace_contract_accepts_only_frozen_300k_endpoint_geometry() -> None:
    contract = next(item for item in tm_case.MAGNETIC_SOURCES if item.tm_element == "V")
    trace = tm_case._trace_from_cells(_cells(contract, first_field=29.999), contract)

    assert len(trace) == contract.point_count
    assert trace[0][0] == pytest.approx(29.999)
    assert trace[-1][0] == pytest.approx(30.0)
    assert min(field for field, _ in trace) == pytest.approx(-30.0)
    assert max(field for field, _ in trace) == pytest.approx(30.0)

    with pytest.raises(tm_case.TMFeSiCrossRepoError, match="endpoint"):
        tm_case._trace_from_cells(_cells(contract, first_field=29.99), contract)


def test_trace_contract_rejects_wrong_explicit_title() -> None:
    contract = tm_case.MAGNETIC_SOURCES[0]
    cells = _cells(contract)
    cells["G1"] = "Fig. 3(b) 200K Ti7Fe52Si41"

    with pytest.raises(tm_case.TMFeSiCrossRepoError, match="trace title"):
        tm_case._trace_from_cells(cells, contract)


def test_magnetic_row_is_direct_endpoint_observation_not_saturation_claim() -> None:
    contract = tm_case.MAGNETIC_SOURCES[0]
    trace = [(30.0, 1.0383), (-30.0, -1.0), (30.0, 1.0379)]

    row = tm_case._magnetic_row(contract, trace)

    assert row["mh_300k_plus30koe_endpoint_mean_emu_g"] == pytest.approx(1.0381)
    assert row["mh_300k_plus30koe_endpoint_abs_difference_emu_g"] == pytest.approx(0.0004)
    assert row["mh_300k_plus30koe_endpoint_count"] == 2
    assert not any("saturation" in key.lower() for key in row)
    assert not any("coerc" in key.lower() for key in row)
    assert not any("curie" in key.lower() for key in row)


def test_identity_join_requires_nominal_composition_and_preparation_family() -> None:
    imported = pd.DataFrame(
        {
            "sample_id": ["tm-fe-si-ti7fe52si41-1050c-1d"],
            "nominal_composition": ["Ti7Fe52Si41"],
            "preparation_family_id": [tm_case.PREPARATION_FAMILY_ID],
            "char__xrd__main_peak_two_theta__degree": [45.22],
        }
    )
    magnetic = pd.DataFrame(
        {
            "sample_id": ["tm-fe-si-ti7fe52si41-1050c-1d"],
            "nominal_composition": ["Ti7Fe52Si41"],
            "preparation_family_id": [tm_case.PREPARATION_FAMILY_ID],
            "mh_300k_plus30koe_endpoint_mean_emu_g": [1.0381],
        }
    )

    joined = tm_case._validate_identity_join(imported, magnetic)
    assert len(joined) == 1
    assert joined.loc[0, "mh_300k_plus30koe_endpoint_mean_emu_g"] == pytest.approx(1.0381)

    mismatched = magnetic.copy()
    mismatched.loc[0, "preparation_family_id"] = "different-preparation"
    with pytest.raises(tm_case.TMFeSiCrossRepoError, match="preparation_family_id"):
        tm_case._validate_identity_join(imported, mismatched)


def test_source_identity_guard_rejects_unpinned_bytes(tmp_path: Path) -> None:
    contract = tm_case.MAGNETIC_SOURCES[0]
    path = tmp_path / contract.filename
    path.write_bytes(b"not-the-public-source")

    with pytest.raises(tm_case.TMFeSiCrossRepoError):
        tm_case._validate_source(path, contract)


def test_magnetic_source_manifest_blocks_model_and_inference_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    for contract in tm_case.MAGNETIC_SOURCES:
        (source_dir / contract.filename).write_bytes(b"fixture")

    monkeypatch.setattr(tm_case, "_validate_source", lambda _path, _contract: None)
    monkeypatch.setattr(
        tm_case,
        "_worksheet_cells",
        lambda path: _cells(
            next(item for item in tm_case.MAGNETIC_SOURCES if item.filename == path.name),
            first_field=29.999 if " V7" in path.name else 30.0,
        ),
    )

    table, manifest = tm_case.build_magnetic_consumer_table(source_dir)

    assert len(table) == 6
    assert set(table["sample_id"]) == {item.sample_id for item in tm_case.MAGNETIC_SOURCES}
    contract = manifest["extraction_contract"]
    assert contract["interpolation"] is False
    assert contract["smoothing"] is False
    assert contract["outlier_removal"] is False
    assert contract["saturation_inferred"] is False
    assert contract["coercivity_inferred"] is False
    assert contract["curie_temperature_inferred"] is False
    blocked = manifest["scientific_boundary"]["blocked"]
    assert "association testing" in blocked
    assert "predictive modeling" in blocked
    assert "causal attribution" in blocked
    assert "engineering decision" in blocked
