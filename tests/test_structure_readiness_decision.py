from src.platform_core.materials_project_structure_enrichment import summarize_v2_2_4_readiness


def test_readiness_blocks_no_api_data_without_fake_counts():
    summary = summarize_v2_2_4_readiness(
        requested_count=838,
        docs=[],
        alignment_rows=[],
        entity_summary=None,
        descriptor_summary=None,
        graph_summary=None,
    )

    assert summary["structure_prediction_readiness"] == "blocked_no_api_data"
    assert summary["predictive_claim_made"] is False
    assert summary["model_training_run"] is False


def test_readiness_allows_restricted_status_after_aligned_valid_artifacts():
    summary = summarize_v2_2_4_readiness(
        requested_count=2,
        docs=[{"material_id": "mp-1", "structure": {}}, {"material_id": "mp-2", "structure": {}}],
        alignment_rows=[
            {"comparison_status": "target_exact_match"},
            {"comparison_status": "target_within_numeric_tolerance"},
        ],
        entity_summary={"integrity_status_counts": {"valid": 2}},
        descriptor_summary={"descriptor_eligible_entities": 2},
        graph_summary={"graph_eligible_entities": 2},
    )

    assert summary["structure_prediction_readiness"] == "structure_prediction_ready_with_restrictions"
