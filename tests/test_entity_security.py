import ast
from pathlib import Path

import pytest

from src.platform_core.entity_serialization import serialize_entity
from src.platform_core.scientific_entities import ScientificEntity


def test_entity_artifact_ref_rejects_absolute_and_traversal_paths():
    with pytest.raises(ValueError, match="artifact reference"):
        ScientificEntity(
            entity_id="bad_path",
            entity_type="MeasurementSeriesEntity",
            schema_id="scientific_entity_schema_v2",
            schema_version="2.2.2",
            domain="generic",
            attributes={"independent_variable": "x", "dependent_variable": "y", "axis_metadata": {}},
            artifact_refs=("../outside.csv",),
        )


def test_new_entity_modules_do_not_import_unsafe_serialization_modules():
    unsafe = {"pickle", "cloudpickle", "joblib"}
    for path in [
        Path("src/platform_core/scientific_entities.py"),
        Path("src/platform_core/entity_serialization.py"),
        Path("src/platform_core/schema_evolution.py"),
    ]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        assert not (imports & unsafe)


def test_serialized_entity_record_is_plain_json_metadata():
    entity = ScientificEntity(
        entity_id="composition_demo",
        entity_type="MaterialCompositionEntity",
        schema_id="scientific_entity_schema_v2",
        schema_version="2.2.2",
        domain="materials",
        attributes={"formula": "FeSi", "elements": ["Fe", "Si"], "stoichiometric_amounts": {"Fe": 1, "Si": 1}, "atomic_fractions": {"Fe": 0.5, "Si": 0.5}},
    )
    record = serialize_entity(entity)

    assert record["compact_metadata"]["record_kind"] == "json_safe_entity_record"
    assert "record" in record and "checksum_sha256" in record
