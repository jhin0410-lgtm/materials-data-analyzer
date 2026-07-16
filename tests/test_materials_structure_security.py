import json

import pytest

from src.platform_core.materials_project_structure_enrichment import plan_existing_id_structure_enrichment


def test_structure_enrichment_rejects_target_filters_and_credentials(tmp_path):
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    (processed / "materials_project_v1_3_acquired.csv").write_text(
        "material_id,energy_above_hull\nmp-1,0.0\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported"):
        plan_existing_id_structure_enrichment(
            {"requested_fields": ["material_id", "structure", "is_stable"], "max_records": 1},
            root=tmp_path,
        )

    plan = plan_existing_id_structure_enrichment({"max_records": 1}, root=tmp_path)
    serialized = json.dumps(plan.to_dict())
    assert "MP_API_KEY" not in serialized
    assert "api_key" not in serialized.lower()
