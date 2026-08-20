"""Fail-closed structural intake for bounded UTF-8 delimited artifacts.

This adapter exists so a previously unseen CSV/TSV/text table can become structurally
inspectable without writing source-specific code first. It deliberately stops before
materials-science semantics: rows are not specimens, header tokens are not trusted units,
and apparent replicate/sample identifiers are proposal-only hints.
"""
from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from .kernel import ResearchLoopError

DELIMITED_STRUCTURAL_INTAKE_SCHEMA_VERSION = "1.0"
DEFAULT_MAX_DELIMITED_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_ROWS = 50_000
DEFAULT_MAX_COLUMNS = 256
DEFAULT_MAX_CELL_CHARACTERS = 16_384
DEFAULT_PREVIEW_ROWS = 5
DEFAULT_PROFILE_UNIQUE_VALUES = 10_000

_DELIMITER_NAMES = {",": "comma", "\t": "tab", ";": "semicolon", "|": "pipe"}
_HINT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("identity_like", re.compile(r"(?:^|[^a-z])(sample|specimen|coupon|cell|track|image|file|id)(?:[^a-z]|$)", re.I)),
    ("replicate_like", re.compile(r"(?:replicate|repeat|trial|run)(?:[^a-z]|$)", re.I)),
    ("time_like", re.compile(r"(?:^|[^a-z])(time|timestamp|cycle)(?:[^a-z]|$)", re.I)),
    ("frequency_like", re.compile(r"(?:frequency|freq|hz)(?:[^a-z]|$)", re.I)),
    ("temperature_like", re.compile(r"(?:temperature|temp)(?:[^a-z]|$)", re.I)),
    ("measurement_like", re.compile(r"(?:voltage|current|power|width|depth|height|stress|strain|resistance|impedance)(?:[^a-z]|$)", re.I)),
)


class DelimitedStructuralIntakeError(ResearchLoopError):
    """Raised when delimited structural intake cannot be performed safely."""


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise DelimitedStructuralIntakeError(f"{field} must be a positive integer")
    return value


def _decode_utf8(raw: bytes) -> str:
    if not isinstance(raw, bytes) or not raw:
        raise DelimitedStructuralIntakeError("artifact_bytes must be non-empty exact bytes")
    if b"\x00" in raw:
        raise DelimitedStructuralIntakeError("artifact contains NUL bytes and is not accepted as text")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DelimitedStructuralIntakeError("artifact is not valid UTF-8 text") from exc
    if not text.strip():
        raise DelimitedStructuralIntakeError("artifact contains no non-whitespace text")
    return text


def _sample_lines(text: str, *, maximum: int = 64) -> list[str]:
    lines: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        lines.append(line)
        if len(lines) >= maximum:
            break
    if len(lines) < 2:
        raise DelimitedStructuralIntakeError("artifact has too few non-empty rows for tabular intake")
    return lines


def _parse_sample(lines: Sequence[str], delimiter: str) -> tuple[list[list[str]], tuple[int, int, int]] | None:
    try:
        rows = list(csv.reader(lines, delimiter=delimiter, strict=True))
    except csv.Error:
        return None
    widths = [len(row) for row in rows]
    multi = [width for width in widths if width >= 2]
    if len(multi) < max(2, math.ceil(len(rows) * 0.8)):
        return None
    counts = Counter(widths)
    modal_width, modal_count = counts.most_common(1)[0]
    if modal_width < 2:
        return None
    # Prefer a delimiter that produces a stable rectangular interpretation, then more
    # columns. A tie is rejected later rather than guessed.
    return rows, (modal_count, modal_width, -len(counts))


def _detect_delimiter(text: str, *, delimiter_hint: str | None = None) -> str:
    if delimiter_hint is not None:
        if delimiter_hint not in _DELIMITER_NAMES:
            raise DelimitedStructuralIntakeError("delimiter_hint is not an allowed delimiter")
        parsed = _parse_sample(_sample_lines(text), delimiter_hint)
        if parsed is None:
            raise DelimitedStructuralIntakeError("delimiter hint does not yield a stable tabular structure")
        return delimiter_hint

    lines = _sample_lines(text)
    candidates: list[tuple[tuple[int, int, int], str]] = []
    for delimiter in _DELIMITER_NAMES:
        parsed = _parse_sample(lines, delimiter)
        if parsed is not None:
            candidates.append((parsed[1], delimiter))
    if not candidates:
        raise DelimitedStructuralIntakeError("no safe delimited table structure detected")
    candidates.sort(reverse=True)
    best_score = candidates[0][0]
    winners = [delimiter for score, delimiter in candidates if score == best_score]
    if len(winners) != 1:
        names = sorted(_DELIMITER_NAMES[item] for item in winners)
        raise DelimitedStructuralIntakeError(
            f"delimiter detection is ambiguous between: {', '.join(names)}"
        )
    return winners[0]


