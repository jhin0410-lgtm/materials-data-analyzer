"""Tests for Smart Factory v1.4 case-study closeout documentation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASE_STUDY = PROJECT_ROOT / "data" / "case_studies" / "smart_factory" / "case_study.md"
CASE_README = PROJECT_ROOT / "data" / "case_studies" / "smart_factory" / "README.md"
ROOT_README = PROJECT_ROOT / "README.md"
DOCS_README = PROJECT_ROOT / "docs" / "README.md"
PROJECT_STRUCTURE = PROJECT_ROOT / "docs" / "PROJECT_STRUCTURE.md"
PROCESSED = PROJECT_ROOT / "data" / "processed"


def test_case_study_contains_required_closeout_sections() -> None:
    text = CASE_STUDY.read_text(encoding="utf-8")

    for section in [
        "## 1. Executive Summary",
        "## 9. Validation Hierarchy",
        "## 14. Model Eligibility",
        "## 15. Why No Representative Model Was Selected",
        "## 17. Trust Boundary",
        "## 22. Future Data Requirements",
        "## 23. Final Conclusion",
    ]:
        assert section in text


def test_case_study_documents_negative_result_and_claim_boundary() -> None:
    text = CASE_STUDY.read_text(encoding="utf-8")

    assert "all non-dummy classification baselines remain `diagnostic_only`" in text
    assert "No representative model is selected" in text
    assert "calibrated probabilities" in text or "calibrated probability" in text
    assert "Do not describe v1.4 as" in text
    assert "Accurate failure prediction" in text


def test_navigation_links_include_smart_factory_closeout() -> None:
    root = ROOT_README.read_text(encoding="utf-8")
    docs = DOCS_README.read_text(encoding="utf-8")
    case_readme = CASE_README.read_text(encoding="utf-8")
    structure = PROJECT_STRUCTURE.read_text(encoding="utf-8")

    assert "Smart Factory / UCI SECOM" in root
    assert "data/case_studies/smart_factory/case_study.md" in root
    assert "trust-boundary closeout" in docs
    assert "Trust spec" in case_readme
    assert "classification_trust.py" in structure


def test_closeout_conclusion_marks_release_ready() -> None:
    closeout = pd.read_csv(PROCESSED / "smart_factory_v1_4_closeout_conclusion.csv")
    values = dict(zip(closeout["field"], closeout["value"]))

    assert values["v1_4_release_readiness"] == "release_ready"
    assert values["representative_model"] == "none"
    assert values["allowed_use"] == "retrospective_offline_diagnostic_framework"


def test_case_study_does_not_make_prohibited_claims_as_positive_claims() -> None:
    text = CASE_STUDY.read_text(encoding="utf-8").lower()

    assert "does not produce a production-ready predictive model" in text
    assert "accurate failure prediction model" not in text
    assert "root-cause identification model" not in text
    assert "real-time monitoring solution claim" in text
