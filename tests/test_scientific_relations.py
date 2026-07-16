import pytest

from src.platform_core.scientific_relations import RelationExecutionReference, ScientificRelation, default_scientific_relations


def test_default_relations_separate_display_equation_from_operator():
    bragg = next(item for item in default_scientific_relations() if item.relation_id == "xrd.bragg.d_spacing")

    assert bragg.equation_display
    assert bragg.operator_id == "xrd_bragg_uncertainty_v2_2"
    assert bragg.execution_status == "registered_operator_required"


def test_arbitrary_relation_import_metadata_rejected():
    with pytest.raises(ValueError, match="arbitrary module_path"):
        RelationExecutionReference(
            operator_id="bad",
            execution_status="metadata_only",
            module_path="user.config.module",
        )


def test_relation_category_validation():
    with pytest.raises(ValueError, match="unsupported relation category"):
        ScientificRelation(
            relation_id="bad",
            relation_version="1",
            category="call_user_function",
            input_entity_types=(),
            output_entity_types=(),
        )