def _finite_number(value: str) -> float | None:
    stripped = value.strip()
    if not stripped:
        return None
    try:
        number = float(stripped)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _header_hints(value: str) -> list[str]:
    return [name for name, pattern in _HINT_PATTERNS if pattern.search(value)]


def _profile_column(
    rows: Sequence[Sequence[str]],
    *,
    column_index: int,
    header_candidate: str,
    unique_cap: int,
) -> dict[str, Any]:
    blank_count = 0
    numeric_count = 0
    text_count = 0
    numeric_min: float | None = None
    numeric_max: float | None = None
    unique: set[str] = set()
    unique_capped = False
    nonblank_count = 0
    value_counts: Counter[str] = Counter()

    for row in rows:
        value = row[column_index] if column_index < len(row) else ""
        if value.strip() == "":
            blank_count += 1
            continue
        nonblank_count += 1
        if len(unique) < unique_cap:
            unique.add(value)
        elif value not in unique:
            unique_capped = True
        if len(value_counts) < unique_cap or value in value_counts:
            value_counts[value] += 1
        number = _finite_number(value)
        if number is None:
            text_count += 1
        else:
            numeric_count += 1
            numeric_min = number if numeric_min is None else min(numeric_min, number)
            numeric_max = number if numeric_max is None else max(numeric_max, number)

    unique_count: int | None = None if unique_capped else len(unique)
    most_common_count = value_counts.most_common(1)[0][1] if value_counts else 0
    repeated_fraction = most_common_count / nonblank_count if nonblank_count else None
    return {
        "column_index": column_index,
        "header_candidate": header_candidate,
        "header_semantic_hints_proposal_only": _header_hints(header_candidate),
        "observed_data_row_count": len(rows),
        "nonblank_count": nonblank_count,
        "blank_count": blank_count,
        "numeric_count": numeric_count,
        "text_count": text_count,
        "numeric_min_structural_only": numeric_min,
        "numeric_max_structural_only": numeric_max,
        "unique_count": unique_count,
        "unique_count_capped": unique_capped,
        "constant_nonblank_signal": nonblank_count > 0 and unique_count == 1,
        "most_common_value_fraction": repeated_fraction,
        "row_values_are_independent_specimens": False,
    }


def inspect_delimited_structure(
    artifact_bytes: bytes,
    *,
    delimiter_hint: str | None = None,
    max_bytes: int = DEFAULT_MAX_DELIMITED_BYTES,
    max_rows: int = DEFAULT_MAX_ROWS,
    max_columns: int = DEFAULT_MAX_COLUMNS,
    max_cell_characters: int = DEFAULT_MAX_CELL_CHARACTERS,
    preview_rows: int = DEFAULT_PREVIEW_ROWS,
    unique_value_cap: int = DEFAULT_PROFILE_UNIQUE_VALUES,
) -> dict[str, Any]:
    """Inspect bounded delimited text without assigning scientific semantics."""
    max_bytes = _positive_int(max_bytes, "max_bytes")
    max_rows = _positive_int(max_rows, "max_rows")
    max_columns = _positive_int(max_columns, "max_columns")
    max_cell_characters = _positive_int(max_cell_characters, "max_cell_characters")
    preview_rows = _positive_int(preview_rows, "preview_rows")
    unique_value_cap = _positive_int(unique_value_cap, "unique_value_cap")
    if not isinstance(artifact_bytes, bytes) or not artifact_bytes:
        raise DelimitedStructuralIntakeError("artifact_bytes must be non-empty exact bytes")
    if len(artifact_bytes) > max_bytes:
        raise DelimitedStructuralIntakeError("artifact exceeds delimited structural intake byte ceiling")

    text = _decode_utf8(artifact_bytes)
    delimiter = _detect_delimiter(text, delimiter_hint=delimiter_hint)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
    rows: list[list[str]] = []
    try:
        for row_index, row in enumerate(reader, start=1):
            if row_index > max_rows:
                raise DelimitedStructuralIntakeError("artifact exceeds delimited structural intake row ceiling")
            if len(row) > max_columns:
                raise DelimitedStructuralIntakeError("artifact exceeds delimited structural intake column ceiling")
            if any(len(cell) > max_cell_characters for cell in row):
                raise DelimitedStructuralIntakeError("artifact contains a cell above the character ceiling")
            rows.append(row)
    except csv.Error as exc:
        raise DelimitedStructuralIntakeError("artifact contains malformed delimited text") from exc

    if len(rows) < 2:
        raise DelimitedStructuralIntakeError("artifact has fewer than two parsed rows")
    widths = [len(row) for row in rows]
    max_width = max(widths)
    min_width = min(widths)
    if max_width < 2:
        raise DelimitedStructuralIntakeError("artifact does not expose at least two columns")

    header = rows[0]
    data_rows = rows[1:]
    header_candidates = [header[index] if index < len(header) else "" for index in range(max_width)]
    profiles = [
        _profile_column(
            data_rows,
            column_index=index,
            header_candidate=header_candidates[index],
            unique_cap=unique_value_cap,
        )
        for index in range(max_width)
    ]
    row_width_counts = {str(width): count for width, count in sorted(Counter(widths).items())}

    return {
        "schema_version": DELIMITED_STRUCTURAL_INTAKE_SCHEMA_VERSION,
        "artifact_sha256": hashlib.sha256(artifact_bytes).hexdigest(),
        "artifact_size_bytes": len(artifact_bytes),
        "encoding": "utf-8",
        "delimiter": delimiter,
        "delimiter_name": _DELIMITER_NAMES[delimiter],
        "parsed_row_count": len(rows),
        "data_row_count_if_first_row_is_header": len(data_rows),
        "minimum_column_count": min_width,
        "maximum_column_count": max_width,
        "rectangular": min_width == max_width,
        "row_width_counts": row_width_counts,
        "first_row_header_candidate": header_candidates,
        "preview_rows": rows[:preview_rows],
        "column_profiles": profiles,
        "accepted_for_analysis": False,
        "requires_domain_mapping": True,
        "structural_parse_is_scientific_validation": False,
        "measurement_semantics_interpreted": False,
        "units_interpreted": False,
        "sample_identity_inferred": False,
        "replicate_independence_inferred": False,
        "calibration_semantics_interpreted": False,
        "scientific_support_established": False,
        "scientific_status_changed": False,
        "limitations": [
            "The first row is exposed only as a header candidate; header text is not trusted scientific metadata.",
            "Parsed rows, repeated measurements, time points, frequencies, and image rows are never counted as independent specimens by this adapter.",
            "Numeric ranges, missingness, constant columns, and repeated-value fractions are structural diagnostics only.",
            "Sample identity, units, calibration, material state, measurement semantics, and replicate independence require a domain-specific intake or review contract.",
        ],
    }


