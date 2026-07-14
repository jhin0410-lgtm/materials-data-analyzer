import pytest

from src.platform_core.artifacts import ArtifactMetadata, ArtifactRegistry, build_default_artifact_registry


def _artifact(**overrides):
    values = {
        "artifact_id": "demo_artifact",
        "case_study_id": "demo",
        "stage": "trust",
        "relative_path": "data/processed/demo.csv",
        "artifact_type": "summary",
        "format": "csv",
        "tracked_policy": "generated_compact",
        "local_only": False,
    }
    values.update(overrides)
    return ArtifactMetadata(**values)


def test_artifact_duplicate_rejected():
    registry = ArtifactRegistry()
    artifact = _artifact()

    registry.register(artifact)

    with pytest.raises(ValueError, match="duplicate artifact_id"):
        registry.register(artifact)


def test_artifact_rejects_absolute_and_traversal_paths():
    with pytest.raises(ValueError, match="absolute paths"):
        _artifact(relative_path="C:/tmp/demo.csv")

    with pytest.raises(ValueError, match="path traversal"):
        _artifact(relative_path="../demo.csv")


def test_artifact_rejects_tracked_local_only_conflict():
    with pytest.raises(ValueError, match="tracked/local_only conflict"):
        _artifact(tracked_policy="generated_compact", local_only=True)


def test_artifact_rejects_tracked_raw_policy():
    with pytest.raises(ValueError, match="raw artifacts cannot be tracked"):
        _artifact(
            artifact_id="raw_demo",
            relative_path="data/raw/demo/raw.zip",
            artifact_type="raw",
            tracked_policy="tracked",
            local_only=False,
        )


def test_default_artifact_registry_contains_reliability_boundaries():
    registry = build_default_artifact_registry()

    local_prediction = registry.get("reliability_v1_5_classification_predictions")
    compact_trust = registry.get("reliability_v1_5_trust_summary")

    assert local_prediction.local_only is True
    assert local_prediction.tracked_policy == "local_only"
    assert compact_trust.local_only is False
    assert compact_trust.tracked_policy == "generated_compact"
