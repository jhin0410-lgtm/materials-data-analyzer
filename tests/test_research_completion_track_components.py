from __future__ import annotations

import hashlib

import pytest

from materials_data_analyzer.research_loop.advanced_statistics_gate import (
    assess_statistical_model_eligibility,
    propagate_independent_standard_uncertainty,
)
from materials_data_analyzer.research_loop.expected_information_gain import (
    expected_information_gain,
    rank_actions_by_eig,
)
from materials_data_analyzer.research_loop.experimental_lineage import ObservationLineage
from materials_data_analyzer.research_loop.literature_evidence_harvester import (
    build_literature_discovery_request,
    normalize_crossref_work,
    normalize_datacite_doi,
    normalize_pmc_search_ids,
)
from materials_data_analyzer.research_loop.research_agent_benchmark import (
    aggregate_agent_benchmark,
    evaluate_agent_scenario,
)
from materials_data_analyzer.research_loop.research_episode import create_research_episode
from materials_data_analyzer.research_loop.research_operations_ui import (
    render_research_episode_html,
)


def _lineage(index: int, *, lab: str = "lab-a", lot: str = "lot-a") -> ObservationLineage:
    return ObservationLineage(
        source_id="source-a" if lab == "lab-a" else "source-b",
        lab_id=lab,
        material_lot_id=lot,
        build_or_synthesis_id=f"build-{index}",
        specimen_id=f"specimen-{index}",
        process_run_id=f"run-{index}",
        acquisition_id=f"acq-{index}",
        measurement_id=f"measurement-{index}",
    )


def test_agent_benchmark_fails_on_epistemic_safety_violation() -> None:
    checks = {
        "evidence_promotion_safe": True,
        "provenance_complete": True,
        "abstention_correct": True,
        "independence_handled": True,
        "review_gate_respected": True,
        "operational_failure_separated": True,
        "next_action_correct": True,
        "stop_condition_correct": True,
    }
    good = evaluate_agent_scenario(
        scenario_id="safe",
        checks=checks,
        cost_units=2.0,
        reference_cost_units=2.0,
    )
    unsafe_checks = dict(checks)
    unsafe_checks["evidence_promotion_safe"] = False
    unsafe = evaluate_agent_scenario(
        scenario_id="unsafe",
        checks=unsafe_checks,
        cost_units=1.0,
        reference_cost_units=2.0,
    )
    summary = aggregate_agent_benchmark([good, unsafe])
    assert good["qualified"] is True
    assert unsafe["false_evidence_promotion"] is True
    assert summary["benchmark_passed"] is False
    assert summary["critical_failure_count"] == 1


def test_advanced_statistics_uses_lineage_not_row_count() -> None:
    lineages = [_lineage(1), _lineage(2)]
    eligibility = assess_statistical_model_eligibility(
        lineages,
        fixed_effects_declared=True,
        repeated_measurements_expected=True,
    )
    assert eligibility["variance_components_eligible"] is True
    assert eligibility["row_count_used_as_independence_without_lineage"] is False
    uncertainty = propagate_independent_standard_uncertainty(
        sensitivities=[1.0, 2.0],
        standard_uncertainties=[0.1, 0.2],
        independence_explicitly_established=True,
    )
    assert uncertainty["eligible"] is True
    assert uncertainty["combined_standard_uncertainty"] == pytest.approx((0.01 + 0.16) ** 0.5)
    blocked = propagate_independent_standard_uncertainty(
        sensitivities=[1.0],
        standard_uncertainties=[0.1],
        independence_explicitly_established=False,
    )
    assert blocked["combined_standard_uncertainty"] is None


def test_eig_requires_validated_probability_model_and_ranks_by_information_per_cost() -> None:
    blocked = expected_information_gain(
        prior_hypothesis_probabilities=[0.5, 0.5],
        outcome_probabilities=[0.5, 0.5],
        posterior_probabilities_by_outcome=[[0.9, 0.1], [0.1, 0.9]],
        probabilistic_model_validated=False,
        model_artifact_sha256=None,
    )
    assert blocked["mode"] == "structural_proxy_only"
    digest = hashlib.sha256(b"model").hexdigest()
    informative = expected_information_gain(
        prior_hypothesis_probabilities=[0.5, 0.5],
        outcome_probabilities=[0.5, 0.5],
        posterior_probabilities_by_outcome=[[0.9, 0.1], [0.1, 0.9]],
        probabilistic_model_validated=True,
        model_artifact_sha256=digest,
        action_cost_units=1.0,
    )
    expensive = expected_information_gain(
        prior_hypothesis_probabilities=[0.5, 0.5],
        outcome_probabilities=[0.5, 0.5],
        posterior_probabilities_by_outcome=[[0.9, 0.1], [0.1, 0.9]],
        probabilistic_model_validated=True,
        model_artifact_sha256=digest,
        action_cost_units=2.0,
    )
    ranked = rank_actions_by_eig({"cheap": informative, "expensive": expensive, "proxy": blocked})
    assert informative["eig_bits"] > 0
    assert [item["action_id"] for item in ranked] == ["cheap", "expensive"]


def test_literature_queries_are_bounded_metadata_discovery_and_keep_evidence_classes() -> None:
    crossref = build_literature_discovery_request(
        provider="crossref", query="IN625 laser powder bed fusion", rows=10
    )
    datacite = build_literature_discovery_request(
        provider="datacite", query="IN625 melt pool dataset", rows=10
    )
    pmc = build_literature_discovery_request(
        provider="pmc", query="additive manufacturing IN625", rows=10
    )
    assert crossref["url"].startswith("https://api.crossref.org/works?")
    assert datacite["url"].startswith("https://api.datacite.org/dois?")
    assert "db=pmc" in pmc["url"]
    assert all(
        request["scientific_status_changed"] is False
        for request in (crossref, datacite, pmc)
    )

    paper = normalize_crossref_work({"DOI": "10.1/test", "title": ["Paper"]})
    dataset = normalize_datacite_doi(
        {
            "id": "10.2/data",
            "attributes": {"titles": [{"title": "Dataset"}], "types": {"resourceTypeGeneral": "Dataset"}},
        }
    )
    pmc_record = normalize_pmc_search_ids(["123"])[0]
    assert paper.evidence_class.value == "E5_literature_claim"
    assert dataset.evidence_class.value == "E2_publication_supplement"
    assert pmc_record.evidence_class.value == "E5_literature_claim"
    assert dataset.trust.reuse == "unknown"


def test_research_operations_ui_is_escaped_and_read_only() -> None:
    episode = create_research_episode(
        episode_id="episode-ui",
        research_question="Does <script>alert(1)</script> execute?",
        mission_id="mission-ui",
        objectives=["observe safely"],
        max_iterations=3,
        cost_budget=3.0,
    )
    rendered = render_research_episode_html(episode)
    assert "<script>alert(1)</script>" not in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert "Read Only" in rendered
    assert "cannot approve evidence" in rendered
    assert "<form" not in rendered.lower()
