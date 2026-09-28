"""Provenance-bound retrospective published comparator for AMB2018-02.

This module deliberately keeps two scientific statements separate:

1. Kollmannsberger et al.'s anisotropic-conductivity model was parameter-calibrated
   against AMMT Case B and then evaluated with those calibration parameters fixed for
   Cases A and C.
2. The publication is NOT admitted as a prospective blind A/C validation result here,
   because the model-form update to anisotropic conductivity was motivated during
   retrospective analysis of AMMT model/data discrepancies.

The comparator therefore provides useful external computational evidence without
weakening the strict no-holdout-leakage contract in the Phase-1 holdout benchmark.
"""

from __future__ import annotations

import copy
import hashlib
import html
import math
import re
import unicodedata
from collections.abc import Mapping
from html.parser import HTMLParser
from io import BytesIO
from typing import Any

from pypdf import PdfReader

from .evidence_packet import canonical_sha256
from .in625_geometry_condition_source_acquisition import fetch_exact_source
from .in625_model_holdout_benchmark import (
    HOLDOUT_CASES,
    _authenticate_contract,
    _case_response_summary,
    _mean,
    _number,
    _validated_sources,
)

SCHEMA_VERSION = "1.0"
POLICY_VERSION = "1.0"

ARTICLE_METADATA_URL = "https://mediatum.ub.tum.de/node?id=1473265"
INSTITUTIONAL_THESIS_URL = "https://mediatum.ub.tum.de/doc/1542610/1542610.pdf"
ALLOWED_HOSTS = ("mediatum.ub.tum.de",)
MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_PDF_BYTES = 64 * 1024 * 1024
TIMEOUT_SECONDS = 180.0

ARTICLE_TITLE = (
    "Accurate prediction of melt pool shapes in laser powder bed fusion by the "
    "non-linear temperature equation including phase changes"
)
ARTICLE_DOI = "10.1007/s40192-019-00132-9"
ARTICLE_AUTHORS = [
    "Stefan Kollmannsberger",
    "Massimo Carraturo",
    "Alessandro Reali",
    "Ferdinando Auricchio",
]

_PUBLISHED_VALUES = {
    "A": {"length_um": 304.0, "width_um": 146.4, "depth_um": 44.6},
    "B": {"length_um": 362.0, "width_um": 123.7, "depth_um": 36.1},
    "C": {"length_um": 346.0, "width_um": 105.1, "depth_um": 27.3},
}

_CALIBRATION_PARAMETERS = {
    "theta_x": 1.0,
    "theta_y": 1.4,
    "theta_z": 0.9,
}


