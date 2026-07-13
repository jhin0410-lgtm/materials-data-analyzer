"""Explicit registry for generic case-study interface metadata."""

from __future__ import annotations

from dataclasses import dataclass, field

from .adapter_registry import AdapterRegistry
from .artifacts import ArtifactRegistry
from .case_studies import CaseStudyMetadata, CaseStudyStageMetadata
from .registry import PluginRegistry
from .trust_registry import TrustPolicyRegistry
from .validation_registry import ValidationPolicyRegistry


@dataclass
class CaseStudyRegistry:
    """Deterministic registry for case-study lifecycle metadata."""

    _case_studies: dict[str, CaseStudyMetadata] = field(default_factory=dict)

    def register(
        self,
        case_study: CaseStudyMetadata,
        *,
        plugin_registry: PluginRegistry,
        artifact_registry: ArtifactRegistry,
        validation_registry: ValidationPolicyRegistry,
        trust_registry: TrustPolicyRegistry,
        adapter_registry: AdapterRegistry | None = None,
    ) -> None:
        if case_study.case_study_id in self._case_studies:
            raise ValueError(f"duplicate case_study_id: {case_study.case_study_id}")
        plugin = plugin_registry.get(case_study.plugin_id)
        if plugin.case_study_id != case_study.case_study_id:
            raise ValueError(
                f"plugin {plugin.plugin_id} belongs to {plugin.case_study_id}, not {case_study.case_study_id}"
            )
        if case_study.validation_policy_id is not None:
            validation_registry.get(case_study.validation_policy_id)
        if case_study.trust_policy_id is not None:
            trust_registry.get(case_study.trust_policy_id)
        for stage_metadata in case_study.stage_metadata:
            self._validate_stage_metadata(case_study, stage_metadata, artifact_registry, adapter_registry)
        self._case_studies[case_study.case_study_id] = case_study

    def _validate_stage_metadata(
        self,
        case_study: CaseStudyMetadata,
        stage_metadata: CaseStudyStageMetadata,
        artifact_registry: ArtifactRegistry,
        adapter_registry: AdapterRegistry | None,
    ) -> None:
        for artifact_id in (
            stage_metadata.required_artifact_ids
            + stage_metadata.optional_artifact_ids
            + stage_metadata.produced_artifact_ids
        ):
            artifact = artifact_registry.get(artifact_id)
            if artifact.case_study_id != case_study.case_study_id:
                raise ValueError(
                    f"artifact {artifact_id} does not belong to case study {case_study.case_study_id}"
                )
        if stage_metadata.adapter_id is not None:
            if adapter_registry is None:
                raise ValueError("adapter registry is required for stage adapter validation")
            adapter = adapter_registry.get(stage_metadata.adapter_id)
            if adapter.case_study_id != case_study.case_study_id:
                raise ValueError(
                    f"adapter {adapter.adapter_id} does not belong to case study {case_study.case_study_id}"
                )
            if adapter.stage != stage_metadata.stage:
                raise ValueError(
                    f"adapter {adapter.adapter_id} stage {adapter.stage} does not match {stage_metadata.stage}"
                )

    def get(self, case_study_id: str) -> CaseStudyMetadata:
        try:
            return self._case_studies[case_study_id]
        except KeyError as exc:
            raise KeyError(f"unknown case_study_id: {case_study_id}") from exc

    def list_case_studies(self) -> list[CaseStudyMetadata]:
        return [self._case_studies[key] for key in sorted(self._case_studies)]

    def get_stage(self, case_study_id: str, stage: str) -> CaseStudyStageMetadata:
        case_study = self.get(case_study_id)
        stage_metadata = case_study.stage(stage)
        if stage_metadata is None:
            raise KeyError(f"case_study_id {case_study_id} has no stage metadata for {stage}")
        return stage_metadata

    def snapshot(self) -> list[dict[str, object]]:
        return [case_study.to_dict() for case_study in self.list_case_studies()]

    def completeness_snapshot(self) -> list[dict[str, object]]:
        return [
            {
                "case_study_id": case_study.case_study_id,
                "status": case_study.status,
                "supported_stages": list(case_study.supported_stages),
                "mapped_stages": [
                    stage.stage for stage in case_study.stage_metadata if stage.adapter_id is not None
                ],
                "executable_stages": list(case_study.executable_stages),
                "missing_stages": list(case_study.missing_stages()),
                "validation_policy": case_study.validation_policy_id,
                "trust_policy": case_study.trust_policy_id,
                "artifact_count": sum(
                    len(stage.required_artifact_ids) + len(stage.optional_artifact_ids) + len(stage.produced_artifact_ids)
                    for stage in case_study.stage_metadata
                ),
                "test_coverage_status": "synthetic_platform_tests",
                "documentation_status": "documented" if case_study.documentation_path else "missing",
                "release_tag": case_study.release_tag,
                "onboarding_status": case_study.onboarding_status(),
                "readiness_matrix": case_study.completeness_flags(),
            }
            for case_study in self.list_case_studies()
        ]


