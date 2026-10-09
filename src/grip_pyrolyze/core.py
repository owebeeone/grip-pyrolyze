#@pyrolyze
"""GRIP-backed reactive hooks and context helpers for PyRolyze."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar, cast

from grip_py import Drip, Grip, GripContext, GripContextLike, GripRegistry, Grok
from pyrolyze.api import app_context_override, pyrolyze
from pyrolyze.runtime import AppContextKey, ExternalStoreRef, PlainCallRuntimeContext


T = TypeVar("T")


GRIP_DEFAULT_REGISTRY = GripRegistry()
GRIP_DEFAULT_GROK = Grok(registry=GRIP_DEFAULT_REGISTRY)

define_grip = GRIP_DEFAULT_REGISTRY.add

_NAMED_CHILD_CONTEXTS: dict[tuple[int, int, str, int], GripContext] = {}

@dataclass(slots=True)
class GripPyrolyzeSession:
    grok: Grok = field(default_factory=lambda: GRIP_DEFAULT_GROK)
    main_home_context: GripContext = field(
        default_factory=lambda: GRIP_DEFAULT_GROK.main_home_context,
    )
    main_presentation_context: GripContext = field(
        default_factory=lambda: GRIP_DEFAULT_GROK.main_presentation_context,
    )
    host_app: object | None = None


def _missing_session(_host_app: object | None) -> GripPyrolyzeSession:
    raise RuntimeError("grip-pyrolyze session is not configured")


def _missing_ambient_grip_context(_host_app: object | None) -> GripContextLike:
    raise LookupError("no authored ambient grip context is available")


GRIP_PYROLYZE_SESSION_KEY = AppContextKey(
    debug_name="grip_pyrolyze.session",
    factory=_missing_session,
    close=None,
)

GRIP_CONTEXT_KEY = AppContextKey(
    debug_name="grip_pyrolyze.context",
    factory=_missing_ambient_grip_context,
    close=None,
)

# Alias kept for the naming used in the design discussion/docs.
GRIP_LOCAL_CONTEXT = GRIP_CONTEXT_KEY


def use_grip_app_context(
    *,
    ctx: GripContextLike | None = None,
    __pyrolyze_ctx: PlainCallRuntimeContext = cast(Any, None),
) -> GripContextLike:
    if __pyrolyze_ctx is None:
        raise RuntimeError("use_grip_app_context() requires a pyrolyze plain-call runtime context")
    if ctx is not None:
        return ctx
    return _resolve_ambient_context(__pyrolyze_ctx)


def use_grip_child_context(
    context_name: str,
    *,
    ctx: GripContextLike | None = None,
    priority: int = 0,
    __pyrolyze_ctx: PlainCallRuntimeContext = cast(Any, None),
) -> GripContext:
    if ctx is not None:
        parent_ctx = ctx
    else:
        if __pyrolyze_ctx is None:
            raise RuntimeError("use_grip_child_context() requires a pyrolyze plain-call runtime context")
        parent_ctx = use_grip_app_context(__pyrolyze_ctx=__pyrolyze_ctx)
    return _get_or_create_named_child_context(parent_ctx, context_name, priority=priority)


def _get_or_create_named_child_context(
    parent_ctx: GripContextLike,
    context_name: str,
    *,
    priority: int,
) -> GripContext:
    consumer_ctx = parent_ctx.get_grip_consumer_context()
    cache_key = (id(parent_ctx.get_grok()), id(consumer_ctx), context_name, priority)
    existing = _NAMED_CHILD_CONTEXTS.get(cache_key)
    if existing is not None:
        return existing

    child = consumer_ctx.create_child(priority=priority)
    _NAMED_CHILD_CONTEXTS[cache_key] = child
    return child


@pyrolyze
def push_grip_context(
    context_name: str,
    func: Callable[..., None],
    **kwargs: Any,
) -> None:
    __pyrolyze_ctx = cast(PlainCallRuntimeContext | None, kwargs.pop("__pyrolyze_ctx", None))
    next_ctx = use_grip_child_context(context_name, __pyrolyze_ctx=cast(Any, __pyrolyze_ctx))
    with app_context_override[GRIP_LOCAL_CONTEXT](next_ctx):
        func(**kwargs)


def use_grip(
    grip_key: object,
    ctx: GripContextLike | object | None = None,
    *,
    __pyrolyze_ctx: PlainCallRuntimeContext = cast(Any, None),
) -> ExternalStoreRef[T | None]:
    """Return a reactive external-store view for ``grip_key``."""
    if ctx is not None:
        return cast(ExternalStoreRef[T | None], _resolve_explicit_context_ref(ctx, grip_key))

    if __pyrolyze_ctx is None:
        raise RuntimeError("use_grip() requires a pyrolyze plain-call runtime context")

    resolved_ctx = _resolve_ambient_context(__pyrolyze_ctx)
    return cast(ExternalStoreRef[T | None], _ref_from_grip_context(resolved_ctx, grip_key))


def _resolve_ambient_context(__pyrolyze_ctx: PlainCallRuntimeContext) -> GripContextLike:
    try:
        authored = __pyrolyze_ctx.get_authored_app_context(GRIP_CONTEXT_KEY)
    except LookupError:
        authored = None

    if authored is not None:
        if not isinstance(authored, GripContextLike):
            raise TypeError("GRIP_CONTEXT_KEY must resolve to a GripContextLike value")
        return authored

    session = cast(GripPyrolyzeSession, __pyrolyze_ctx.get_app_context(GRIP_PYROLYZE_SESSION_KEY))
    return session.main_presentation_context


def _resolve_explicit_context_ref(
    ctx: GripContextLike | object,
    grip_key: object,
) -> ExternalStoreRef[Any]:
    lookup = getattr(ctx, "lookup_grip", None)
    if callable(lookup):
        payload = lookup(grip_key)
        return _coerce_lookup_payload(payload, extra_unsubscribe=_callable_attr(ctx, "unsubscribe"))

    if isinstance(ctx, GripContextLike):
        return _ref_from_grip_context(
            ctx,
            grip_key,
            extra_unsubscribe=_callable_attr(ctx, "unsubscribe"),
        )

    raise TypeError("use_grip() explicit ctx must be a GripContextLike or expose lookup_grip(grip)")


def _ref_from_grip_context(
    ctx: GripContextLike,
    grip_key: object,
    *,
    extra_unsubscribe: Callable[[], None] | None = None,
) -> ExternalStoreRef[Any]:
    consumer_ctx = ctx.get_grip_consumer_context()
    drip = ctx.get_grok().query(grip_key, consumer_ctx)
    return _ref_from_drip(drip, extra_unsubscribe=extra_unsubscribe)


def _coerce_lookup_payload(
    payload: object,
    *,
    extra_unsubscribe: Callable[[], None] | None = None,
) -> ExternalStoreRef[Any]:
    if isinstance(payload, tuple):
        if len(payload) != 2:
            raise TypeError("lookup_grip() tuple results must be (source, unsubscribe)")
        source, unsubscribe = payload
        return _coerce_lookup_payload(
            source,
            extra_unsubscribe=_chain_unsubscribe(
                _coerce_unsubscribe(unsubscribe),
                extra_unsubscribe,
            ),
        )

    if isinstance(payload, ExternalStoreRef):
        return _with_extra_unsubscribe(payload, extra_unsubscribe)

    if isinstance(payload, Drip):
        return _ref_from_drip(payload, extra_unsubscribe=extra_unsubscribe)

    ref_method = getattr(payload, "ref", None)
    if callable(ref_method):
        ref = ref_method()
        if not isinstance(ref, ExternalStoreRef):
            raise TypeError("lookup_grip().ref() must return an ExternalStoreRef")
        return _with_extra_unsubscribe(ref, extra_unsubscribe)

    if callable(getattr(payload, "subscribe", None)) and callable(getattr(payload, "get", None)):
        return _with_extra_unsubscribe(
            ExternalStoreRef(
                identity=payload,
                subscribe=cast(
                    Callable[[Callable[[], None]], Callable[[], None]],
                    payload.subscribe,
                ),
                get=cast(Callable[[], Any], payload.get),
            ),
            extra_unsubscribe,
        )

    raise TypeError("lookup_grip() must return a Drip, ExternalStoreRef, or (source, unsubscribe)")


def _ref_from_drip(
    drip: Drip[Any],
    *,
    extra_unsubscribe: Callable[[], None] | None = None,
) -> ExternalStoreRef[Any]:
    def subscribe(listener: Callable[[], None]) -> Callable[[], None]:
        initialized = False

        def on_change(_value: object | None) -> None:
            nonlocal initialized
            if not initialized:
                initialized = True
                return
            listener()

        unsubscribe = drip.subscribe_priority(on_change)
        return _chain_unsubscribe(unsubscribe, extra_unsubscribe)

    return ExternalStoreRef(
        identity=drip,
        subscribe=subscribe,
        get=drip.get,
    )


def _with_extra_unsubscribe(
    ref: ExternalStoreRef[Any],
    extra_unsubscribe: Callable[[], None] | None,
) -> ExternalStoreRef[Any]:
    if extra_unsubscribe is None:
        return ref

    def subscribe(listener: Callable[[], None]) -> Callable[[], None]:
        unsubscribe = ref.subscribe(listener)
        return _chain_unsubscribe(unsubscribe, extra_unsubscribe)

    return ExternalStoreRef(
        identity=ref.identity,
        subscribe=subscribe,
        get=ref.get,
    )


def _callable_attr(value: object, name: str) -> Callable[[], None] | None:
    candidate = getattr(value, name, None)
    if callable(candidate):
        return cast(Callable[[], None], candidate)
    return None


def _coerce_unsubscribe(value: object) -> Callable[[], None] | None:
    if value is None:
        return None
    if not callable(value):
        raise TypeError("lookup_grip() unsubscribe must be callable or None")
    return cast(Callable[[], None], value)


def _chain_unsubscribe(
    first: Callable[[], None] | None,
    second: Callable[[], None] | None,
) -> Callable[[], None]:
    def unsubscribe() -> None:
        if first is not None:
            first()
        if second is not None:
            second()

    return unsubscribe


__all__ = [
    "GRIP_CONTEXT_KEY",
    "GRIP_DEFAULT_GROK",
    "GRIP_DEFAULT_REGISTRY",
    "GRIP_LOCAL_CONTEXT",
    "GRIP_PYROLYZE_SESSION_KEY",
    "GripPyrolyzeSession",
    "define_grip",
    "push_grip_context",
    "use_grip",
    "use_grip_app_context",
    "use_grip_child_context",
]
