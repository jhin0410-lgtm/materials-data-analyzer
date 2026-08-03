"""Battery Archive connector and raw zip inventory helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
from typing import Any
import zipfile

import pandas as pd

from config import PROJECT_ROOT

from connectors.base import BaseConnector, IngestionResult


RAW_DIR = PROJECT_ROOT / "data" / "raw" / "battery_archive"
PROCESSED_PATH = PROJECT_ROOT / "data" / "processed" / "battery_archive_records.csv"
BATTERY_ARCHIVE_INVENTORY_COLUMNS = [
    "zip_file",
    "internal_csv_path",
    "file_name",
    "file_type",
    "uncompressed_size_bytes",
    "compressed_size_bytes",
    "crc32",
]
BATTERY_ARCHIVE_METADATA_COLUMNS = [
    "filename_stem",
    "cell_id",
    "source",
    "chemistry",
    "form_factor",
    "temperature_C",
    "soc_min_pct",
    "soc_max_pct",
    "soc_window",
    "charge_c_rate",
    "discharge_c_rate",
    "protocol_label",
    "metadata_parse_status",
    "metadata_parse_message",
]
KNOWN_CHEMISTRY_TOKENS = {"LFP", "NMC", "NCA", "LCO", "LMO"}
KNOWN_FORM_FACTOR_TOKENS = {
    "18650",
    "21700",
    "coin",
    "cylindrical",
    "pouch",
    "prism",
    "prismatic",
}
_CYCLE_SUFFIX_PATTERN = re.compile(r"_cycle_data\.csv$", re.IGNORECASE)
_TEMPERATURE_PATTERNS = [
    re.compile(r"^T(?P<value>-?\d+(?:\.\d+)?)$", re.IGNORECASE),
    re.compile(r"^(?P<value>-?\d+(?:\.\d+)?)degC$", re.IGNORECASE),
    re.compile(r"^(?P<value>-?\d+(?:\.\d+)?)C$", re.IGNORECASE),
]
_SOC_PATTERNS = [
    re.compile(
        r"^SOC(?P<minimum>\d+(?:\.\d+)?)-(?P<maximum>\d+(?:\.\d+)?)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<minimum>\d+(?:\.\d+)?)-(?P<maximum>\d+(?:\.\d+)?)(?:SOC)?$",
        re.IGNORECASE,
    ),
]
_SOC_PAIR_PATTERN = re.compile(r"^(?P<maximum>\d+(?:\.\d+)?)SOC$", re.IGNORECASE)


def _list_zip_paths(raw_dir: str | Path) -> list[Path]:
    """Return sorted Battery Archive zip paths from a local raw directory."""
    raw_path = Path(raw_dir)
    if not raw_path.exists():
        raise FileNotFoundError(
            f"Battery Archive raw directory was not found: {raw_path}"
        )
    if not raw_path.is_dir():
        raise ValueError(f"Battery Archive raw path is not a directory: {raw_path}")

    zip_paths = sorted(raw_path.glob("*.zip"), key=lambda path: path.name.casefold())
    if not zip_paths:
        raise FileNotFoundError(
            f"No Battery Archive zip files were found in raw directory: {raw_path}"
        )
    return zip_paths


def _is_cycle_data_entry(zip_info: zipfile.ZipInfo) -> bool:
    """Return whether a zip entry is a Battery Archive cycle_data CSV file."""
    if zip_info.is_dir():
        return False

    internal_path = zip_info.filename.replace("\\", "/")
    path_parts = [part for part in internal_path.split("/") if part]
    if not path_parts:
        return False
    if "__MACOSX" in path_parts:
        return False

    file_name = path_parts[-1]
    if file_name.startswith(".") or file_name.startswith("._"):
        return False

    return file_name.casefold().endswith("_cycle_data.csv")


def _unknown_metadata() -> dict[str, object]:
    """Return a default metadata payload for unparsed filename fields."""
    return {
        "filename_stem": "",
        "cell_id": "unknown",
        "source": "unknown",
        "chemistry": "unknown",
        "form_factor": "unknown",
        "temperature_C": float("nan"),
        "soc_min_pct": float("nan"),
        "soc_max_pct": float("nan"),
        "soc_window": "unknown",
        "charge_c_rate": float("nan"),
        "discharge_c_rate": float("nan"),
        "protocol_label": "unknown",
        "metadata_parse_status": "unparsed",
        "metadata_parse_message": "",
    }


def _format_numeric(value: float | int | None) -> str:
    """Format metadata numeric values without noisy trailing zeros."""
    if value is None or pd.isna(value):
        return "unknown"
    return f"{float(value):g}"


def _parse_c_rate_value(token: str) -> float | None:
    """Parse a conservative C-rate token into a numeric value."""
    value = token.strip()
    if not value:
        return None

    c_over_match = re.fullmatch(r"C/(?P<denominator>\d+(?:\.\d+)?)", value, re.I)
    if c_over_match:
        denominator = float(c_over_match.group("denominator"))
        return None if denominator == 0 else 1.0 / denominator

    c_prefix_match = re.fullmatch(r"C(?P<value>\d+(?:\.\d+)?)", value, re.I)
    if c_prefix_match:
        return float(c_prefix_match.group("value"))

    c_suffix_match = re.fullmatch(r"(?P<value>\d+(?:\.\d+)?)C?", value, re.I)
    if c_suffix_match:
        return float(c_suffix_match.group("value"))

    return None


def _looks_like_c_rate_token(token: str) -> bool:
    """Return whether a token is likely a C-rate, not a temperature token."""
    if "/" in token:
        return True
    if "-" in token:
        return all(_parse_c_rate_value(part) is not None for part in token.split("-"))
    parsed_value = _parse_c_rate_value(token)
    return parsed_value is not None and parsed_value <= 5


def _parse_temperature_token(token: str) -> float | None:
    """Parse a temperature token while avoiding common C-rate tokens."""
    for pattern in _TEMPERATURE_PATTERNS:
        match = pattern.fullmatch(token)
        if not match:
            continue
        value = float(match.group("value"))
        if token.upper().startswith("T") or "deg" in token.lower() or value < 0:
            return value
        # Observed Battery Archive temperatures are >= 15C when positive. This
        # avoids treating standalone C-rate tokens such as 1C as temperatures.
        if value > 5:
            return value
    return None


def _find_form_factor_index(tokens: list[str]) -> int | None:
    """Find the first observed form-factor token."""
    for index, token in enumerate(tokens):
        if token.casefold() in KNOWN_FORM_FACTOR_TOKENS:
            return index
    return None


def _find_temperature(tokens: list[str], start_index: int) -> tuple[int | None, float | None]:
    """Find a conservative temperature token after form factor/chemistry tokens."""
    for index in range(start_index, len(tokens)):
        parsed_temperature = _parse_temperature_token(tokens[index])
        if parsed_temperature is not None:
            return index, parsed_temperature
    return None, None


def _find_soc_window(
    tokens: list[str],
    start_index: int,
) -> tuple[int | None, float | None, float | None, str]:
    """Find an SOC window token or token pair."""
    for index in range(start_index, len(tokens)):
        token = tokens[index]
        for pattern in _SOC_PATTERNS:
            match = pattern.fullmatch(token)
            if not match:
                continue
            minimum = float(match.group("minimum"))
            maximum = float(match.group("maximum"))
            if 0 <= minimum <= maximum <= 100:
                return index, minimum, maximum, f"{_format_numeric(minimum)}-{_format_numeric(maximum)}"

        if index + 1 < len(tokens) and re.fullmatch(r"\d+(?:\.\d+)?", token):
            pair_match = _SOC_PAIR_PATTERN.fullmatch(tokens[index + 1])
            if pair_match:
                minimum = float(token)
                maximum = float(pair_match.group("maximum"))
                if 0 <= minimum <= maximum <= 100:
                    return index, minimum, maximum, f"{_format_numeric(minimum)}-{_format_numeric(maximum)}"

    return None, None, None, "unknown"


def _find_c_rates(tokens: list[str], start_index: int) -> tuple[float | None, float | None, str]:
    """Find charge/discharge C-rates only when the filename separates them."""
    for token in tokens[start_index:]:
        if "-" not in token:
            continue
        parts = token.split("-")
        if len(parts) != 2:
            continue
        charge_rate = _parse_c_rate_value(parts[0])
        discharge_rate = _parse_c_rate_value(parts[1])
        if charge_rate is not None and discharge_rate is not None:
            return charge_rate, discharge_rate, ""

    for token in tokens[start_index:]:
        if _looks_like_c_rate_token(token):
            return None, None, (
                f"single C-rate token `{token}` was not assigned to charge/discharge"
            )
    return None, None, "charge/discharge C-rate token not found"


def _derive_cell_id(prefix_tokens: list[str]) -> str:
    """Derive a cell id only when the prefix has an explicit sample token."""
    if len(prefix_tokens) < 2:
        return "unknown"
    return "_".join(prefix_tokens)


def _build_protocol_label(metadata: dict[str, object]) -> str:
    """Build a compact protocol label from parsed, explicit metadata fields."""
    components = [
        str(metadata.get("chemistry", "unknown")),
        str(metadata.get("form_factor", "unknown")),
        (
            f"{_format_numeric(metadata.get('temperature_C'))}C"
            if not pd.isna(metadata.get("temperature_C"))
            else "unknown_temp"
        ),
        str(metadata.get("soc_window", "unknown")),
        (
            f"{_format_numeric(metadata.get('charge_c_rate'))}-"
            f"{_format_numeric(metadata.get('discharge_c_rate'))}C"
            if not pd.isna(metadata.get("charge_c_rate"))
            and not pd.isna(metadata.get("discharge_c_rate"))
            else "unknown_rate"
        ),
    ]
    if all(not component.startswith("unknown") for component in components):
        return "|".join(components)
    return "unknown"


def _finalize_metadata_status(metadata: dict[str, object], messages: list[str]) -> None:
    """Set parse status and message based on recognized metadata fields."""
    required_text_fields = ["cell_id", "source", "chemistry", "form_factor", "soc_window"]
    required_numeric_fields = [
        "temperature_C",
        "soc_min_pct",
        "soc_max_pct",
        "charge_c_rate",
        "discharge_c_rate",
    ]
    missing_fields = [
        field
        for field in required_text_fields
        if str(metadata.get(field, "unknown")) in {"", "unknown"}
    ]
    missing_fields.extend(
        field for field in required_numeric_fields if pd.isna(metadata.get(field))
    )

    core_fields = [
        "chemistry",
        "form_factor",
        "temperature_C",
        "soc_min_pct",
        "soc_max_pct",
        "charge_c_rate",
        "discharge_c_rate",
    ]
    parsed_core_count = sum(
        (
            str(metadata.get(field, "unknown")) not in {"", "unknown"}
            if field in {"chemistry", "form_factor"}
            else not pd.isna(metadata.get(field))
        )
        for field in core_fields
    )

    if parsed_core_count == 0:
        metadata["metadata_parse_status"] = "unparsed"
    elif missing_fields:
        metadata["metadata_parse_status"] = "partially_parsed"
    else:
        metadata["metadata_parse_status"] = "parsed"

    if missing_fields:
        messages.append("missing fields: " + ", ".join(missing_fields))
    metadata["metadata_parse_message"] = "; ".join(message for message in messages if message)


def parse_battery_archive_filename(
    zip_file: str | Path,
    internal_csv_path: str | PurePosixPath,
    file_name: str | None = None,
) -> dict[str, object]:
    """Parse conservative Battery Archive metadata from an inventory filename.

    The parser uses only tokens observed in the file path. Ambiguous fields are
    left as unknown/NaN and described through metadata_parse_status/message.
    """
    internal_path = str(internal_csv_path).replace("\\", "/")
    path = PurePosixPath(internal_path)
    resolved_file_name = file_name or path.name
    metadata = _unknown_metadata()
    metadata["source"] = path.parts[0] if len(path.parts) > 1 else Path(zip_file).stem
    metadata["filename_stem"] = _CYCLE_SUFFIX_PATTERN.sub("", resolved_file_name)

    messages: list[str] = []
    tokens = [token for token in metadata["filename_stem"].split("_") if token]
    form_factor_index = _find_form_factor_index(tokens)
    if form_factor_index is None:
        messages.append("form factor token not found")
        _finalize_metadata_status(metadata, messages)
        return metadata

    metadata["form_factor"] = tokens[form_factor_index].lower()
    metadata["cell_id"] = _derive_cell_id(tokens[:form_factor_index])

    temperature_index, temperature = _find_temperature(tokens, form_factor_index + 1)
    if temperature_index is None:
        messages.append("temperature token not found")
        chemistry_tokens = []
    else:
        metadata["temperature_C"] = temperature
        chemistry_tokens = [
            token
            for token in tokens[form_factor_index + 1 : temperature_index]
            if token.upper() in KNOWN_CHEMISTRY_TOKENS
        ]

    if chemistry_tokens:
        metadata["chemistry"] = "_".join(token.upper() for token in chemistry_tokens)
    else:
        messages.append("chemistry token not found")

    soc_start = (temperature_index + 1) if temperature_index is not None else form_factor_index + 1
    soc_index, soc_min, soc_max, soc_window = _find_soc_window(tokens, soc_start)
    if soc_index is not None:
        metadata["soc_min_pct"] = soc_min
        metadata["soc_max_pct"] = soc_max
        metadata["soc_window"] = soc_window
    else:
        messages.append("SOC window token not found")

    rate_start = (soc_index + 1) if soc_index is not None else soc_start
    charge_rate, discharge_rate, rate_message = _find_c_rates(tokens, rate_start)
    if charge_rate is not None and discharge_rate is not None:
        metadata["charge_c_rate"] = charge_rate
        metadata["discharge_c_rate"] = discharge_rate
    elif rate_message:
        messages.append(rate_message)

    metadata["protocol_label"] = _build_protocol_label(metadata)
    _finalize_metadata_status(metadata, messages)
    return metadata


def _validate_cycle_inventory_columns(inventory_df: pd.DataFrame) -> None:
    """Validate required v1.1.1 inventory columns."""
    missing_columns = [
        column
        for column in ["zip_file", "internal_csv_path", "file_name"]
        if column not in inventory_df.columns
    ]
    if missing_columns:
        raise ValueError(
            "Battery Archive cycle inventory is missing required column(s): "
            + ", ".join(missing_columns)
        )


def enrich_cycle_file_inventory(inventory_df: pd.DataFrame) -> pd.DataFrame:
    """Add conservative filename-derived metadata to a cycle file inventory."""
    _validate_cycle_inventory_columns(inventory_df)
    enriched_df = inventory_df.copy()
    metadata_rows = [
        parse_battery_archive_filename(
            zip_file=row["zip_file"],
            internal_csv_path=row["internal_csv_path"],
            file_name=row["file_name"],
        )
        for _, row in enriched_df.iterrows()
    ]
    metadata_df = pd.DataFrame(metadata_rows, columns=BATTERY_ARCHIVE_METADATA_COLUMNS)
    enriched_df = pd.concat([enriched_df.reset_index(drop=True), metadata_df], axis=1)

    duplicate_count = int(
        enriched_df.duplicated(["zip_file", "internal_csv_path"]).sum()
    )
    if duplicate_count:
        raise ValueError(
            "Duplicate Battery Archive cycle inventory records found during enrichment."
        )

    return enriched_df.sort_values(
        ["zip_file", "internal_csv_path"],
        key=lambda series: series.astype(str).str.casefold(),
    ).reset_index(drop=True)


def discover_cycle_files(raw_dir: str | Path) -> list[dict[str, object]]:
    """Discover Battery Archive cycle_data CSV entries without extracting zips."""
    records: list[dict[str, object]] = []
    for zip_path in _list_zip_paths(raw_dir):
        try:
            with zipfile.ZipFile(zip_path) as archive:
                for zip_info in archive.infolist():
                    if not _is_cycle_data_entry(zip_info):
                        continue
                    internal_csv_path = zip_info.filename.replace("\\", "/")
                    records.append(
                        {
                            "zip_file": zip_path.name,
                            "internal_csv_path": internal_csv_path,
                            "file_name": PurePosixPath(internal_csv_path).name,
                            "file_type": "cycle_data",
                            "uncompressed_size_bytes": int(zip_info.file_size),
                            "compressed_size_bytes": int(zip_info.compress_size),
                            "crc32": f"{zip_info.CRC:08x}",
                        }
                    )
        except zipfile.BadZipFile as exc:
            raise ValueError(
                f"Could not read Battery Archive zip file: {zip_path.name}"
            ) from exc

    return sorted(
        records,
        key=lambda record: (
            str(record["zip_file"]).casefold(),
            str(record["internal_csv_path"]).casefold(),
        ),
    )


def build_cycle_file_inventory(raw_dir: str | Path) -> pd.DataFrame:
    """Build a deterministic cycle_data file inventory DataFrame."""
    records = discover_cycle_files(raw_dir)
    if not records:
        raise ValueError(
            f"No Battery Archive cycle_data CSV files were found in: {Path(raw_dir)}"
        )

    inventory_df = pd.DataFrame(records, columns=BATTERY_ARCHIVE_INVENTORY_COLUMNS)
    duplicate_mask = inventory_df.duplicated(
        subset=["zip_file", "internal_csv_path"],
        keep=False,
    )
    if duplicate_mask.any():
        duplicates = inventory_df.loc[
            duplicate_mask, ["zip_file", "internal_csv_path"]
        ]
        raise ValueError(
            "Duplicate Battery Archive cycle file records were found: "
            f"{duplicates.to_dict(orient='records')}"
        )

    return inventory_df.sort_values(
        ["zip_file", "internal_csv_path"],
        key=lambda series: series.astype(str).str.casefold(),
    ).reset_index(drop=True)


class BatteryArchiveConnector(BaseConnector):
    """Generic skeleton for a future Battery Archive API endpoint."""

    source_name = "battery_archive"

    def __init__(self, base_url: str | None = None, endpoint: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("BATTERY_ARCHIVE_BASE_URL") or "").rstrip("/")
        self.api_key = os.getenv("BATTERY_ARCHIVE_API_KEY")
        self.endpoint = endpoint or os.getenv("BATTERY_ARCHIVE_ENDPOINT")

    def get_json(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """GET JSON from a configured Battery Archive endpoint."""
        if not self.base_url:
            raise RuntimeError(
                "BATTERY_ARCHIVE_BASE_URL is not configured. Set it in the "
                "environment when an endpoint is available."
            )
        try:
            import requests
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "The requests package is required for Battery Archive ingestion.\n"
                "Install it with: pip install requests"
            ) from exc

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()

    def fetch(self, limit: int = 50, full: bool = False) -> IngestionResult:
        """Probe Battery Archive if endpoint details are configured."""
        del full
        if not self.endpoint:
            return IngestionResult(
                source_name=self.source_name,
                warnings=[
                    "Battery Archive endpoint is not configured yet. Set "
                    "BATTERY_ARCHIVE_ENDPOINT and BATTERY_ARCHIVE_BASE_URL when "
                    "API documentation is available."
                ],
            )

        RAW_DIR.mkdir(parents=True, exist_ok=True)
        PROCESSED_PATH.parent.mkdir(parents=True, exist_ok=True)
        response_json = self.get_json(self.endpoint, params={"limit": limit})
        raw_path = RAW_DIR / "battery_archive_probe_raw.json"
        raw_path.write_text(json.dumps(response_json, indent=2), encoding="utf-8")

        return IngestionResult(
            source_name=self.source_name,
            raw_paths=[raw_path],
            processed_paths=[],
            warnings=[
                "Raw JSON was saved. Processed CSV conversion is pending until "
                "the Battery Archive response schema is finalized."
            ],
        )
