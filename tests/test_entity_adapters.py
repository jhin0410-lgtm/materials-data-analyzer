import pandas as pd
import pytest

from src.platform_core.entity_adapters import (
    composition_row_to_entity,
    entity_to_compact_dict,
    legacy_scientific_input_to_quantities,
    measurement_dataframe_metadata_to_entity,
    quantity_to_legacy_value,
)


def test_composition_row_adapter_is_deterministic_and_compact():
    row = {
        "formula": "FeSi",
        "elements": ["Fe", "Si"],
        "stoichiometric_amounts": {"Fe": 1, "Si": 1},
        "atomic_fractions": {"Fe": 0.5, "Si": 0.5},
    }

    first = composition_row_to_entity(row)
    second = composition_row_to_entity(row)
    compact = entity_to_compact_dict(first)

    assert first.entity_id == second.entity_id
    assert compact["entity_type"] == "MaterialCompositionEntity"


def test_measurement_dataframe_adapter_records_metadata_not_full_table():
    frame = pd.DataFrame({"time": [0, 1], "signal": [2.0, 3.0]})
    entity = measurement_dataframe_metadata_to_entity(
        frame,
        entity_id="series_demo",
        independent_variable="time",
        dependent_variable="signal",
        artifact_ref="outputs/synthetic/series.csv",
    )

    assert entity.attributes["axis_metadata"]["row_count"] == 2
    assert entity.artifact_refs == ("outputs/synthetic/series.csv",)


def test_legacy_scientific_input_to_quantities_preserves_units():
    quantities = legacy_scientific_input_to_quantities(
        [{"variable_id": "temperature", "value": 25.0, "unit": "degC"}]
    )
    legacy = quantity_to_legacy_value(quantities["temperature"])

    assert legacy["unit"] == "degC"
    assert legacy["canonical_unit"] == "K"
    assert legacy["canonical_value"] == pytest.approx(298.15)
