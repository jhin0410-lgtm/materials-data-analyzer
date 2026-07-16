import json

from src.platform_core.materials_project_adapters import MaterialsProjectTargetAdapter


def test_mp_target_uncertainty_is_unavailable_not_zero():
    fixture = json.loads(open("configs/examples/materials_project_structure_entity_conversion.json", encoding="utf-8").read())
    quantity = MaterialsProjectTargetAdapter().to_quantity(fixture["summary"])

    assert quantity.value is not None
    uncertainty = quantity.value.uncertainty
    assert uncertainty.kind == "unavailable"
    assert uncertainty.value is None
    assert uncertainty.method == "source_does_not_provide_uncertainty"