class In625PublishedComparatorError(ValueError):
    """Raised when published-model evidence or retrospective scope drifts."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise In625PublishedComparatorError(message)


def _sha(value: object, field: str) -> str:
    _require(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value),
        f"{field} must be lowercase SHA-256",
    )
    return str(value)


class _TextCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data)


def _normalized_html_text(raw: bytes) -> str:
    decoded = raw.decode("utf-8", errors="replace")
    parser = _TextCollector()
    parser.feed(decoded)
    return re.sub(r"\s+", " ", html.unescape(" ".join(parser.parts))).strip()


def _normalized_pdf_pages(raw: bytes) -> list[str]:
    _require(raw.startswith(b"%PDF-"), "institutional thesis source is not a PDF")
    try:
        reader = PdfReader(BytesIO(raw), strict=False)
        pages: list[str] = []
        for page in reader.pages:
            text = unicodedata.normalize("NFKC", page.extract_text() or "")
            # Rejoin words split specifically by a PDF line-break hyphen.
            # Ordinary inline hyphens remain untouched.
            text = re.sub(r"(?<=\w)-[ \t]*\n[ \t]*(?=\w)", "", text)
            pages.append(re.sub(r"\s+", " ", text).strip())
    except Exception as exc:
        raise In625PublishedComparatorError(
            f"institutional thesis PDF could not be parsed: {exc}"
        ) from exc
    _require(any(pages), "institutional thesis PDF produced no extractable text")
    return pages

def _find_unique_page(
    pages: list[str],
    pattern: str,
    label: str,
) -> tuple[int, str]:
    compiled = re.compile(pattern, flags=re.IGNORECASE | re.DOTALL)
    matches = [
        (index, page)
        for index, page in enumerate(pages)
        if compiled.search(page)
    ]
    _require(
        len(matches) == 1,
        f"{label} must match exactly one PDF page; found {len(matches)}",
    )
    return matches[0]


def _anchor_receipt(text: str, pattern: str, label: str) -> dict[str, Any]:
    compiled = re.compile(pattern, flags=re.IGNORECASE | re.DOTALL)
    match = compiled.search(text)
    _require(match is not None, f"required source anchor missing: {label}")
    matched = match.group(0).encode("utf-8")
    return {
        "anchor_id": label,
        "pattern_sha256": hashlib.sha256(pattern.encode("utf-8")).hexdigest(),
        "matched_text_sha256": hashlib.sha256(matched).hexdigest(),
        "matched_utf8_bytes": len(matched),
    }


def acquire_kollmannsberger_retrospective_evidence() -> dict[str, Any]:
    """Acquire institutional source bytes and retain only hashes/bounded facts."""

    metadata = fetch_exact_source(
        ARTICLE_METADATA_URL,
        allowed_hosts=ALLOWED_HOSTS,
        max_bytes=MAX_METADATA_BYTES,
        timeout_seconds=TIMEOUT_SECONDS,
    )
    thesis = fetch_exact_source(
        INSTITUTIONAL_THESIS_URL,
        allowed_hosts=ALLOWED_HOSTS,
        max_bytes=MAX_PDF_BYTES,
        timeout_seconds=TIMEOUT_SECONDS,
    )
    metadata_text = _normalized_html_text(metadata.body)
    pages = _normalized_pdf_pages(thesis.body)

    metadata_anchors = [
        _anchor_receipt(
            metadata_text,
            (
                r"Accurate prediction of melt pool shapes in laser powder bed fusion "
                r"by the non-linear temperature equation including phase changes"
            ),
            "article-title",
        ),
        _anchor_receipt(
            metadata_text,
            r"10\.1007/s40192-019-00132-9",
            "article-doi",
        ),
        _anchor_receipt(
            metadata_text,
            r"Kollmannsberger.*Carraturo.*Reali.*Auricchio",
            "article-authors",
        ),
    ]

    calibration_index, calibration_page = _find_unique_page(
        pages,
        r"After calibration to the AMMT machine B we obtain the set",
        "case-b-calibration-statement",
    )
    validation_index, validation_page = _find_unique_page(
        pages,
        r"In the validation step, we keep the calibration parameters fixed",
        "fixed-parameter-a-c-validation-statement",
    )
    table_index, table_page = _find_unique_page(
        pages,
        r"A\s+304\s+146\.4\s+44\.6\s+0\.82",
        "anisotropic-computed-values-table",
    )

    calibration_anchors = [
        _anchor_receipt(
            calibration_page,
            r"After calibration to the AMMT machine B we obtain the set",
            "case-b-calibration-statement",
        ),
        _anchor_receipt(
            calibration_page,
            r"1\.0.{0,160}1\.4.{0,160}0\.9",
            "anisotropic-calibration-parameters",
        ),
        _anchor_receipt(
            validation_page,
            (
                r"In the validation step, we keep the calibration parameters fixed"
                r".{0,500}cases A and C of the AMMT machine"
            ),
            "fixed-parameter-a-c-validation-statement",
        ),
    ]
    table_anchors = [
        _anchor_receipt(
            table_page,
            r"A\s+304\s+146\.4\s+44\.6\s+0\.82",
            "published-case-a-values",
        ),
        _anchor_receipt(
            table_page,
            r"B\s+362\s+123\.7\s+36\.1\s+1\.23",
            "published-case-b-values",
        ),
        _anchor_receipt(
            table_page,
            r"C\s+346\s+105\.1\s+27\.3\s+1\.88",
            "published-case-c-values",
        ),
    ]

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "evidence_type": "published_retrospective_model_prediction_source",
        "source_bindings": [
            {
                "source_id": "tum-institutional-article-metadata",
                "role": "article_identity_and_doi",
                "requested_url": ARTICLE_METADATA_URL,
                "final_url": metadata.final_url,
                "sha256": hashlib.sha256(metadata.body).hexdigest(),
                "byte_size": len(metadata.body),
                "content_type": metadata.content_type,
                "anchors": metadata_anchors,
                "raw_source_bytes_persisted": False,
            },
            {
                "source_id": "tum-institutional-thesis-model-reproduction",
                "role": "calibration_method_and_published_prediction_values",
                "requested_url": INSTITUTIONAL_THESIS_URL,
                "final_url": thesis.final_url,
                "sha256": hashlib.sha256(thesis.body).hexdigest(),
                "byte_size": len(thesis.body),
                "content_type": thesis.content_type,
                "calibration_page_index_zero_based": calibration_index,
                "validation_page_index_zero_based": validation_index,
                "prediction_table_page_index_zero_based": table_index,
                "anchors": calibration_anchors + table_anchors,
                "raw_source_bytes_persisted": False,
            },
        ],
        "article_identity": {
            "title": ARTICLE_TITLE,
            "doi": ARTICLE_DOI,
            "authors": list(ARTICLE_AUTHORS),
            "publication_year": 2019,
        },
        "model_identity": {
            "model_id": "kollmannsberger-2019-anisotropic-conductivity",
            "model_class": (
                "published_thermal_phase_change_anisotropic_conductivity"
            ),
            "computational_evidence_class": (
                "published_computational_retrospective"
            ),
        },
        "calibration_record": {
            "parameter_fit_case_ids": ["B"],
            "reported_anisotropic_conductivity_scalars": dict(
                _CALIBRATION_PARAMETERS
            ),
            "parameters_reported_fixed_for_validation_case_ids": ["A", "C"],
        },
        "published_predictions": [
            {
                "case_id": case_id,
                "melt_pool_length_um": values["length_um"],
                "melt_pool_width_mean_um": values["width_um"],
                "melt_pool_depth_mean_um": values["depth_um"],
            }
            for case_id, values in _PUBLISHED_VALUES.items()
        ],
        "retrospective_scope": {
            "case_b_parameter_calibration_reported": True,
            "a_c_parameters_reported_fixed_after_case_b_calibration": True,
            "strict_prospective_holdout_model_selection_established": False,
            "reason": (
                "The publication describes a model-form update to anisotropic "
                "conductivity during retrospective analysis of AMMT discrepancies. "
                "This evidence therefore does not establish that A/C responses were "
                "unavailable to model-form selection."
            ),
            "eligible_claim": "retrospective_published_model_comparison",
            "ineligible_claim": "strict_blind_holdout_validation",
        },
        "authority_boundary": {
            "empirical_measurement_created": False,
            "published_values_promoted_to_empirical": False,
            "strict_blind_validation_claimed": False,
            "engineering_readiness_established": False,
            "scientific_status_promoted": False,
        },
    }
    report["report_sha256"] = canonical_sha256(report)
    return report


def _authenticate_evidence(
    evidence: Mapping[str, Any],
    *,
    trusted_evidence_sha256: str,
) -> dict[str, Any]:
    trusted = _sha(trusted_evidence_sha256, "trusted_evidence_sha256")
    snapshot = copy.deepcopy(dict(evidence))
    _require(
        canonical_sha256(snapshot) == trusted,
        (
            "published comparator evidence does not match external "
            "trust-root SHA-256"
        ),
    )
    embedded = _sha(
        snapshot.pop("report_sha256", None),
        "evidence.report_sha256",
    )
    _require(
        canonical_sha256(snapshot) == embedded,
        "published evidence self-hash mismatch",
    )
    snapshot["report_sha256"] = embedded
    scope = snapshot.get("retrospective_scope")
    calibration = snapshot.get("calibration_record")
    boundary = snapshot.get("authority_boundary")
    _require(isinstance(scope, Mapping), "retrospective scope is missing")
    _require(isinstance(calibration, Mapping), "calibration record is missing")
    _require(isinstance(boundary, Mapping), "authority boundary is missing")
    _require(
        calibration.get("parameter_fit_case_ids") == ["B"]
        and calibration.get("parameters_reported_fixed_for_validation_case_ids")
        == ["A", "C"],
        "published comparator calibration partition drifted",
    )
    _require(
        scope.get("case_b_parameter_calibration_reported") is True
        and scope.get("a_c_parameters_reported_fixed_after_case_b_calibration")
        is True
        and scope.get("strict_prospective_holdout_model_selection_established")
        is False
        and scope.get("eligible_claim")
        == "retrospective_published_model_comparison"
        and scope.get("ineligible_claim") == "strict_blind_holdout_validation",
        "published comparator retrospective boundary drifted",
    )
    _require(
        boundary.get("empirical_measurement_created") is False
        and boundary.get("published_values_promoted_to_empirical") is False
        and boundary.get("strict_blind_validation_claimed") is False
        and boundary.get("engineering_readiness_established") is False
        and boundary.get("scientific_status_promoted") is False,
        "published comparator authority was widened",
    )
    return snapshot


def evaluate_kollmannsberger_retrospective_comparator(
    contract: Mapping[str, Any],
    evidence: Mapping[str, Any],
    *,
    trusted_contract_sha256: str,
    trusted_evidence_sha256: str,
    repository_root: str,
) -> dict[str, Any]:
    """Compare published A/C predictions to current frozen NIST responses."""

    frozen = _authenticate_contract(
        contract,
        trusted_contract_sha256=trusted_contract_sha256,
    )
    source = _authenticate_evidence(
        evidence,
        trusted_evidence_sha256=trusted_evidence_sha256,
    )
    predictions_raw = source.get("published_predictions")
    _require(
        isinstance(predictions_raw, list),
        "published predictions are missing",
    )
    predictions: dict[str, Mapping[str, Any]] = {}
    for index, item in enumerate(predictions_raw):
        _require(
            isinstance(item, Mapping),
            f"published_predictions[{index}] must be an object",
        )
        case_id = item.get("case_id")
        if case_id not in HOLDOUT_CASES:
            continue
        normalized_case_id = str(case_id)
        _require(
            normalized_case_id not in predictions,
            f"duplicate published holdout prediction case_id: {normalized_case_id}",
        )
        predictions[normalized_case_id] = item
    _require(
        set(predictions) == set(HOLDOUT_CASES),
        "published A/C prediction coverage incomplete",
    )

    _process_rows, response_rows = _validated_sources(repository_root)
    observed = {
        case_id: _case_response_summary(response_rows, case_id)
        for case_id in HOLDOUT_CASES
    }

    case_metrics: list[dict[str, Any]] = []
    width_errors: list[float] = []
    depth_errors: list[float] = []
    for case_id in HOLDOUT_CASES:
        row = predictions[case_id]
        obs = observed[case_id]
        response_metrics: dict[str, Any] = {}
        for short, field in (
            ("width", "melt_pool_width_mean_um"),
            ("depth", "melt_pool_depth_mean_um"),
        ):
            prediction_value = _number(row.get(field), f"{case_id}.{field}")
            observed_value = _number(
                obs[short]["trace_mean_average_um"],
                f"{case_id}.observed_{short}",
            )
            error = abs(prediction_value - observed_value)
            relative = (
                error / abs(observed_value)
                if observed_value != 0.0
                else None
            )
            sd = obs[short]["trace_mean_sample_sd_um"]
            normalized = (
                error / float(sd)
                if isinstance(sd, (int, float))
                and not isinstance(sd, bool)
                and math.isfinite(float(sd))
                and float(sd) > 0.0
                else None
            )
            low, high = obs[short]["trace_mean_range_um"]
            response_metrics[short] = {
                "published_prediction_um": prediction_value,
                "observed_trace_mean_average_um": observed_value,
                "observed_trace_mean_sample_sd_um": sd,
                "observed_trace_mean_range_um": [low, high],
                "absolute_error_um": error,
                "relative_error_fraction": relative,
                "absolute_error_over_trace_mean_sample_sd": normalized,
                "prediction_within_observed_trace_mean_range": (
                    low <= prediction_value <= high
                ),
                "trace_spread_is_calibrated_uncertainty_interval": False,
            }
            if short == "width":
                width_errors.append(error)
            else:
                depth_errors.append(error)
        case_metrics.append(
            {
                "case_id": case_id,
                "responses": response_metrics,
            }
        )

    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "evaluation_type": (
            "published_retrospective_amb2018_02_ac_comparison"
        ),
        "benchmark_contract_sha256": frozen["contract_sha256"],
        "published_evidence_sha256": source["report_sha256"],
        "model_identity": copy.deepcopy(source["model_identity"]),
        "calibration_record": copy.deepcopy(source["calibration_record"]),
        "case_metrics": case_metrics,
        "aggregate_ac_metrics": {
            "width_mae_um": _mean(width_errors),
            "depth_mae_um": _mean(depth_errors),
            "case_count": len(HOLDOUT_CASES),
            "case_b_included": False,
        },
        "scientific_interpretation": {
            "parameter_fit_reported_case_b_only": True,
            "published_parameters_fixed_for_a_c": True,
            "strict_blind_model_selection_established": False,
            "eligible_as_strict_phase1_holdout_prediction": False,
            "eligible_as_retrospective_published_comparator": True,
        },
        "scientific_boundary": {
            "published_computational_result_is_empirical": False,
            "agreement_establishes_causality": False,
            "agreement_establishes_mechanistic_uniqueness": False,
            "prospective_blind_validation_established": False,
            "engineering_readiness_established": False,
            "scientific_status_promoted": False,
        },
    }
    result["evaluation_sha256"] = canonical_sha256(result)
    return result


__all__ = [
    "ARTICLE_DOI",
    "ARTICLE_METADATA_URL",
    "ARTICLE_TITLE",
    "INSTITUTIONAL_THESIS_URL",
    "In625PublishedComparatorError",
    "acquire_kollmannsberger_retrospective_evidence",
    "evaluate_kollmannsberger_retrospective_comparator",
]
