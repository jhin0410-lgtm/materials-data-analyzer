from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from src.loaders.characterization_bundle import (
    BUNDLE_TYPE,
    MANIFEST_NAME,
    NORMALIZED_INPUT_NAME,
    REPORT_NAME,
    SUMMARY_NAME,
    UNIT_LABEL_RULE,
    consume_characterization_bundle,
    validate_characterization_bundle,
)
from src.loaders.characterization_features import REQUIRED_COLUMNS, sha256_file

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = PROJECT_ROOT / "scripts" / "consume_characterization_handoff_bundle.py"


def _record(path: Path) -> dict[str, object]:
    return {
        "path": path.name,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _write_bundle(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    source_hash_characters = {"raman": "a", "ftir": "b", "xps": "c", "tga": "d"}
    for instrument, feature_name, unit in (
        ("raman", "candidate_count", "count"),
        ("ftir", "band_candidate_count", "count"),
        ("xps", "peak_candidate_count", "count"),
        ("tga", "retained_mass_percent", "%"),
    ):
        rows.append(
            {
                "sample_id": "public-dwcnt",
                "measurement_id": f"public-dwcnt-{instrument}-public",
                "instrument": instrument,
                "feature_name": feature_name,
                "feature_label": None,
                "value": 2.0 if unit == "count" else 12.5,
                "unit": unit,
                "method": f"{instrument}_diagnostic_method",
                "source_file": f"producer-local/{instrument}.tab",
                "source_sha256": source_hash_characters[instrument] * 64,
                "preprocessing_id": f"{instrument}-preprocessing-v1",
                "quality_flag": "review_required",
            }
        )
    feature_path = root / "characterization_features_long.csv"
    pd.DataFrame(rows, columns=REQUIRED_COLUMNS).to_csv(feature_path, index=False)

    context_path = root / "sample_context.csv"
    pd.DataFrame(
        [
            {
                "sample_id": "public-dwcnt",
                "source_label": "DWCNT",
                "material_class": "double-walled carbon nanotubes",
                "dataset_persistent_id": "doi:10.57745/7KA2UG",
                "identical_physical_aliquot_confirmed": False,
            }
        ]
    ).to_csv(context_path, index=False)

    source_manifest = root / "case_source_manifest.json"
    source_manifest.write_text('{"source": "public"}\n', encoding="utf-8")
    analysis_manifest = root / "case_analysis_manifest.json"
    analysis_manifest.write_text('{"analysis_count": 4}\n', encoding="utf-8")
    comparability = root / "comparability_matrix.csv"
    pd.DataFrame(
        {
            "modality": ["raman", "ftir", "xps", "tga"],
            "comparability_status": ["conditionally_comparable"] * 4,
        }
    ).to_csv(comparability, index=False)

    manifest = {
        "schema_version": "1.0",
        "bundle_type": BUNDLE_TYPE,
        "case_id": "public-carbon-dwcnt-multimodal-v1",
        "producer": {
            "repository": "jhin0410-lgtm/materials-characterization-analyzer",
            "software_versions": ["0.8.3"],
            "analysis_result_schema_versions": ["1.0"],
        },
        "join_contract": {
            "join_key": "sample_id",
            "row_order_join_allowed": False,
            "aggregation_performed": False,
            "missing_metadata_inferred": False,
        },
        "feature_table": {
            **_record(feature_path),
            "columns": REQUIRED_COLUMNS,
            "row_count": 4,
            "sample_count": 1,
            "measurement_count": 4,
            "instruments": ["ftir", "raman", "tga", "xps"],
            "quality_flag_counts": {"review_required": 4},
            "source_sha256_record_count": 4,
            "preprocessing_id_record_count": 4,
        },
        "sample_context": {
            **_record(context_path),
            "columns": pd.read_csv(context_path).columns.tolist(),
            "row_count": 1,
        },
        "evidence_references": {
            "source_manifest": _record(source_manifest),
            "analysis_manifest": _record(analysis_manifest),
            "comparability_matrix": _record(comparability),
        },
        "scientific_closeout": {
            "evidence_level": "Diagnostic",
            "result": "real_public_multimodal_features_exported",
            "strongest_evidence": "All feature rows retain source hashes and stable IDs.",
            "primary_limitation": "Identical physical aliquots are not confirmed.",
            "suitable_for": [
                "cross-repository contract validation",
                "descriptive multimodal feature integration",
            ],
            "unsuitable_for": [
                "process-response modeling",
                "causal attribution",
                "engineering release decisions",
            ],
        },
    }
    manifest_path = root / "characterization_handoff_bundle.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _harden_bundle(manifest_path: Path) -> Path:
    root = manifest_path.parent
    features = pd.read_csv(root / "characterization_features_long.csv")
    feature_records = json.loads(features.to_json(orient="records"))

    source_manifest = root / "case_source_manifest.json"
    source_manifest.write_text(
        json.dumps(
            {
                "case_id": "public-carbon-dwcnt-multimodal-v1",
                "sources": [
                    {"source_sha256": value}
                    for value in features["source_sha256"].astype(str).tolist()
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    analysis_manifest = root / "case_analysis_manifest.json"
    analysis_manifest.write_text(
        json.dumps(
            {
                "analysis_count": 1,
                "analyses": [
                    {
                        "schema_version": "1.0",
                        "software_version": "test",
                        "features": feature_records,
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["evidence_identity_binding_contract"] = {
        "schema_version": "1.0",
        "required": True,
    }
    manifest["evidence_references"]["source_manifest"] = _record(source_manifest)
    manifest["evidence_references"]["analysis_manifest"] = _record(analysis_manifest)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _refresh_evidence_record(manifest_path: Path, label: str) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    path = manifest_path.parent / manifest["evidence_references"][label]["path"]
    manifest["evidence_references"][label] = _record(path)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_consumer_validates_bundle_and_builds_integrated_sample_table(tmp_path: Path) -> None:
    bundle_manifest = _write_bundle(tmp_path / "producer")
    output = tmp_path / "consumer"

    paths = consume_characterization_bundle(bundle_manifest, output)

    expected = {
        NORMALIZED_INPUT_NAME,
        "characterization_features_validated_long.csv",
        "characterization_feature_dictionary.csv",
        "characterization_features_wide.csv",
        "characterization_handoff_manifest.json",
        "integrated_sample_table.csv",
        "sample_join_audit.csv",
        SUMMARY_NAME,
        REPORT_NAME,
        MANIFEST_NAME,
    }
    assert expected.issubset({path.name for path in output.iterdir()})
    assert paths["cross_repository_manifest"].name == MANIFEST_NAME

    audit = pd.read_csv(output / "sample_join_audit.csv")
    assert audit.to_dict("records") == [
        {"sample_id": "public-dwcnt", "join_status": "matched"}
    ]
    integrated = pd.read_csv(output / "integrated_sample_table.csv")
    assert len(integrated) == 1
    assert integrated.loc[0, "source_label"] == "DWCNT"
    assert {
        "char__raman__candidate_count__count",
        "char__ftir__band_candidate_count__count",
        "char__xps__peak_candidate_count__count",
        "char__tga__retained_mass_percent__percent",
    }.issubset(integrated.columns)

    normalized = pd.read_csv(output / NORMALIZED_INPUT_NAME)
    assert normalized.loc[normalized["instrument"].eq("tga"), "unit"].tolist() == [
        "percent"
    ]
    producer_features = pd.read_csv(bundle_manifest.parent / "characterization_features_long.csv")
    assert producer_features.loc[producer_features["instrument"].eq("tga"), "unit"].tolist() == [
        "%"
    ]

    summary = json.loads((output / SUMMARY_NAME).read_text(encoding="utf-8"))
    assert summary["status"] == "verified"
    assert summary["join_summary"] == {
        "matched": 1,
        "process_only": 0,
        "characterization_only": 0,
    }
    assert summary["unit_label_normalization"] == {
        "performed": True,
        "rule": UNIT_LABEL_RULE,
        "mappings": {"%": "percent"},
        "record_count": 1,
        "numeric_values_modified": False,
        "source_feature_table_preserved": True,
    }
    assert summary["evidence_identity_binding"] == {
        "contract_present": False,
        "contract_required": False,
        "legacy_checksum_only_validation": True,
        "semantic_identity_binding_verified": False,
        "scientific_comparability_established": False,
    }
    assert summary["scientific_closeout"]["evidence_level"] == "Diagnostic"
    assert summary["software_validation"]["numeric_values_modified"] is False
    assert summary["software_validation"]["model_trained"] is False
    assert summary["software_validation"]["scientific_metrics_recomputed"] is False
    assert summary["software_validation"]["legacy_checksum_only_evidence_validation"] is True
    assert summary["software_validation"]["scientific_comparability_established"] is False

    consumer_manifest = json.loads((output / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert consumer_manifest["unit_label_normalization"]["mappings"] == {
        "%": "percent"
    }
    assert consumer_manifest["evidence_identity_binding"]["contract_present"] is False
    for name, filename in consumer_manifest["outputs"].items():
        assert consumer_manifest["output_sha256"][name] == sha256_file(output / filename)
    assert not list(output.glob("*.pkl"))
    assert not list(output.glob("*model*"))


def test_hardened_bundle_is_independently_revalidated_by_consumer(tmp_path: Path) -> None:
    bundle_manifest = _harden_bundle(_write_bundle(tmp_path / "producer"))
    validated = validate_characterization_bundle(bundle_manifest)
    binding = validated.evidence_identity_binding
    assert binding["contract_present"] is True
    assert binding["contract_required"] is True
    assert binding["semantic_identity_binding_verified"] is True
    assert binding["analysis_manifest_features_reproduced"] is True
    assert binding["every_feature_row_source_sha256_bound"] is True
    assert binding["comparability_identity_coverage_verified"] is True
    assert binding["scientific_comparability_established"] is False

    output = tmp_path / "consumer"
    consume_characterization_bundle(bundle_manifest, output)
    summary = json.loads((output / SUMMARY_NAME).read_text(encoding="utf-8"))
    assert summary["software_validation"][
        "semantic_evidence_identity_binding_verified"
    ] is True
    assert summary["software_validation"]["scientific_comparability_established"] is False
    consumer_manifest = json.loads((output / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert consumer_manifest["evidence_identity_binding"][
        "semantic_identity_binding_verified"
    ] is True


def test_hardened_bundle_rejects_semantically_drifted_analysis_with_refreshed_hash(
    tmp_path: Path,
) -> None:
    bundle_manifest = _harden_bundle(_write_bundle(tmp_path / "producer"))
    analysis_path = bundle_manifest.parent / "case_analysis_manifest.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    analysis["analyses"][0]["features"][0]["value"] = 999.0
    analysis_path.write_text(json.dumps(analysis), encoding="utf-8")
    _refresh_evidence_record(bundle_manifest, "analysis_manifest")

    with pytest.raises(ValueError, match="analysis manifest does not reproduce feature table"):
        validate_characterization_bundle(bundle_manifest)


def test_hardened_bundle_rejects_unbound_source_with_refreshed_hash(tmp_path: Path) -> None:
    bundle_manifest = _harden_bundle(_write_bundle(tmp_path / "producer"))
    source_path = bundle_manifest.parent / "case_source_manifest.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source["sources"] = source["sources"][1:]
    source_path.write_text(json.dumps(source), encoding="utf-8")
    _refresh_evidence_record(bundle_manifest, "source_manifest")

    with pytest.raises(ValueError, match="source manifest does not bind every feature"):
        validate_characterization_bundle(bundle_manifest)


def test_hardened_bundle_rejects_unrelated_comparability_with_refreshed_hash(
    tmp_path: Path,
) -> None:
    bundle_manifest = _harden_bundle(_write_bundle(tmp_path / "producer"))
    comparability_path = bundle_manifest.parent / "comparability_matrix.csv"
    table = pd.read_csv(comparability_path)
    table.loc[table["modality"].eq("tga"), "modality"] = "xrd"
    table.to_csv(comparability_path, index=False)
    _refresh_evidence_record(bundle_manifest, "comparability_matrix")

    with pytest.raises(ValueError, match="comparability matrix misses feature instruments"):
        validate_characterization_bundle(bundle_manifest)


def test_hardened_bundle_rejects_malformed_required_contract(tmp_path: Path) -> None:
    bundle_manifest = _harden_bundle(_write_bundle(tmp_path / "producer"))
    manifest = json.loads(bundle_manifest.read_text(encoding="utf-8"))
    manifest["evidence_identity_binding_contract"]["required"] = False
    bundle_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="required must be true"):
        validate_characterization_bundle(bundle_manifest)


def test_bundle_manifest_duplicate_json_key_fails_closed(tmp_path: Path) -> None:
    bundle_manifest = _write_bundle(tmp_path / "producer")
    text = bundle_manifest.read_text(encoding="utf-8")
    text = text.replace(
        '{\n  "bundle_type"',
        '{\n  "case_id": "duplicate",\n  "bundle_type"',
        1,
    )
    bundle_manifest.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate JSON key"):
        validate_characterization_bundle(bundle_manifest)


def test_consumer_cli_runs_end_to_end(tmp_path: Path) -> None:
    bundle_manifest = _write_bundle(tmp_path / "producer")
    output = tmp_path / "consumer"

    completed = subprocess.run(
        [
            sys.executable,
            str(CLI_PATH),
            "--bundle-manifest",
            str(bundle_manifest),
            "--output",
            str(output),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "handoff completed" in completed.stdout.lower()
    assert (output / SUMMARY_NAME).is_file()


def test_bundle_validation_rejects_feature_checksum_tampering(tmp_path: Path) -> None:
    bundle_manifest = _write_bundle(tmp_path / "producer")
    feature_path = bundle_manifest.parent / "characterization_features_long.csv"
    feature_path.write_text(feature_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="feature_table checksum mismatch"):
        validate_characterization_bundle(bundle_manifest)


def test_bundle_validation_rejects_path_traversal(tmp_path: Path) -> None:
    bundle_manifest = _write_bundle(tmp_path / "producer")
    manifest = json.loads(bundle_manifest.read_text(encoding="utf-8"))
    manifest["feature_table"]["path"] = "../characterization_features_long.csv"
    bundle_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="relative sibling filename"):
        validate_characterization_bundle(bundle_manifest)


def test_consumer_rejects_nonempty_output_without_deleting_files(tmp_path: Path) -> None:
    bundle_manifest = _write_bundle(tmp_path / "producer")
    output = tmp_path / "consumer"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("preserve me", encoding="utf-8")

    with pytest.raises(FileExistsError, match="existing files were preserved"):
        consume_characterization_bundle(bundle_manifest, output)

    assert sentinel.read_text(encoding="utf-8") == "preserve me"
