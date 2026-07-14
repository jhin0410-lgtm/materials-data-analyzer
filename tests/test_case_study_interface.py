import pytest

from src.platform_core.case_studies import CaseStudyMetadata, CaseStudyStageMetadata


def test_case_study_stage_rejects_unknown_stage_and_duplicate_artifacts():
    with pytest.raises(ValueError, match="unsupported case-study stage"):
        CaseStudyStageMetadata(stage="not_a_stage")

    with pytest.raises(ValueError, match="duplicate required_artifact_ids"):
        CaseStudyStageMetadata(stage="trust", required_artifact_ids=("a", "a"))


def test_case_study_metadata_enforces_executable_subset_and_no_weak_full_onboarding():
    with pytest.raises(ValueError, match="subset"):
        CaseStudyMetadata(
            case_study_id="demo",
            display_name="Demo",
            domain="demo",
            description="demo",
            status="partially_onboarded",
            plugin_id="demo",
            config_schema_version="2.0",
            data_contract_id="contract",
            validation_policy_id=None,
            trust_policy_id=None,
            primary_unit="row",
            time_key=None,
            group_keys=(),
            target_type="none",
            supported_stages=("contract", "trust"),
            available_stages=("contract",),
            executable_stages=("trust",),
            local_only_policy=("local",),
            documentation_path="docs/demo.md",
            release_tag=None,
            limitations=(),
        )

    with pytest.raises(ValueError, match="fully_onboarded"):
        CaseStudyMetadata(
            case_study_id="demo",
            display_name="Demo",
            domain="demo",
            description="demo",
            status="fully_onboarded",
            plugin_id="demo",
            config_schema_version="2.0",
            data_contract_id="contract",
            validation_policy_id=None,
            trust_policy_id=None,
            primary_unit="row",
            time_key=None,
            group_keys=(),
            target_type="none",
            supported_stages=("contract", "trust"),
            available_stages=("contract",),
            executable_stages=(),
            local_only_policy=("local",),
            documentation_path="docs/demo.md",
            release_tag=None,
            limitations=(),
        )


def test_case_study_metadata_readiness_matrix():
    metadata = CaseStudyMetadata(
        case_study_id="demo",
        display_name="Demo",
        domain="demo",
        description="demo",
        status="partially_onboarded",
        plugin_id="demo",
        config_schema_version="2.0",
        data_contract_id="contract",
        validation_policy_id="random_reference_only",
        trust_policy_id=None,
        primary_unit="row",
        time_key=None,
        group_keys=(),
        target_type="binary",
        supported_stages=("contract",),
        available_stages=("contract",),
        executable_stages=(),
        local_only_policy=("local",),
        documentation_path="docs/demo.md",
        release_tag=None,
        limitations=(),
    )

    flags = metadata.completeness_flags()

    assert flags["identity_defined"] is True
    assert flags["trust_policy_defined"] is False
    assert metadata.onboarding_status() == "not_ready"
