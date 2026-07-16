from src.platform_core.materials_project_acquisition import (
    MaterialsProjectEnrichmentRequest,
    query_plan_from_existing_manifest,
)
import json


def test_query_plan_matches_existing_manifest_without_target_filter():
    manifest = json.loads(open("data/processed/materials_project_v1_3_acquisition_manifest.json", encoding="utf-8").read())
    plan = query_plan_from_existing_manifest(manifest)
    payload = plan.to_dict()

    assert payload["collection"] == "materials.summary"
    assert payload["filters"]["elements"] == ["Fe", "Si"]
    assert payload["filters"]["num_elements"] == [2, 5]
    assert payload["filters"]["include_gnome"] is False
    assert "energy_above_hull" in payload["requested_fields"]
    assert "structure" not in payload["requested_fields"]
    assert "energy_above_hull" not in payload["filters"]
    assert len(plan.checksum()) == 64


def test_enrichment_request_requires_bounded_material_ids():
    request = MaterialsProjectEnrichmentRequest(
        mode="enrich_existing_ids",
        material_ids=("mp-1", "mp-2"),
        requested_fields=("material_id", "structure"),
        max_records=2,
    )

    assert request.to_dict()["material_id_count"] == 2


def test_enrichment_request_rejects_unbounded_ids():
    try:
        MaterialsProjectEnrichmentRequest(
            mode="enrich_existing_ids",
            material_ids=("mp-1", "mp-2", "mp-3"),
            requested_fields=("material_id", "structure"),
            max_records=2,
        )
    except ValueError as exc:
        assert "exceed" in str(exc)
    else:
        raise AssertionError("expected max record rejection")
