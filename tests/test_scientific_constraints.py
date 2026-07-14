import pytest

from src.platform_core.scientific_constraint_registry import (
    ScientificConstraintRegistry,
    build_default_scientific_constraint_registry,
)
from src.platform_core.scientific_constraints import ScientificConstraint, VariableRequirement
from src.platform_core.scientific_evaluators import build_default_evaluator_registry
from src.platform_core.units import build_default_unit_registry


def test_default_scientific_constraints_are_deterministic_and_include_xrd():
    registry = build_default_scientific_constraint_registry()

    ids = [constraint["constraint_id"] for constraint in registry.snapshot()]
    assert ids == sorted(ids)
    assert "xrd.bragg.geometry" in ids
    assert "xrd.scherrer.preconditions" in ids
    assert registry.get("xrd.scherrer.preconditions").equation_display == "D = K lambda / (beta cos(theta))"


def test_constraint_registry_rejects_duplicate_unknown_evaluator_and_bad_units():
    evaluator_registry = build_default_evaluator_registry()
    unit_registry = build_default_unit_registry()
    registry = ScientificConstraintRegistry(evaluator_registry, unit_registry)
    constraint = ScientificConstraint(
        constraint_id="demo.positive",
        name="positive",
        domain="demo",
        category="domain_constraint",
        description="demo",
        evaluator_id="check_positive",
        required_variables=(VariableRequirement("x", expected_unit="nm"),),
        expected_units={"x": "nm"},
        evaluation_role="range_check",
        status="validation_ready",
    )
    registry.register(constraint)

    with pytest.raises(ValueError):
        registry.register(constraint)
    with pytest.raises(KeyError):
        registry.register(
            ScientificConstraint(
                constraint_id="demo.unknown",
                name="unknown",
                domain="demo",
                category="domain_constraint",
                description="demo",
                evaluator_id="missing",
                required_variables=(VariableRequirement("x"),),
            )
        )
    with pytest.raises(KeyError):
        registry.register(
            ScientificConstraint(
                constraint_id="demo.bad_unit",
                name="bad unit",
                domain="demo",
                category="domain_constraint",
                description="demo",
                evaluator_id="check_positive",
                required_variables=(VariableRequirement("x", expected_unit="parsec"),),
                expected_units={"x": "parsec"},
            )
        )


def test_equation_display_is_non_executable_metadata():
    with pytest.raises(ValueError):
        ScientificConstraint(
            constraint_id="demo.eval",
            name="eval",
            domain="demo",
            category="domain_constraint",
            description="demo",
            equation_display="eval('1+1')",
        )

    constraint = build_default_scientific_constraint_registry().get("xrd.bragg.geometry")
    assert constraint.evaluator_id == "check_bragg_geometry"
    assert "lambda" in constraint.equation_display
