import pytest

from src.platform_core.adapters import AdapterExecutionPolicy, AdapterMetadata


def _adapter(**overrides):
    values = {
        "adapter_id": "demo_trust",
        "plugin_id": "demo",
        "case_study_id": "demo",
        "stage": "trust",
        "module_path": "scripts/demo.py",
        "callable_name": "main",
        "execution_mode": "dry_run_safe",
        "required_artifacts": ("demo_input",),
        "produced_artifacts": ("demo_output",),
        "execution_policy": AdapterExecutionPolicy(writes_outputs=True),
        "executable_status": "executable_disabled",
        "blocked_reasons": ("actual_execution_disabled",),
    }
    values.update(overrides)
    return AdapterMetadata(**values)


def test_adapter_execution_policy_disables_actual_execution():
    policy = AdapterExecutionPolicy(writes_outputs=True)

    assert policy.safe_for_dry_run is True
    assert policy.safe_for_manifest_only is True
    assert policy.execution_allowed is False

    with pytest.raises(ValueError, match="must not allow actual execution"):
        AdapterExecutionPolicy(execution_allowed=True)


def test_adapter_rejects_invalid_stage_or_executable_mode():
    with pytest.raises(ValueError, match="unsupported adapter stage"):
        _adapter(stage="not_a_stage")

    with pytest.raises(ValueError, match="cannot be executable"):
        _adapter(execution_mode="executable_future")


def test_adapter_serialization_has_no_execution_permission():
    payload = _adapter().to_dict()

    assert payload["adapter_id"] == "demo_trust"
    assert payload["execution_allowed"] is False
    assert payload["network_required"] is False
    assert payload["model_training_required"] is False