def build_default_case_study_registry(
    plugin_registry: PluginRegistry,
    artifact_registry: ArtifactRegistry,
    validation_registry: ValidationPolicyRegistry,
    trust_registry: TrustPolicyRegistry,
    adapter_registry: AdapterRegistry,
) -> CaseStudyRegistry:
    """Build the built-in case-study interface registry."""

    registry = CaseStudyRegistry()
    common_local_policy = (
        "raw data stays local-only",
        "large generated row-level artifacts stay local-only",
        "tracked artifacts are compact summaries, manifests, contracts, or inventories",
    )
    case_studies = [
        CaseStudyMetadata(
            case_study_id="battery_archive",
            display_name="Battery Archive",
            domain="battery_cycle_aging",
            description="Cycle-level battery aging case study based on zip inventory and normalized cycle summaries.",
            status="partially_onboarded",
            plugin_id="battery_archive",
            config_schema_version="2.0",
            data_contract_id="battery_archive_cycle_data_contract",
            validation_policy_id="group_aware_regression",
            trust_policy_id=None,
            primary_unit="cell_cycle",
            time_key="cycle_index",
            group_keys=("cycle_series_id", "cell_id"),
            target_type="capacity_retention_proxy",
            supported_stages=("contract", "acquisition", "normalization", "readiness", "validation", "closeout"),
            available_stages=("contract", "acquisition", "normalization", "readiness", "closeout"),
            executable_stages=(),
            local_only_policy=common_local_policy,
            documentation_path="data/case_studies/battery_archive/README.md",
            release_tag="v1.1",
            limitations=(
                "timeseries feature extraction remains future work",
                "trust-stage adapter is not mapped in v2.0.4",
                "analysis-ready full table is local-only",
            ),
            stage_metadata=(
                CaseStudyStageMetadata(
                    stage="acquisition",
                    required_artifact_ids=(),
                    produced_artifact_ids=("battery_archive_cycle_file_inventory",),
                    execution_status="script_only",
                    raw_data_required=True,
                    side_effect_class="tracked_compact_outputs",
                    description="Zip member inventory and cycle-file discovery.",
                ),
                CaseStudyStageMetadata(
                    stage="normalization",
                    required_artifact_ids=("battery_archive_cycle_file_inventory",),
                    produced_artifact_ids=("battery_archive_analysis_ready",),
                    execution_status="script_only",
                    raw_data_required=True,
                    side_effect_class="local_only_outputs",
                    description="Cycle CSV normalization and analysis-ready table creation.",
                ),
                CaseStudyStageMetadata(
                    stage="closeout",
                    required_artifact_ids=("battery_archive_reliability_group_summary",),
                    produced_artifact_ids=("battery_archive_reliability_group_summary",),
                    execution_status="script_only",
                    side_effect_class="tracked_compact_outputs",
                    description="Battery Archive case-study summary artifacts.",
                ),
            ),
            interface_status="interface_partial",
        ),
        CaseStudyMetadata(
            case_study_id="materials_project",
            display_name="Materials Project",
            domain="materials_property_screening",
            description="Computed-property screening and group-aware validation case study with exact-provenance boundary.",
            status="interface_mapped",
            plugin_id="materials_project",
            config_schema_version="2.0",
            data_contract_id="materials_project_v1_3_contract",
            validation_policy_id="group_aware_regression",
            trust_policy_id="materials_group_generalization",
            primary_unit="material_entry",
            time_key=None,
            group_keys=("composition_group",),
            target_type="energy_above_hull_regression",
            supported_stages=("contract", "acquisition", "normalization", "validation", "trust", "closeout"),
            available_stages=("contract", "acquisition", "normalization", "validation", "trust", "closeout"),
            executable_stages=(),
            local_only_policy=common_local_policy,
            documentation_path="data/case_studies/materials_project/README.md",
            release_tag="v1.3.1",
            limitations=(
                "no DFT execution",
                "no production screening claim",
                "trust adapter is dry-run mapped but not executable",
            ),
            stage_metadata=(
                CaseStudyStageMetadata(
                    stage="validation",
                    required_artifact_ids=("materials_project_v1_3_validation_metrics",),
                    produced_artifact_ids=("materials_project_v1_3_validation_metrics",),
                    execution_status="script_only",
                    side_effect_class="tracked_compact_outputs",
                    description="Group-aware validation compact metrics.",
                ),
                CaseStudyStageMetadata(
                    stage="trust",
                    adapter_id="materials_project_trust_closeout",
                    required_artifact_ids=("materials_project_v1_3_validation_metrics",),
                    produced_artifact_ids=(
                        "materials_project_v1_3_trust_conclusion",
                        "materials_project_v1_3_claim_boundary",
                    ),
                    execution_status="dry_run_mapped_execution_blocked",
                    side_effect_class="manifest_only",
                    description="Trust-boundary closeout mapping; actual script execution remains disabled.",
                ),
            ),
            interface_status="interface_complete",
        ),
        CaseStudyMetadata(
            case_study_id="smart_factory",
            display_name="Smart Factory / UCI SECOM",
            domain="process_quality_classification",
            description="SECOM process-quality fallback case study with time-aware validation and trust boundary.",
            status="interface_mapped",
            plugin_id="smart_factory",
            config_schema_version="2.0",
            data_contract_id="smart_factory_v1_4_process_quality_contract",
            validation_policy_id="time_aware_classification",
            trust_policy_id="smart_factory_time_aware",
            primary_unit="process_sample",
            time_key="observation_timestamp",
            group_keys=(),
            target_type="binary_failure_classification",
            supported_stages=("contract", "acquisition", "normalization", "readiness", "validation", "trust", "closeout"),
            available_stages=("contract", "acquisition", "normalization", "readiness", "validation", "trust", "closeout"),
            executable_stages=(),
            local_only_policy=common_local_policy,
            documentation_path="data/case_studies/smart_factory/README.md",
            release_tag="v1.4.0",
            limitations=(
                "no explicit equipment, lot, product, or recipe IDs",
                "group-aware validation is not ready",
                "trust adapter is dry-run mapped but not executable",
            ),
            stage_metadata=(
                CaseStudyStageMetadata(
                    stage="validation",
                    required_artifact_ids=("smart_factory_v1_4_classification_metrics",),
                    produced_artifact_ids=("smart_factory_v1_4_classification_metrics",),
                    execution_status="script_only",
                    side_effect_class="tracked_compact_outputs",
                    description="Time-aware classification compact metrics.",
                ),
                CaseStudyStageMetadata(
                    stage="trust",
                    adapter_id="smart_factory_trust_closeout",
                    required_artifact_ids=("smart_factory_v1_4_classification_metrics",),
                    produced_artifact_ids=(
                        "smart_factory_v1_4_trust_summary",
                        "smart_factory_v1_4_claim_boundary",
                        "smart_factory_v1_4_closeout_conclusion",
                    ),
                    execution_status="dry_run_mapped_execution_blocked",
                    side_effect_class="manifest_only",
                    description="Trust-boundary closeout mapping; actual script execution remains disabled.",
                ),
            ),
            interface_status="interface_complete",
        ),
        CaseStudyMetadata(
            case_study_id="reliability",
            display_name="Reliability / Backblaze",
            domain="asset_reliability_risk",
            description="Backblaze asset-level reliability case study with 7-day asset/time-aware diagnostic validation.",
            status="partially_onboarded",
            plugin_id="reliability",
            config_schema_version="2.0",
            data_contract_id="reliability_contract_v1_5",
            validation_policy_id="asset_time_combined_classification",
            trust_policy_id="reliability_asset_time_aware",
            primary_unit="asset_prediction_origin",
            time_key="observation_date",
            group_keys=("serial_number",),
            target_type="binary_7_day_failure_risk",
            supported_stages=(
                "contract",
                "acquisition",
                "normalization",
                "readiness",
                "feature_build",
                "validation",
                "trust",
                "closeout",
            ),
            available_stages=(
                "contract",
                "acquisition",
                "normalization",
                "readiness",
                "feature_build",
                "validation",
                "trust",
                "closeout",
            ),
            executable_stages=("trust",),
            local_only_policy=common_local_policy,
            documentation_path="data/case_studies/reliability/README.md",
            release_tag="v1.5.0",
            limitations=(
                "trust verify adapter only reads compact tracked artifacts",
                "raw archive and row-level prediction artifacts are local-only",
                "no survival, RUL, calibrated probability, or maintenance automation claim",
            ),
            stage_metadata=(
                CaseStudyStageMetadata(
                    stage="validation",
                    required_artifact_ids=("reliability_v1_5_classification_metrics",),
                    produced_artifact_ids=("reliability_v1_5_classification_metrics",),
                    execution_status="script_only",
                    side_effect_class="tracked_compact_outputs",
                    description="Asset/time-aware classification compact metrics.",
                ),
                CaseStudyStageMetadata(
                    stage="trust",
                    adapter_id="reliability_trust_closeout",
                    required_artifact_ids=(
                        "reliability_v1_5_classification_metrics",
                        "reliability_v1_5_model_eligibility",
                        "reliability_v1_5_validation_stability_summary",
                        "reliability_v1_5_trust_summary",
                        "reliability_v1_5_claim_boundary",
                        "reliability_v1_5_closeout_conclusion",
                    ),
                    produced_artifact_ids=(
                        "reliability_v1_5_trust_summary",
                        "reliability_v1_5_claim_boundary",
                        "reliability_v1_5_closeout_conclusion",
                    ),
                    execution_status="verify_executable_allowlisted",
                    side_effect_class="local_only_outputs",
                    description="Controlled read-only verification of tracked reliability trust artifacts.",
                ),
            ),
            interface_status="interface_complete",
        ),
    ]
    for case_study in case_studies:
        registry.register(
            case_study,
            plugin_registry=plugin_registry,
            artifact_registry=artifact_registry,
            validation_registry=validation_registry,
            trust_registry=trust_registry,
            adapter_registry=adapter_registry,
        )
    return registry
