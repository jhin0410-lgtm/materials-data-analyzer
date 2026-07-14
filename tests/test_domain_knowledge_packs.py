from src.platform_core.domain_knowledge import build_default_domain_knowledge_registry
from src.platform_core.scientific_constraint_registry import build_default_scientific_constraint_registry


def test_default_domain_knowledge_packs_are_registered_and_reference_constraints():
    pack_registry = build_default_domain_knowledge_registry()
    constraint_registry = build_default_scientific_constraint_registry()

    pack_ids = [pack["pack_id"] for pack in pack_registry.snapshot()]
    assert pack_ids == sorted(pack_ids)
    assert {
        "materials_basic_v1",
        "battery_degradation_basic_v1",
        "manufacturing_process_basic_v1",
        "reliability_degradation_basic_v1",
        "xrd_crystallography_basic_v1",
    } <= set(pack_ids)
    for pack in pack_registry.snapshot():
        for constraint_id in pack["constraint_ids"]:
            assert constraint_registry.get(constraint_id).constraint_id == constraint_id


def test_domain_knowledge_cautions_prevent_overclaims():
    pack = build_default_domain_knowledge_registry().get("xrd_crystallography_basic_v1")

    assert any("not particle size" in caution for caution in pack.cautions)
    assert any(feature.status == "future_feature_candidate" for feature in pack.feature_definitions)
