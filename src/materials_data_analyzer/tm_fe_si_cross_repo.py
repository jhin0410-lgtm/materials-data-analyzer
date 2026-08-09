"""Frozen real-data TM-Fe-Si MCA-to-MDA descriptive consumer."""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import pandas as pd

from loaders.characterization_features import sha256_file

from .characterization_use_workflow import consume_characterization_bundle_for_use

CASE_ID = "tm-fe-si-public-xrd-mh-descriptive-v1"
MCA_CASE_ID = "tm-fe-si-public-xrd-descriptive-v1"
DATASET_DOI = "10.17632/gp8rkw2k6v.2"
PUBLICATION_DOI = "10.1016/j.dib.2022.108868"
DATASET_VERSION = "2"
DATASET_LICENSE = "CC BY 4.0"
PREPARATION_FAMILY_ID = "tm-fe-si-arc-melt-remelt-1050c-1d-air-cool"
FIELD_TARGET_KOE = 30.0
FIELD_ENDPOINT_TOLERANCE_KOE = 0.005
EXPECTED_FIELD_MIN_KOE = -30.0
EXPECTED_FIELD_MAX_KOE = 30.0
EXPECTED_FIELD_HEADER = "H (kOe)"
EXPECTED_MAGNETIZATION_HEADER = "M (emu/g)"
SHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
MAGNETIC_TABLE_NAME = "tm_fe_si_magnetic_consumer_table.csv"
DESCRIPTIVE_TABLE_NAME = "tm_fe_si_cross_modal_descriptive_table.csv"
SOURCE_MANIFEST_NAME = "tm_fe_si_magnetic_source_manifest.json"
SUMMARY_NAME = "tm_fe_si_cross_modal_summary.json"
REPORT_NAME = "tm_fe_si_cross_modal_report.md"
IMPORTED_DIR_NAME = "characterization_import"


@dataclass(frozen=True)
class MagneticSourceContract:
    tm_element: str
    filename: str
    size_bytes: int
    sha256: str
    title_300k: str
    point_count: int

    @property
    def nominal_composition(self) -> str:
        return f"{self.tm_element}7Fe52Si41"

    @property
    def sample_id(self) -> str:
        return f"tm-fe-si-{self.tm_element.lower()}7fe52si41-1050c-1d"


MAGNETIC_SOURCES = (
    MagneticSourceContract(
        "Ti",
        "Fig.3b-MH curves Ti7Fe52Si41.xlsx",
        144_037,
        "eeda55b961b6000f3865f11707afdb247715c1210362fe9ff3186a11218c999e",
        "Fig. 3(b) 300K Ti7Fe52Si41",
        437,
    ),
    MagneticSourceContract(
        "Zr",
        "Fig.3d-MH curves Zr7Fe52Si41.xlsx",
        142_383,
        "b3f9498fe32e28ce3af5638626689f6801e8710959f58c01d670695e1c618437",
        "Fig. 3(d) 300K Zr7Fe52Si41",
        442,
    ),
    MagneticSourceContract(
        "Hf",
        "Fig.3f-MH curves Hf7Fe52Si41.xlsx",
        142_516,
        "b67e0166b5f6a538f05bb51a7dd96eacbb5c2aba636693379566ba8bddc786fc",
        "Fig. 3(f) 300K Hf7Fe52Si41",
        442,
    ),
    MagneticSourceContract(
        "V",
        "Fig.4b-MH curves V7Fe52Si41.xlsx",
        143_245,
        "90ec2bc7b6af67650c62e3751dae2633db026ebe52f3008a8d9853924ba20c82",
        "Fig. 4(b) 300K V7Fe52Si41",
        437,
    ),
    MagneticSourceContract(
        "Nb",
        "Fig.4d-MH curves Nb7Fe52Si41.xlsx",
        142_731,
        "0d4d0c2e9d016baa6dae88f061f4b6654ce14c6f007b49289af2ba7cb347cc27",
        "Fig. 4(d) 300K Nb7Fe52Si41",
        437,
    ),
    MagneticSourceContract(
        "Ta",
        "Fig.4f-MH curves Ta7Fe52Si41.xlsx",
        143_666,
        "4b8f303afa20ef7235a673a68976d61adb8c0e4f93ae4b421c1f8bc95ab028e2",
        "Fig. 4(f) 300K Ta7Fe52Si41",
        437,
    ),
)


