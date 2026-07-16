from src.platform_core.v2_2_trust_closeout import build_evidence_summary


def test_v2_2_evidence_summary_keeps_negative_and_limited_results():
    summary = build_evidence_summary()
    records = {record["evidence_id"]: record for record in summary["evidence_records"]}

    assert records["composition_derived_features"]["status"] == "performance_degraded"
    assert records["composition_derived_features"]["evidence_level"] == "predictive_value_not_supported"
    assert records["structure_descriptors"]["status"] == "structure_predictive_value_limited"
    assert records["structure_descriptors"]["evidence_level"] == "predictive_value_limited"
    assert records["periodic_graph_artifacts"]["evidence_level"] == "artifact_generated"
    assert summary["key_counts"]["composition_feature_rows"] == 838
    assert summary["key_counts"]["known_structure_cohort_rows"] == 838
    assert summary["key_counts"]["graph_artifact_count"] == 838
