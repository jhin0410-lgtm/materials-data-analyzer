"""Public characterization-bundle trust boundary.

The schema-aware implementation is kept in ``_characterization_bundle_ladder_core``.
This facade adds the consumer-owned material-domain binding required for schema 1.1:
a producer ladder cannot claim maturity for a source material domain that is absent
from (or ambiguous in) the checksum-bound sample context.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from . import _characterization_bundle_ladder_core as _core

BUNDLE_SCHEMA_VERSION = _core.BUNDLE_SCHEMA_VERSION
EVIDENCE_LADDER_BUNDLE_SCHEMA_VERSION = _core.EVIDENCE_LADDER_BUNDLE_SCHEMA_VERSION
SUPPORTED_BUNDLE_SCHEMA_VERSIONS = _core.SUPPORTED_BUNDLE_SCHEMA_VERSIONS
BUNDLE_TYPE = _core.BUNDLE_TYPE
CONSUMER_SCHEMA_VERSION = _core.CONSUMER_SCHEMA_VERSION
SUMMARY_NAME = _core.SUMMARY_NAME
REPORT_NAME = _core.REPORT_NAME
MANIFEST_NAME = _core.MANIFEST_NAME
NORMALIZED_INPUT_NAME = _core.NORMALIZED_INPUT_NAME
EXTERNAL_PROCESS_INPUT_NAME = _core.EXTERNAL_PROCESS_INPUT_NAME
UNIT_LABEL_RULE = _core.UNIT_LABEL_RULE
PROCESS_IDENTITY_COLUMNS = _core.PROCESS_IDENTITY_COLUMNS
ValidatedCharacterizationBundle = _core.ValidatedCharacterizationBundle
ValidatedProcessInput = _core.ValidatedProcessInput
validate_external_process_input = _core.validate_external_process_input

_MATERIAL_CONTEXT_FIELDS = (
    "source_material_domain",
    "material",
    "material_name",
)


def _normalized_material_value(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"schema-1.1 sample context contains blank {field} material-domain values"
        )
    return value.strip().casefold()


def _validate_ladder_material_domain_binding(
    bundle: ValidatedCharacterizationBundle,
) -> None:
    """Bind one declared ladder source domain to checksum-bound sample context.

    Schema 1.1 deliberately fails closed when the context has no material-domain field
    or describes multiple source material domains. A single evidence ladder must not
    silently summarize heterogeneous materials without an explicit producer-side domain
    identifier.
    """
    assessment = bundle.evidence_ladder_assessment
    if assessment is None:
        raise ValueError(
            "schema-1.1 characterization bundle is missing a verified evidence ladder"
        )
    declaration = assessment.get("declaration")
    if not isinstance(declaration, Mapping):
        raise ValueError("verified evidence ladder is missing declaration")
    subject = declaration.get("subject")
    if not isinstance(subject, Mapping):
        raise ValueError("verified evidence ladder is missing declaration.subject")
    declared_domain = subject.get("source_material_domain")
    if not isinstance(declared_domain, str) or not declared_domain.strip():
        raise ValueError(
            "verified evidence ladder source_material_domain must be non-empty"
        )

    context = bundle.sample_context
    field = next(
        (candidate for candidate in _MATERIAL_CONTEXT_FIELDS if candidate in context.columns),
        None,
    )
    if field is None:
        raise ValueError(
            "schema-1.1 characterization bundle requires a checksum-bound sample-context "
            "material domain field (source_material_domain, material, or material_name)"
        )

    raw_values = context[field].astype("string").str.strip()
    if raw_values.isna().any() or raw_values.eq("").any():
        raise ValueError(
            f"schema-1.1 sample context contains blank {field} material-domain values"
        )
    normalized_values = {
        _normalized_material_value(str(value), field=field)
        for value in raw_values.astype(str)
    }
    if len(normalized_values) != 1:
        raise ValueError(
            "schema-1.1 evidence ladder requires exactly one checksum-bound source "
            f"material domain; {field} contains {len(normalized_values)} distinct values"
        )
    contextual_domain = next(iter(normalized_values))
    if declared_domain.strip().casefold() != contextual_domain:
        raise ValueError(
            "scientific evidence-ladder source_material_domain does not match the "
            f"checksum-bound sample context {field}"
        )


def validate_characterization_bundle(
    manifest_path: str | Path,
) -> ValidatedCharacterizationBundle:
    """Validate a characterization bundle and its consumer-owned domain binding."""
    bundle = _core.validate_characterization_bundle(manifest_path)
    if bundle.manifest.get("schema_version") == EVIDENCE_LADDER_BUNDLE_SCHEMA_VERSION:
        _validate_ladder_material_domain_binding(bundle)
    return bundle


def consume_characterization_bundle(
    manifest_path: str | Path,
    output_dir: str | Path,
    *,
    process_table_path: str | Path | None = None,
) -> dict[str, Path]:
    """Consume only after the public schema/material trust boundary has passed."""
    # Do not let the internal schema-aware consumer become a bypass around the stronger
    # public material-domain binding. It will re-run its own lower-level validation.
    validate_characterization_bundle(manifest_path)
    return _core.consume_characterization_bundle(
        manifest_path,
        output_dir,
        process_table_path=process_table_path,
    )


__all__ = [
    "BUNDLE_SCHEMA_VERSION",
    "EVIDENCE_LADDER_BUNDLE_SCHEMA_VERSION",
    "SUPPORTED_BUNDLE_SCHEMA_VERSIONS",
    "BUNDLE_TYPE",
    "CONSUMER_SCHEMA_VERSION",
    "SUMMARY_NAME",
    "REPORT_NAME",
    "MANIFEST_NAME",
    "NORMALIZED_INPUT_NAME",
    "EXTERNAL_PROCESS_INPUT_NAME",
    "UNIT_LABEL_RULE",
    "ValidatedCharacterizationBundle",
    "ValidatedProcessInput",
    "consume_characterization_bundle",
    "validate_characterization_bundle",
    "validate_external_process_input",
]
