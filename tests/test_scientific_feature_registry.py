import pytest

from src.platform_core.scientific_feature_candidates import ScientificFeatureCandidate
from src.platform_core.scientific_feature_registry import (
    ScientificFeatureRegistry,
    build_default_scientific_feature_registry,
)


def test_default_scientific_feature_registry_is_deterministic_and_valid():
    registry = build_default_scientific_feature_registry()
    features = registry.list_features()

    assert [feature.feature_id for feature in features] == sorted(feature.feature_id for feature in features)
    assert registry.validate()["valid"] is True
    assert registry.get("xrd.bragg_d_spacing").validation_status == "bounded_builder_candidate"
    assert registry.get("materials.atomic_radius_mismatch").eligibility_status == "eligible_with_metadata_requirement"
    assert registry.get("battery.capacity_retention").feature_id == "battery.capacity_retention"


def test_scientific_feature_registry_rejects_duplicates_and_unknown_references():
    registry = build_default_scientific_feature_registry()
    feature = registry.get("xrd.bragg_d_spacing")

    with pytest.raises(ValueError, match="duplicate"):
        registry.register(feature)

    empty = ScientificFeatureRegistry(
        registry.constraint_registry,
        registry.knowledge_registry,
        registry.unit_registry,
    )
    bad = ScientificFeatureCandidate(
        feature_id="bad.feature",
        name="Bad feature",
        domain="xrd",
        knowledge_pack_id="xrd_crystallography_basic_v1",
        source_constraint_ids=("missing.constraint",),
        required_variables=("two_theta",),
        required_units={"two_theta": "degree"},
        definition_summary="Bad missing constraint reference.",
    )
    with pytest.raises(KeyError):
        empty.register(bad)


def test_scientific_feature_registry_filters_by_domain_and_status():
    registry = build_default_scientific_feature_registry()

    xrd = registry.snapshot(domain="xrd")
    bounded = registry.snapshot(validation_status="bounded_builder_candidate")

    assert {row["feature_id"] for row in xrd} == {
        "xrd.bragg_d_spacing",
        "xrd.scherrer_crystallite_size",
    }
    assert "xrd.bragg_d_spacing" in {row["feature_id"] for row in bounded}