class TMFeSiCrossRepoError(ValueError):
    """Raised when a frozen case invariant fails closed."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_source(path: Path, contract: MagneticSourceContract) -> None:
    if not path.is_file() or path.is_symlink():
        raise TMFeSiCrossRepoError(f"magnetic source must be a regular file: {path}")
    if path.name != contract.filename:
        raise TMFeSiCrossRepoError(f"unexpected magnetic source filename: {path.name}")
    if path.stat().st_size != contract.size_bytes:
        raise TMFeSiCrossRepoError(f"magnetic source size mismatch: {path.name}")
    if _sha256(path) != contract.sha256:
        raise TMFeSiCrossRepoError(f"magnetic source SHA-256 mismatch: {path.name}")


def _worksheet_cells(path: Path) -> dict[str, str | float]:
    try:
        with zipfile.ZipFile(path) as archive:
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            sheet_root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    except (KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
        raise TMFeSiCrossRepoError(
            f"magnetic source is not the expected readable XLSX structure: {path.name}"
        ) from exc
    if sheet_root.find(f".//{SHEET_NS}f") is not None:
        raise TMFeSiCrossRepoError("formulas are not allowed in the frozen M-H source")
    shared = [
        "".join(node.text or "" for node in item.iter(f"{SHEET_NS}t"))
        for item in shared_root.findall(f"{SHEET_NS}si")
    ]
    cells: dict[str, str | float] = {}
    for cell in sheet_root.findall(f".//{SHEET_NS}c"):
        ref = cell.attrib.get("r")
        value_node = cell.find(f"{SHEET_NS}v")
        if not ref or value_node is None or value_node.text is None:
            continue
        if cell.attrib.get("t") == "s":
            try:
                cells[ref] = shared[int(value_node.text)]
            except (ValueError, IndexError) as exc:
                raise TMFeSiCrossRepoError(f"invalid shared string at {ref}") from exc
        else:
            try:
                cells[ref] = float(value_node.text)
            except ValueError as exc:
                raise TMFeSiCrossRepoError(f"non-numeric value at {ref}") from exc
    return cells


def _trace_from_cells(
    cells: dict[str, str | float], contract: MagneticSourceContract
) -> list[tuple[float, float]]:
    if cells.get("G1") != contract.title_300k:
        raise TMFeSiCrossRepoError(
            f"unexpected 300 K trace title for {contract.nominal_composition}"
        )
    if cells.get("G2") != EXPECTED_FIELD_HEADER:
        raise TMFeSiCrossRepoError("unexpected 300 K field header")
    if cells.get("H2") != EXPECTED_MAGNETIZATION_HEADER:
        raise TMFeSiCrossRepoError("unexpected 300 K magnetization header")
    trace: list[tuple[float, float]] = []
    row = 3
    while True:
        field = cells.get(f"G{row}")
        magnetization = cells.get(f"H{row}")
        if field is None and magnetization is None:
            break
        if not isinstance(field, float) or not isinstance(magnetization, float):
            raise TMFeSiCrossRepoError(
                f"missing or non-numeric 300 K M-H pair at row {row}"
            )
        if not math.isfinite(field) or not math.isfinite(magnetization):
            raise TMFeSiCrossRepoError(f"non-finite 300 K M-H pair at row {row}")
        trace.append((field, magnetization))
        row += 1
    if len(trace) != contract.point_count:
        raise TMFeSiCrossRepoError(
            f"unexpected 300 K point count for {contract.nominal_composition}: {len(trace)}"
        )
    fields = [field for field, _ in trace]
    if not math.isclose(min(fields), EXPECTED_FIELD_MIN_KOE, rel_tol=0.0, abs_tol=1e-9):
        raise TMFeSiCrossRepoError("300 K loop does not reach the frozen -30 kOe minimum")
    if not math.isclose(max(fields), EXPECTED_FIELD_MAX_KOE, rel_tol=0.0, abs_tol=1e-9):
        raise TMFeSiCrossRepoError("300 K loop does not reach the frozen +30 kOe maximum")
    for label, field in (("first", trace[0][0]), ("last", trace[-1][0])):
        if abs(field - FIELD_TARGET_KOE) > FIELD_ENDPOINT_TOLERANCE_KOE:
            raise TMFeSiCrossRepoError(
                f"{label} 300 K endpoint is not within the frozen +30 kOe tolerance"
            )
    return trace


def _magnetic_row(
    contract: MagneticSourceContract,
    trace: list[tuple[float, float]],
) -> dict[str, object]:
    fields = [trace[0][0], trace[-1][0]]
    values = [trace[0][1], trace[-1][1]]
    return {
        "sample_id": contract.sample_id,
        "nominal_composition": contract.nominal_composition,
        "preparation_family_id": PREPARATION_FAMILY_ID,
        "measurement_temperature_k": 300.0,
        "mh_endpoint_target_field_koe": FIELD_TARGET_KOE,
        "mh_endpoint_field_tolerance_koe": FIELD_ENDPOINT_TOLERANCE_KOE,
        "mh_300k_plus30koe_endpoint_mean_emu_g": sum(values) / 2.0,
        "mh_300k_plus30koe_endpoint_abs_difference_emu_g": abs(values[0] - values[1]),
        "mh_300k_plus30koe_endpoint_count": 2,
        "mh_300k_endpoint_field_min_koe": min(fields),
        "mh_300k_endpoint_field_max_koe": max(fields),
        "mh_300k_loop_point_count": len(trace),
        "magnetic_source_file": contract.filename,
        "magnetic_source_sha256": contract.sha256,
        "dataset_persistent_id": f"doi:{DATASET_DOI}",
        "dataset_version": DATASET_VERSION,
        "dataset_license": DATASET_LICENSE,
    }


def build_magnetic_consumer_table(
    source_dir: str | Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Extract direct 300 K +30 kOe endpoint observations from six pinned files."""
    root = Path(source_dir)
    if not root.is_dir() or root.is_symlink():
        raise TMFeSiCrossRepoError(f"magnetic source directory not found or unsafe: {root}")
    rows: list[dict[str, object]] = []
    source_records: list[dict[str, object]] = []
    for contract in MAGNETIC_SOURCES:
        path = root / contract.filename
        _validate_source(path, contract)
        trace = _trace_from_cells(_worksheet_cells(path), contract)
        rows.append(_magnetic_row(contract, trace))
        source_records.append(
            {
                "sample_id": contract.sample_id,
                "nominal_composition": contract.nominal_composition,
                "filename": contract.filename,
                "size_bytes": contract.size_bytes,
                "sha256": contract.sha256,
                "trace_title_300k": contract.title_300k,
                "point_count_300k": contract.point_count,
            }
        )
    table = pd.DataFrame(rows).sort_values("sample_id").reset_index(drop=True)
    if len(table) != 6 or table["sample_id"].duplicated().any():
        raise TMFeSiCrossRepoError("magnetic consumer table stable identities are invalid")
    manifest = {
        "schema_version": "1.0",
        "case_id": CASE_ID,
        "publication_doi": PUBLICATION_DOI,
        "dataset_doi": DATASET_DOI,
        "dataset_version": DATASET_VERSION,
        "dataset_license": DATASET_LICENSE,
        "sources": source_records,
        "extraction_contract": {
            "temperature_k": 300.0,
            "trace_columns": ["G", "H"],
            "field_unit": "kOe",
            "magnetization_unit": "emu/g",
            "endpoint_target_field_koe": FIELD_TARGET_KOE,
            "endpoint_tolerance_koe": FIELD_ENDPOINT_TOLERANCE_KOE,
            "endpoints_used": ["first_numeric_pair", "last_numeric_pair"],
            "interpolation": False,
            "smoothing": False,
            "outlier_removal": False,
            "saturation_inferred": False,
            "coercivity_inferred": False,
            "curie_temperature_inferred": False,
        },
        "scientific_boundary": {
            "evidence_level": "Diagnostic",
            "allowed": [
                "direct descriptive comparison of observed 300 K +30 kOe endpoint magnetization"
            ],
            "blocked": [
                "saturation magnetization claim",
                "coercivity claim",
                "Curie-temperature claim",
                "association testing",
                "predictive modeling",
                "causal attribution",
                "engineering decision",
            ],
        },
    }
    return table, manifest


