import pytest

from src.platform_core.adapter_registry import build_default_adapter_registry
from src.platform_core.artifacts import build_default_artifact_registry
from src.platform_core.case_study_adapter import build_case_study_stage_plan
from src.platform_core.case_study_registry import CaseStudyRegistry, build_default_case_study_registry
from src.platform_core.registry import build_default_plugin_registry
from src.platform_core.trust_registry import build_default_trust_policy_registry
from src.platform_core.validation_registry import build_default_validation_policy_registry


def _registries():
    plugin_registry = build_default_plugin_registry()
    artifact_registry = build_default_artifact_registry()
    validation_registry = build_default_validation_policy_registry()
    trust_registry = build_default_trust_policy_registry()
    adapter_registry = build_default_adapter_registry(plugin_registry, artifact_registry)
    case_study_registry = build_default_case_study_registry(
        plugin_registry,
        artifact_registry,
        validation_registry,
        trust_registry,
        adapter_registry,
    )
    return plugin_registry, artifact_registry, validation_registry, trust_registry, adapter_registry, case_study_registry


def test_default_case_study_listing_is_deterministic_and_honest():
    *_, case_study_registry = _registries()

    case_studies = case_study_registry.list_case_studies()

    assert [case.case_study_id for case in case_studies] == [
        "battery_archive",
        "materials_project",
        "reliability",
        "smart_factory",
    ]
    assert all(case.status != "fully_onboarded" for case in case_studies)
    assert case_study_registry.get("battery_archive").trust_policy_id is None
    assert case_study_registry.get("reliability").executable_stages == ("trust",)


def test_case_study_registry_unknown_and_duplicate_rejected():
    plugin_registry, artifact_registry, validation_registry, trust_registry, adapter_registry, case_study_registry = _registries()

    with pytest.raises(KeyError, match="unknown case_study_id"):
        case_study_registry.get("missing")

    duplicate = case_study_registry.get("reliability")
    with pytest.raises(ValueError, match="duplicate case_study_id"):
        case_study_registry.register(
            duplicate,
            plugin_registry=plugin_registry,
            artifact_registry=artifact_registry,
            validation_registry=validation_registry,
            trust_registry=trust_registry,
            adapter_registry=adapter_registry,
        )


def test_case_study_stage_bridge_maps_execution_boundaries():
    _, artifact_registry, _, _, adapter_registry, case_study_registry = _registries()

    reliability = build_case_study_stage_plan(
        case_study_id="reliability",
        stage="trust",
        case_study_registry=case_study_registry,
        artifact_registry=artifact_registry,
        adapter_registry=adapter_registry,
    )
    materials = build_case_study_stage_plan(
        case_study_id="materials_project",
        stage="trust",
        case_study_registry=case_study_registry,
        artifact_registry=artifact_registry,
        adapter_registry=adapter_registry,
    )
    battery = build_case_study_stage_plan(
        case_study_id="battery_archive",
        stage="validation",
        case_study_registry=case_study_registry,
        artifact_registry=artifact_registry,
        adapter_registry=adapter_registry,
    )

    assert reliability.adapter_id == "reliability_trust_closeout"
    assert reliability.execution_boundary == "adapter_mapped_verify_allowlisted"
    assert materials.execution_boundary == "adapter_mapped_execution_disabled"
    assert battery.missing_stage_reason == "stage_not_mapped"
    assert battery.execution_status == "not_available"


def test_case_study_completeness_snapshot_fields():
    *_, case_study_registry = _registries()

    snapshot = case_study_registry.completeness_snapshot()
    reliability = next(item for item in snapshot if item["case_study_id"] == "reliability")

    assert reliability["onboarding_status"] == "execution_candidate"
    assert reliability["readiness_matrix"]["executable_allowed"] is True
    assert "trust" in reliability["mapped_stages"]