def structural_intake_acquired_delimited(
    *,
    receipt: Mapping[str, Any],
    package_directory: str | Path,
    evidence_gap: object,
) -> dict[str, Any]:
    """Inspect an acquired delimited artifact while preserving its receipt SHA binding."""
    artifact_path = receipt.get("artifact_path")
    expected_sha = receipt.get("artifact_sha256")
    if not isinstance(artifact_path, str):
        raise DelimitedStructuralIntakeError("receipt artifact_path must be a string")
    suffix = Path(artifact_path).suffix.lower()
    if suffix not in {".csv", ".tsv", ".txt"}:
        raise DelimitedStructuralIntakeError("receipt artifact_path is not a supported delimited suffix")
    if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        raise DelimitedStructuralIntakeError("receipt artifact_sha256 is invalid")
    relative = PurePosixPath(artifact_path)
    if relative.is_absolute() or "." in relative.parts or ".." in relative.parts or "\\" in artifact_path:
        raise DelimitedStructuralIntakeError("receipt artifact_path is not safe relative POSIX")
    root = Path(package_directory).resolve(strict=True)
    target = root.joinpath(*relative.parts)
    if target.is_symlink():
        raise DelimitedStructuralIntakeError("acquired delimited artifact may not be a symlink")
    resolved = target.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise DelimitedStructuralIntakeError("acquired artifact resolves outside package directory") from exc
    raw = resolved.read_bytes()
    observed_sha = hashlib.sha256(raw).hexdigest()
    if observed_sha != expected_sha:
        raise DelimitedStructuralIntakeError("acquired delimited artifact no longer matches receipt SHA-256")

    delimiter_hint = "\t" if suffix == ".tsv" else None
    structure = inspect_delimited_structure(raw, delimiter_hint=delimiter_hint)
    return {
        "decision": "requires_domain_scientific_mapping",
        "accepted_for_analysis": False,
        "scientific_status_changed": False,
        "artifact_sha256": observed_sha,
        "package_directory": root.as_posix(),
        "evidence_gap": evidence_gap,
        "delimited_structure": structure,
        "reason_codes": ["structural_intake_complete_domain_semantics_unresolved"],
    }


__all__ = [
    "DEFAULT_MAX_CELL_CHARACTERS",
    "DEFAULT_MAX_COLUMNS",
    "DEFAULT_MAX_DELIMITED_BYTES",
    "DEFAULT_MAX_ROWS",
    "DELIMITED_STRUCTURAL_INTAKE_SCHEMA_VERSION",
    "DelimitedStructuralIntakeError",
    "inspect_delimited_structure",
    "structural_intake_acquired_delimited",
]