def _validate_identity_join(imported: pd.DataFrame, magnetic: pd.DataFrame) -> pd.DataFrame:
    required = {"sample_id", "nominal_composition", "preparation_family_id"}
    missing_imported = sorted(required - set(imported.columns))
    missing_magnetic = sorted(required - set(magnetic.columns))
    if missing_imported or missing_magnetic:
        raise TMFeSiCrossRepoError(
            f"stable identity columns missing; imported={missing_imported}, magnetic={missing_magnetic}"
        )
    for label, table in (
        ("imported characterization table", imported),
        ("magnetic table", magnetic),
    ):
        sample_ids = table["sample_id"].astype("string").str.strip()
        if sample_ids.isna().any() or sample_ids.eq("").any():
            raise TMFeSiCrossRepoError(f"{label} contains blank sample_id")
        if sample_ids.duplicated().any():
            raise TMFeSiCrossRepoError(f"{label} contains duplicate sample_id")
    imported_ids = set(imported["sample_id"].astype(str))
    magnetic_ids = set(magnetic["sample_id"].astype(str))
    if imported_ids != magnetic_ids:
        raise TMFeSiCrossRepoError(
            "sample_id sets differ; "
            f"characterization_only={sorted(imported_ids - magnetic_ids)}, "
            f"magnetic_only={sorted(magnetic_ids - imported_ids)}"
        )
    compared = imported[
        ["sample_id", "nominal_composition", "preparation_family_id"]
    ].merge(
        magnetic[["sample_id", "nominal_composition", "preparation_family_id"]],
        on="sample_id",
        validate="one_to_one",
        suffixes=("_characterization", "_magnetic"),
        sort=True,
    )
    for column in ("nominal_composition", "preparation_family_id"):
        left = compared[f"{column}_characterization"].astype("string").str.strip()
        right = compared[f"{column}_magnetic"].astype("string").str.strip()
        bad = ~left.eq(right)
        if bad.any():
            samples = compared.loc[bad, "sample_id"].astype(str).tolist()
            raise TMFeSiCrossRepoError(f"stable identity mismatch for {column}: {samples}")
    magnetic_payload = magnetic.drop(
        columns=["nominal_composition", "preparation_family_id"]
    )
    return imported.merge(
        magnetic_payload,
        on="sample_id",
        how="inner",
        validate="one_to_one",
        sort=True,
    ).sort_values("sample_id").reset_index(drop=True)


