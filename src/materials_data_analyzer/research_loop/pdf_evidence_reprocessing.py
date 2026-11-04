"""Offline reprocessing of immutable evidence with the approved safe PDF runtime.

Historical receipts are observations, not instructions to install their parser.
Only the separately pinned checkout contract can authorize source-level review.
No caller-authored report, digest or contract grants scientific authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from ..pdf_runtime import CURRENT_PYPDF_VERSION, require_current_pdf_parser
from . import in625_geometry_condition_source_acquisition as acquisition

CONTRACT_PATH = "configs/research/pdf_evidence_reprocessing.v1.json"
CONTRACT_SHA256 = "55856da65b30107ce8bb5513b05cc0f169c311fd72c7e389c21c5df98747d158"
HISTORICAL_PATH = "configs/research/in625_geometry_condition_multisource_reviewed_witness.v1.json"
HISTORICAL_SHA256 = "923eb2158a29541eacd6f1b6bbdace77ac2fa52e0365572f4953e00e12715589"
REGISTRY_PATH = "configs/research/in625_geometry_condition_source_reconnaissance.v1.json"
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024


class EvidenceReprocessingError(ValueError):
    """Evidence cannot be promoted to a completed source-review contract."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceReprocessingError("duplicate evidence JSON key")
        result[key] = value
    return result


