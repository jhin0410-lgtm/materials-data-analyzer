from src.platform_core.v2_2_trust_closeout import validate_artifact_lineage


def test_v2_2_artifact_lineage_uses_tracked_compact_artifacts_only():
    lineage = validate_artifact_lineage()

    assert lineage["valid"] is True
    assert lineage["input_artifact_count"] >= 14
    assert lineage["missing_artifacts"] == []
    for artifact in lineage["artifacts"]:
        assert artifact["tracked_compact"] is True
        assert artifact["artifact"].startswith("data/processed/")
        assert "outputs/" not in artifact["artifact"]
        assert len(artifact["checksum_sha256"]) == 64