def _descriptive_feature_columns(table: pd.DataFrame) -> list[str]:
    xrd = sorted(column for column in table.columns if column.startswith("char__xrd__"))
    magnetic = [
        "mh_300k_plus30koe_endpoint_mean_emu_g",
        "mh_300k_plus30koe_endpoint_abs_difference_emu_g",
        "mh_300k_endpoint_field_min_koe",
        "mh_300k_endpoint_field_max_koe",
    ]
    return [*xrd, *magnetic]


def _report(summary: dict[str, Any]) -> str:
    return f"""# TM-Fe-Si Cross-Repository Descriptive Case

## Result

- Software workflow: **{summary['status']}**
- Scientific evidence: **Diagnostic**
- Samples: {summary['sample_count']}
- Requested downstream use: `descriptive`
- Row-order join used: `false`
- Exact XRD/VSM physical aliquot identity confirmed: `false`

The MCA XRD bundle was consumed through the existing checksum-validating MDA
characterization workflow. Consumer-owned 300 K M-H observations were then
joined only after exact equality of `sample_id`, `nominal_composition`, and
`preparation_family_id`.

`mh_300k_plus30koe_endpoint_mean_emu_g` is the arithmetic mean of the first and
last observed loop endpoints near +30 kOe (tolerance ±0.005 kOe). It is not
labeled or interpreted as saturation magnetization. No interpolation, smoothing,
outlier removal, coercivity inference, or Curie-temperature inference occurred.

The six-row table is suitable for descriptive per-composition inspection and
cross-repository provenance validation only. Correlation significance testing,
predictive modeling, causal attribution, phase assignment, absolute XRD
intensity comparison, and engineering decisions remain unsupported.
"""


