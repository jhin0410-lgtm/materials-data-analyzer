from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import src.loaders.characterization_research_bundle as research_bundle
from src.loaders.characterization_features import sha256_file
from src.loaders.characterization_research_bundle import (
    ValidatedResearchCharacterizationBundle,
    consume_characterization_research_bundle,
    revalidate_characterization_research_bundle_identity,
)


def _validated_bundle(tmp_path: Path) -> ValidatedResearchCharacterizationBundle:
    root = tmp_path / "producer"
    root.mkdir()
    manifest_path = root / "characterization_handoff_bundle.json"
    ladder_path = root / "scientific_evidence_ladder_assessment.json"
    feature_path = root / "characterization_features_long.csv"
    context_path = root / "sample_context.csv"
    source_path = root / "source_manifest.json"
    analysis_path = root / "analysis_manifest.json"
    comparability_path = root / "comparability_matrix.csv"

    manifest_path.write_text('{"schema_version":"1.1"}\n', encoding="utf-8")
    ladder_path.write_text('{"assessment":"validated"}\n', encoding="utf-8")
    feature_path.write_text("sample_id,instrument\nsample-a,raman\n", encoding="utf-8")
    context_path.write_text("sample_id\nsample-a\n", encoding="utf-8")
    source_path.write_text("{}\n", encoding="utf-8")
    analysis_path.write_text("{}\n", encoding="utf-8")
    comparability_path.write_text("modality\nraman\n", encoding="utf-8")

    return ValidatedResearchCharacterizationBundle(
        manifest_path=manifest_path,
        manifest={
            "schema_version": "1.1",
            "bundle_type": "materials_characterization_feature_handoff",
        },
        manifest_sha256=sha256_file(manifest_path),
        manifest_size_bytes=manifest_path.stat().st_size,
        feature_path=feature_path,
        sample_context_path=context_path,
        evidence_paths={
            "source_manifest": source_path,
            "analysis_manifest": analysis_path,
            "comparability_matrix": comparability_path,
        },
        feature_table=pd.DataFrame([{"sample_id": "sample-a", "instrument": "raman"}]),
        sample_context=pd.DataFrame([{"sample_id": "sample-a"}]),
        evidence_identity_binding={},
        scientific_evidence_ladder={
            "assessment_sha256": "a" * 64,
            "declaration_sha256": "b" * 64,
            "highest_contiguous_supported_level": "L5_material_domain_validation",
            "first_blocking_level": "L6_independent_external_validation",
            "subject": {"modality": "raman"},
            "readiness": {},
        },
        scientific_evidence_ladder_path=ladder_path,
        scientific_evidence_ladder_file_sha256=sha256_file(ladder_path),
        scientific_evidence_ladder_file_size_bytes=ladder_path.stat().st_size,
        scientific_evidence_ladder_assessment={"assessment_sha256": "a" * 64},
    )


def test_revalidation_rejects_manifest_mutation_after_validation(tmp_path: Path) -> None:
    bundle = _validated_bundle(tmp_path)
    revalidate_characterization_research_bundle_identity(bundle)

    bundle.manifest_path.write_text('{"schema_version":"1.1","changed":true}\n')

    with pytest.raises(ValueError, match="manifest changed after research validation"):
        revalidate_characterization_research_bundle_identity(bundle)


def test_revalidation_rejects_ladder_mutation_after_validation(tmp_path: Path) -> None:
    bundle = _validated_bundle(tmp_path)
    revalidate_characterization_research_bundle_identity(bundle)
    assert bundle.scientific_evidence_ladder_path is not None

    bundle.scientific_evidence_ladder_path.write_text('{"assessment":"changed"}\n')

    with pytest.raises(ValueError, match="assessment changed after research validation"):
        revalidate_characterization_research_bundle_identity(bundle)


def test_public_consumer_rechecks_manifest_immediately_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _validated_bundle(tmp_path)
    monkeypatch.setattr(
        research_bundle,
        "validate_characterization_research_bundle",
        lambda _path: bundle,
    )

    def _consume_then_mutate(*_args: object, **_kwargs: object) -> dict[str, Path]:
        bundle.manifest_path.write_text('{"schema_version":"1.1","changed":true}\n')
        return {}

    monkeypatch.setattr(
        research_bundle,
        "consume_characterization_bundle",
        _consume_then_mutate,
    )

    with pytest.raises(ValueError, match="manifest changed after research validation"):
        consume_characterization_research_bundle(
            bundle.manifest_path,
            tmp_path / "consumer",
        )


def test_public_consumer_rechecks_ladder_immediately_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _validated_bundle(tmp_path)
    monkeypatch.setattr(
        research_bundle,
        "validate_characterization_research_bundle",
        lambda _path: bundle,
    )

    def _consume_then_mutate(*_args: object, **_kwargs: object) -> dict[str, Path]:
        assert bundle.scientific_evidence_ladder_path is not None
        bundle.scientific_evidence_ladder_path.write_text('{"assessment":"changed"}\n')
        return {}

    monkeypatch.setattr(
        research_bundle,
        "consume_characterization_bundle",
        _consume_then_mutate,
    )

    with pytest.raises(ValueError, match="assessment changed after research validation"):
        consume_characterization_research_bundle(
            bundle.manifest_path,
            tmp_path / "consumer",
        )