def _trusted_json(relative: str, expected: str) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[3]
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to(root) or path.stat().st_size > 512 * 1024:
        raise EvidenceReprocessingError("trusted evidence record escaped its path/byte budget")
    raw = path.read_bytes()
    if _sha(raw) != expected:
        raise EvidenceReprocessingError("trusted evidence record identity drifted")
    value = json.loads(raw, object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise EvidenceReprocessingError("trusted evidence record must be an object")
    return value


def _load_contract() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    contract = _trusted_json(CONTRACT_PATH, CONTRACT_SHA256)
    historical = _trusted_json(HISTORICAL_PATH, HISTORICAL_SHA256)
    registry = _trusted_json(REGISTRY_PATH, contract["registry_sha256"])
    if (contract["schema_version"] != "1.0"
            or contract["historical_witness_sha256"] != HISTORICAL_SHA256
            or contract["parser"] != {"package": "pypdf", "version": CURRENT_PYPDF_VERSION,
                                      "strict": False}):
        raise EvidenceReprocessingError("review contract/parser identity drifted")
    return contract, historical, registry


def _claim_observation(rule: Mapping[str, Any], pages: list[str]) -> dict[str, Any]:
    """Check linked quantities/units in a bounded, explicitly reviewed context.

    Regexes and scopes come only from pinned checkout rules. No whitespace or
    glyph normalization is applied to quantities beyond the established source
    text extraction. These are source assertions, never measurement transfer.
    """
    page_index = rule["page_index_zero_based"]
    if not isinstance(page_index, int) or isinstance(page_index, bool) or not 0 <= page_index < len(pages):
        raise EvidenceReprocessingError("reviewed claim page is absent")
    page = pages[page_index]
    spans = list(re.finditer(rule["context_regex"], page, re.IGNORECASE))
    if len(spans) != 1 or len(spans[0].group().encode()) > 4096:
        raise EvidenceReprocessingError("reviewed claim context is absent, ambiguous or exceeds budget")
    context = spans[0].group()
    quantities = []
    for quantity in rule["quantities"]:
        matches = list(re.finditer(quantity["pattern"], context))
        if len(matches) != 1:
            raise EvidenceReprocessingError("reviewed quantity is absent or ambiguous")
        groups = matches[0].groupdict()
        try:
            observed = Decimal(groups["value"])
            expected = Decimal(quantity["value"])
        except (InvalidOperation, KeyError) as exc:
            raise EvidenceReprocessingError("reviewed quantity is malformed") from exc
        if not observed.is_finite() or observed != expected or groups.get("unit") != quantity["unit"]:
            raise EvidenceReprocessingError("reviewed numeric value or unit changed")
        quantities.append({"name": quantity["name"], "value": str(observed),
                           "unit": groups["unit"]})
    return {
        "claim_id": rule["claim_id"], "scope": rule["scope"],
        "page_index_zero_based": page_index,
        "context_text": context,
        "context_sha256": _sha(context.encode()), "context_utf8_bytes": len(context.encode()),
        "quantities": quantities, "context_check_passed": True,
    }


def reprocess_retained_sources(retained: Mapping[str, bytes]) -> dict[str, Any]:
    """Re-extract exact originals; report missing evidence without inventing it.

    This function never fetches, writes, imports a historical parser or trusts a
    serialized new result. Its caller must retain original bytes separately.
    """
    require_current_pdf_parser()
    contract, historical, registry = _load_contract()
    historical_sources = {item["source_id"]: item for item in historical["sources"]}
    registered = {item["source_id"]: item for item in registry["sources"]}
    specs = {**historical_sources,
             **{item["source_id"]: item for item in contract["additional_sources"]}}
    if set(retained) - set(specs):
        raise EvidenceReprocessingError("unregistered retained source")
    if any(not isinstance(raw, bytes) or len(raw) > MAX_SOURCE_BYTES for raw in retained.values()):
        raise EvidenceReprocessingError("retained source exceeds type/byte budget")
    if sum(map(len, retained.values())) > MAX_TOTAL_BYTES:
        raise EvidenceReprocessingError("retained evidence exceeds cumulative byte budget")
    results = []
    for source_id, spec in specs.items():
        old = historical_sources.get(source_id)
        review = contract["source_reviews"][source_id]
        result: dict[str, Any] = {
            "source_id": source_id, "requested_url": spec["requested_url"],
            "source_sha256": spec["source_sha256"], "media_type": spec["media_type"],
            "source_metadata": {key: spec.get(key) for key in
                                ("title", "authors", "doi", "publication_date", "authority")},
            "lineage": "historical_original" if old else "new_source_observation",
            "historical_claim_receipts": old["claims"] if old else [],
            "technical_checks_passed": False, "source_review_complete": False,
            "physical_or_model_validation_demonstrated": False,
        }
        raw = retained.get(source_id)
        if raw is None:
            result["status"] = "missing_original" if old else "missing_source_observation"
            results.append(result)
            continue
        if len(raw) != spec["source_size_bytes"] or _sha(raw) != spec["source_sha256"]:
            raise EvidenceReprocessingError(f"{source_id}: source identity changed")
        if spec["media_type"] == "pdf":
            pages = acquisition._pdf_pages(raw, source_id=source_id, content_type="application/pdf")
        elif spec["media_type"] == "html":
            pages = acquisition._html_pages(raw)
        else:
            raise EvidenceReprocessingError("unsupported evidence media type")
        new_claims = []
        if old:
            for claim in registered[source_id]["claims_under_review"]:
                new_claims.append(acquisition._claim_receipt(claim, pages, is_pdf=spec["media_type"] == "pdf"))
            if any(not claim["matched"] for claim in new_claims):
                raise EvidenceReprocessingError(f"{source_id}: historical claim context no longer matches")
        result["reprocessed_claim_receipts"] = new_claims
        comparisons = []
        for before, after in zip(result["historical_claim_receipts"], new_claims, strict=True):
            comparisons.append({"claim_id": before["claim_id"],
                                "extraction_receipt_equal": before["matches"] == after["matches"]})
        result["historical_comparison"] = comparisons
        result["reviewed_claim_observations"] = [_claim_observation(rule, pages) for rule in review["claims"]]
        result["technical_checks_passed"] = True
        expected_claims = {item["claim_id"] for item in spec["claims"]}
        reviewed_claims = {item["claim_id"] for item in review["claims"]}
        complete = (review["review_status"] == "reviewed"
                    and isinstance(review["review_reference"], str) and bool(review["review_reference"].strip())
                    and reviewed_claims == expected_claims and bool(expected_claims))
        result["source_review_complete"] = complete
        result["status"] = "source_review_complete" if complete else "reprocessed_pending_review"
        results.append(result)
    return {
        "schema_version": "1.0", "contract_id": contract["contract_id"],
        "contract_sha256": CONTRACT_SHA256, "parser": contract["parser"],
        "historical_witness_sha256": HISTORICAL_SHA256,
        "network_requests_performed": 0, "historical_records_rewritten": False,
        "all_originals_present": all(item["source_id"] in retained for item in historical["sources"]),
        "complete_source_review": all(item["source_review_complete"] for item in results),
        "physical_or_model_validation_demonstrated": False, "sources": results,
    }


def verify_reprocessed_sources(retained: Mapping[str, bytes]) -> dict[str, Any]:
    """Recompute from source bytes; never accept caller-authored success flags."""
    result = reprocess_retained_sources(retained)
    if not result["complete_source_review"]:
        raise EvidenceReprocessingError("source review incomplete: originals missing or review pending")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", default=[], metavar="SOURCE_ID=PATH")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; preserve previous research records")
    retained = {}
    total = 0
    for binding in args.source:
        source_id, separator, path = binding.partition("=")
        if not separator or not source_id or source_id in retained:
            parser.error("source bindings must be unique SOURCE_ID=PATH entries")
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_SOURCE_BYTES + 1)
        total += len(raw)
        if len(raw) > MAX_SOURCE_BYTES or total > MAX_TOTAL_BYTES:
            parser.error("retained source input exceeds byte budget")
        retained[source_id] = raw
    result = reprocess_retained_sources(retained)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return 0 if result["complete_source_review"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