def build_tm_fe_si_cross_repo_case(
    bundle_manifest: str | Path,
    magnetic_source_dir: str | Path,
    output_dir: str | Path,
    *,
    requested_use: str = "descriptive",
) -> dict[str, object]:
    """Build the complete TM-Fe-Si descriptive case transactionally."""
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = output.parent / f".{output.name}.building"
    if stage.exists():
        raise FileExistsError(f"staging directory already exists: {stage}")
    stage.mkdir()
    try:
        magnetic, source_manifest = build_magnetic_consumer_table(magnetic_source_dir)
        magnetic_path = stage / MAGNETIC_TABLE_NAME
        magnetic.to_csv(magnetic_path, index=False, lineterminator="\n")
        source_manifest_path = stage / SOURCE_MANIFEST_NAME
        source_manifest_path.write_text(
            json.dumps(source_manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        import_dir = stage / IMPORTED_DIR_NAME
        consume_characterization_bundle_for_use(
            bundle_manifest,
            import_dir,
            requested_use=requested_use,
        )
        imported = pd.read_csv(import_dir / "integrated_sample_table.csv")
        merged = _validate_identity_join(imported, magnetic)
        if len(merged) != 6:
            raise TMFeSiCrossRepoError("cross-modal descriptive join did not produce six rows")
        descriptive_path = stage / DESCRIPTIVE_TABLE_NAME
        merged.to_csv(descriptive_path, index=False, lineterminator="\n")

        import_summary = json.loads(
            (import_dir / "cross_repository_handoff_summary.json").read_text(encoding="utf-8")
        )
        if import_summary.get("case_id") != MCA_CASE_ID:
            raise TMFeSiCrossRepoError(
                f"unexpected MCA case_id: {import_summary.get('case_id')!r}"
            )
        eligibility = import_summary.get("downstream_use_eligibility")
        if not isinstance(eligibility, dict) or eligibility.get("requested_use") != "descriptive":
            raise TMFeSiCrossRepoError(
                "descriptive downstream-use eligibility was not preserved"
            )
        summary = {
            "schema_version": "1.0",
            "case_id": CASE_ID,
            "status": "verified_descriptive_cross_repo_case",
            "sample_count": int(len(merged)),
            "sample_ids": merged["sample_id"].astype(str).tolist(),
            "identity_contract": {
                "join_key": "sample_id",
                "additional_verified_fields": [
                    "nominal_composition",
                    "preparation_family_id",
                ],
                "row_order_join_used": False,
                "exact_xrd_vsm_physical_aliquot_identity_confirmed": False,
            },
            "characterization_import": {
                "producer_case_id": MCA_CASE_ID,
                "bundle_manifest_sha256": sha256_file(Path(bundle_manifest)),
                "status": import_summary.get("status"),
                "evidence_level": import_summary.get("scientific_closeout", {}).get(
                    "evidence_level"
                ),
                "requested_use": eligibility.get("requested_use"),
                "maximum_allowed_use": eligibility.get("maximum_allowed_use"),
            },
            "magnetic_consumer": {
                "table_sha256": sha256_file(magnetic_path),
                "source_manifest_sha256": sha256_file(source_manifest_path),
                "temperature_k": 300.0,
                "quantity": "observed_plus30koe_loop_endpoint_mean",
                "saturation_magnetization_claimed": False,
                "interpolation_performed": False,
                "smoothing_performed": False,
            },
            "descriptive_output": {
                "table_sha256": sha256_file(descriptive_path),
                "feature_columns": _descriptive_feature_columns(merged),
                "correlation_computed": False,
                "hypothesis_test_computed": False,
                "model_trained": False,
            },
            "scientific_closeout": {
                "evidence_level": "Diagnostic",
                "strongest_evidence": "Checksum-bound MCA XRD features and six checksum-bound public 300 K M-H traces share explicit nominal composition and preparation-family identities.",
                "primary_limitation": "Exact XRD/VSM physical aliquot identity and independent XRD peak truth are unconfirmed; n=6 does not support predictive, causal, or generalizable association claims.",
                "suitable_for": [
                    "descriptive per-composition inspection",
                    "cross-repository provenance and identity validation",
                ],
                "unsupported_for": [
                    "absolute XRD intensity comparison",
                    "phase assignment",
                    "saturation-magnetization claim",
                    "association significance",
                    "prediction",
                    "causality",
                    "engineering decision",
                ],
            },
        }
        summary_path = stage / SUMMARY_NAME
        summary_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (stage / REPORT_NAME).write_text(_report(summary), encoding="utf-8")
        stage.replace(output)
        return {
            "status": summary["status"],
            "output": str(output),
            "sample_count": 6,
            "magnetic_table": str(output / MAGNETIC_TABLE_NAME),
            "descriptive_table": str(output / DESCRIPTIVE_TABLE_NAME),
            "summary": str(output / SUMMARY_NAME),
        }
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


__all__ = [
    "CASE_ID",
    "MAGNETIC_SOURCES",
    "TMFeSiCrossRepoError",
    "build_magnetic_consumer_table",
    "build_tm_fe_si_cross_repo_case",
]
