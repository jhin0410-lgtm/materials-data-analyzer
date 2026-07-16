from pathlib import Path

from src.platform_core.artifact_resolver import ArtifactResolver
from src.platform_core.artifacts import build_default_artifact_registry
from src.platform_core.report_extractors import extract_materials_project_results
from src.platform_core.v2_2_trust_closeout import render_closeout_summary


def test_v2_2_closeout_summary_is_report_ready():
    summary = render_closeout_summary()

    assert "release readiness: `release_ready`" in summary
    assert "composition context decision: `performance_degraded`" in summary
    assert "known-structure context decision: `structure_predictive_value_limited`" in summary
    assert "graph/GNN evidence: `none`" in summary
    assert "not DFT uncertainty" in summary


def test_platform_report_extractor_reads_v2_2_closeout_artifact():
    resolver = ArtifactResolver(Path("."), build_default_artifact_registry())
    extracted = extract_materials_project_results(resolver)

    assert extracted.key_compact_results["v2_2_release_readiness"] == "release_ready"
    assert extracted.key_compact_results["v2_2_composition_decision"] == "performance_degraded"
    assert extracted.key_compact_results["v2_2_known_structure_decision"] == "structure_predictive_value_limited"
    assert extracted.key_compact_results["v2_2_representative_model"] == "none"
    assert extracted.representative_model_status == "none_selected"
