from src.platform_core.scientific_interfaces import INTERFACE_BOUNDARY


def test_interface_boundary_disallows_config_import_paths_and_raw_reads():
    assert INTERFACE_BOUNDARY["config_import_paths_allowed"] is False
    assert INTERFACE_BOUNDARY["explicit_registry_required"] is True
    assert INTERFACE_BOUNDARY["raw_dataset_read_in_core"] is False
    assert INTERFACE_BOUNDARY["model_execution_in_core"] is False
