def test_import_package() -> None:
    import grip_pyrolyze

    assert grip_pyrolyze.__name__ == "grip_pyrolyze"


def test_use_grip_requires_runtime_context() -> None:
    import pytest

    from grip_pyrolyze import use_grip

    with pytest.raises(RuntimeError, match="use_grip"):
        use_grip(0)
