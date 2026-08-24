"""Scope-correct facade over the reviewed Weaver full-text acquisition implementation.

The underlying acquisition, identity checks, claim matching, source restrictions and authority
logic remain byte-for-byte unchanged. This facade corrects one output vocabulary defect: the
AMMT primary-text claim establishes fixed 195 W / 800 mm/s scans with *increasing spot diameter*;
it does not independently establish the separately sourced Naderi/mds2 numeric 50–256 µm range.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from . import weaver_2021_full_text_acquisition_impl as _impl

NEXT_ACTION_CLASS = _impl.NEXT_ACTION_CLASS
MAX_CLAIM_SPAN_CHARS = _impl.MAX_CLAIM_SPAN_CHARS
IMPLEMENTATION_ID = _impl.IMPLEMENTATION_ID
FACTORY_ID = _impl.FACTORY_ID
REQUIRED_VERIFIED_PRIMITIVES = _impl.REQUIRED_VERIFIED_PRIMITIVES
Weaver2021FullTextAcquisitionError = _impl.Weaver2021FullTextAcquisitionError
Fetcher = _impl.Fetcher
_canonical_sha = _impl._canonical_sha
build_derived_weaver_authorization = _impl.build_derived_weaver_authorization

_OLD_AMMT_SCOPE_KEY = "ammt_195w_800_condition_and_spot_range_established"
_AMMT_SCOPE_KEY = "ammt_195w_800_condition_with_increasing_spot_diameter_established"


def execute_derived_weaver_acquisition(*, authorization: Mapping[str, Any], fetcher: Fetcher = _impl.fetch_exact_source) -> dict[str, Any]:
    """Execute reviewed acquisition and expose the AMMT evidence scope without range overclaim."""

    report = _impl.execute_derived_weaver_acquisition(
        authorization=authorization,
        fetcher=fetcher,
    )
    scope = report.get("evidence_scope")
    if not isinstance(scope, Mapping):
        raise Weaver2021FullTextAcquisitionError("Weaver evidence_scope is missing")
    if _OLD_AMMT_SCOPE_KEY not in scope:
        raise Weaver2021FullTextAcquisitionError("reviewed Weaver AMMT scope field is missing")
    if _AMMT_SCOPE_KEY in scope:
        raise Weaver2021FullTextAcquisitionError("Weaver AMMT scope field is duplicated")

    corrected_scope = dict(scope)
    established = corrected_scope.pop(_OLD_AMMT_SCOPE_KEY)
    corrected_scope[_AMMT_SCOPE_KEY] = established

    corrected = dict(report)
    corrected["evidence_scope"] = corrected_scope
    corrected.pop("report_sha256_without_self_field", None)
    corrected["report_sha256_without_self_field"] = _canonical_sha(corrected)
    return corrected


__all__ = [
    "FACTORY_ID",
    "IMPLEMENTATION_ID",
    "MAX_CLAIM_SPAN_CHARS",
    "NEXT_ACTION_CLASS",
    "REQUIRED_VERIFIED_PRIMITIVES",
    "Weaver2021FullTextAcquisitionError",
    "build_derived_weaver_authorization",
    "execute_derived_weaver_acquisition",
]
