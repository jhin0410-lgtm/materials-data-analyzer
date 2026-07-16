import pandas as pd

from src.analyzers.materials_physics_features import MaterialsFeatureBuildRequest, build_feature_matrix
from src.platform_core.entity_adapters import composition_row_to_entity


def test_materials_entity_adapter_does_not_change_v2_2_1_feature_value():
    row = {
        "formula": "FeSi",
        "elements": ["Fe", "Si"],
        "stoichiometric_amounts": {"Fe": 1, "Si": 1},
        "atomic_fractions": {"Fe": 0.5, "Si": 0.5},
    }
    entity = composition_row_to_entity(row)
    frame = pd.DataFrame({"formula": ["FeSi"]})

    result = build_feature_matrix(
        frame,
        MaterialsFeatureBuildRequest(
            input_path="synthetic.csv",
            composition_sources=("formula",),
            local_feature_matrix_path="outputs/synthetic/materials_features.csv",
        ),
    )

    assert entity.attributes["atomic_fractions"] == {"Fe": 0.5, "Si": 0.5}
    assert not result.findings
    assert len(result.feature_matrix) == 1
    assert result.feature_coverage["coverage_rate"].min() == 1.0
