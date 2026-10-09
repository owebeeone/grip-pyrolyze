from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from grip_py import Drip
from pyrolyze.runtime import ExternalStoreRef


class FakeGrok:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object]] = []
        self._drips: dict[tuple[object, object], Drip[Any]] = {}

    def set_drip(self, grip: object, ctx: object, drip: Drip[Any]) -> None:
        self._drips[(grip, ctx)] = drip

    def query(self, grip: object, ctx: object) -> Drip[Any]:
        self.calls.append((grip, ctx))
        return self._drips[(grip, ctx)]


@dataclass(frozen=True, slots=True)
class FakeConsumerContext:
    name: str
    create_child_calls: list[int] = field(default_factory=list, compare=False, hash=False)

    def create_child(self, *, priority: int = 0) -> object:
        self.create_child_calls.append(priority)
        return f"child:{self.name}:{priority}:{len(self.create_child_calls)}"


@dataclass(slots=True)
class FakeGripContext:
    grok: FakeGrok
    consumer_context: FakeConsumerContext

    def get_grip_consumer_context(self) -> FakeConsumerContext:
        return self.consumer_context

    def get_grip_home_context(self) -> FakeConsumerContext:
        return self.consumer_context

    def get_grok(self) -> FakeGrok:
        return self.grok


@dataclass(slots=True)
class FakeSession:
    grok: FakeGrok
    main_home_context: FakeGripContext
    main_presentation_context: FakeGripContext
    host_app: object | None = None


@dataclass(slots=True)
class FakeRuntimeContext:
    app_context: dict[object, object] = field(default_factory=dict)
    authored_context: dict[object, object] = field(default_factory=dict)
    locals: dict[str, object] = field(default_factory=dict)

    def get_or_init_local(self, key: str, factory: Any) -> object:
        if key not in self.locals:
            self.locals[key] = factory()
        return self.locals[key]

    def get_local(self, key: str, default: object | None = None) -> object | None:
        return self.locals.get(key, default)

    def set_local(self, key: str, value: object) -> None:
        self.locals[key] = value

    def get_app_context(self, key: object) -> object:
        return self.app_context[key]

    def has_app_context(self, key: object) -> bool:
        return key in self.app_context

    def get_authored_app_context(self, key: object) -> object:
        if key not in self.authored_context:
            raise LookupError(key)
        return self.authored_context[key]

    def has_authored_app_context(self, key: object) -> bool:
        return key in self.authored_context


@dataclass(slots=True)
class FakeLookupContext:
    drip: Drip[Any]
    lookup_calls: list[object] = field(default_factory=list)
    unsubscribe_calls: int = 0

    def lookup_grip(self, grip: object) -> tuple[Drip[Any], Any]:
        self.lookup_calls.append(grip)

        def unsubscribe() -> None:
            self.unsubscribe_calls += 1

        return self.drip, unsubscribe


def test_use_grip_with_explicit_lookup_context_chains_cleanup() -> None:
    from grip_pyrolyze import use_grip

    explicit = FakeLookupContext(drip=Drip("alpha"))
    runtime = FakeRuntimeContext()

    ref = use_grip("weather", explicit, __pyrolyze_ctx=runtime)

    assert isinstance(ref, ExternalStoreRef)
    assert ref.get() == "alpha"
    assert explicit.lookup_calls == ["weather"]

    notifications: list[str] = []
    unsubscribe = ref.subscribe(lambda: notifications.append("changed"))
    explicit.drip.next("beta")

    assert notifications == ["changed"]

    unsubscribe()
    assert explicit.unsubscribe_calls == 1


def test_use_grip_prefers_authored_context_over_session_default() -> None:
    from grip_pyrolyze import GRIP_CONTEXT_KEY, GRIP_PYROLYZE_SESSION_KEY, use_grip

    grok = FakeGrok()
    session_ctx = FakeGripContext(grok=grok, consumer_context=FakeConsumerContext("session"))
    authored_ctx = FakeGripContext(grok=grok, consumer_context=FakeConsumerContext("authored"))
    session = FakeSession(
        grok=grok,
        main_home_context=session_ctx,
        main_presentation_context=session_ctx,
    )
    grok.set_drip("count", authored_ctx.consumer_context, Drip(21))
    grok.set_drip("count", session_ctx.consumer_context, Drip(7))
    runtime = FakeRuntimeContext(
        app_context={GRIP_PYROLYZE_SESSION_KEY: session},
        authored_context={GRIP_CONTEXT_KEY: authored_ctx},
    )

    ref = use_grip("count", __pyrolyze_ctx=runtime)

    assert ref.get() == 21
    assert grok.calls == [("count", authored_ctx.consumer_context)]


def test_use_grip_falls_back_to_session_main_presentation_context() -> None:
    from grip_pyrolyze import GRIP_PYROLYZE_SESSION_KEY, use_grip

    grok = FakeGrok()
    session_ctx = FakeGripContext(grok=grok, consumer_context=FakeConsumerContext("session"))
    session = FakeSession(
        grok=grok,
        main_home_context=session_ctx,
        main_presentation_context=session_ctx,
    )
    grok.set_drip("count", session_ctx.consumer_context, Drip(7))
    runtime = FakeRuntimeContext(app_context={GRIP_PYROLYZE_SESSION_KEY: session})

    ref = use_grip("count", __pyrolyze_ctx=runtime)

    assert ref.get() == 7
    assert grok.calls == [("count", session_ctx.consumer_context)]


def test_use_grip_child_context_accepts_explicit_parent_without_runtime() -> None:
    from grip_pyrolyze.core import use_grip_child_context

    parent = FakeGripContext(grok=FakeGrok(), consumer_context=FakeConsumerContext("parent"))

    child = use_grip_child_context("weather:A", ctx=parent)

    assert child == "child:parent:0:1"
    assert parent.consumer_context.create_child_calls == [0]


def test_use_grip_child_context_reuses_named_child_for_same_parent() -> None:
    from grip_pyrolyze.core import use_grip_child_context

    parent = FakeGripContext(grok=FakeGrok(), consumer_context=FakeConsumerContext("parent"))

    first = use_grip_child_context("weather:A", ctx=parent)
    second = use_grip_child_context("weather:A", ctx=parent)
    third = use_grip_child_context("weather:B", ctx=parent)

    assert first == second
    assert third != first
    assert parent.consumer_context.create_child_calls == [0, 0]
