def test_import_package() -> None:
    import grip_pyrolyze

    assert grip_pyrolyze.__name__ == "grip_pyrolyze"
    assert hasattr(grip_pyrolyze, "define_grip")
    assert hasattr(grip_pyrolyze, "push_grip_context")


def test_use_grip_requires_runtime_context() -> None:
    import pytest

    from grip_pyrolyze import use_grip

    with pytest.raises(RuntimeError, match="use_grip"):
        use_grip(0)


def test_define_grip_registers_on_default_registry() -> None:
    from grip_pyrolyze import define_grip
    from grip_pyrolyze.core import GRIP_DEFAULT_REGISTRY

    grip = define_grip("TestDefineGrip", 42)

    assert grip.name == "TestDefineGrip"
    assert grip.default == 42
    assert GRIP_DEFAULT_REGISTRY.get_by_key(grip.key) is grip


def test_session_defaults_follow_default_grok() -> None:
    from grip_pyrolyze import GripPyrolyzeSession
    from grip_pyrolyze.core import GRIP_DEFAULT_GROK

    session = GripPyrolyzeSession()

    assert session.grok is GRIP_DEFAULT_GROK
    assert session.main_presentation_context is GRIP_DEFAULT_GROK.main_presentation_context
