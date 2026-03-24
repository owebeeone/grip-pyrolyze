# Grip-Pyrolyze Bootstrap API

## Purpose

This document defines the smallest useful API for bootstrapping real
`pyrolyze` + `grip-py` applications.

The goal is not to solve the full application-graph design problem.

The goal is to provide:

- one reactive read helper: `use_grip(...)`
- one ambient grip-scope key carried through PyRolyze app context
- one easy way to derive or reuse a named child grip context for a subtree


## Core Idea

The important missing primitive is not a large session API.

It is a small transformed helper that:

1. reads the current ambient grip context
2. derives or reuses a child context by a stable name
3. republishes that child context for descendants
4. renders the passed component inside that overridden scope

That gives us a no-prop-drilling way to move around the grip graph while
keeping authored graph structure explicit.


## What We Reuse From PyRolyze

PyRolyze already has the runtime pieces we need:

- `app_context_override[...]`
- reactive app-context reads
- plain-call runtime locals
- `ExternalStoreRef`

So `grip-pyrolyze` should stay thin.


## Ambient Grip Scope

`grip-pyrolyze` should define one authored app-context key:

```python
GRIP_LOCAL_CONTEXT: AppContextKey[GripContextLike]
```

Meaning:

- this is the current ambient grip scope for the subtree
- `use_grip(GRIP)` reads from this scope when no explicit `ctx` is supplied
- subtree helpers can replace this scope lexically with
  `app_context_override[GRIP_LOCAL_CONTEXT](...)`

If no authored local context is present, `use_grip(...)` falls back to the
session `main_presentation_context`.


## `use_grip`

Author-facing shape:

```python
value = use_grip(GRIP)
value = use_grip(GRIP, ctx)
```

Runtime shape:

```python
def use_grip(
    grip_key,
    ctx: GripContextLike | None = None,
    *,
    __pyrolyze_ctx: PlainCallRuntimeContext = ...,
) -> ExternalStoreRef:
    ...
```

Semantics:

- explicit `ctx` wins
- otherwise read `GRIP_LOCAL_CONTEXT` from PyRolyze app context
- otherwise fall back to the session main presentation context
- subscribe to the underlying grip drip through `ExternalStoreRef`
- unsubscribe cleanly when the slot deactivates or rebinds

This keeps the read side small and unsurprising.


## Generic Grip Context Changer

This should be the main authoring convenience.

Conceptually:

```python
@pyrolyze
def push_grip_context(
    context_name: str,
    func: PyrolyzeComponent,
    **kwargs,
) -> None:
    grip_ctx = use_grip_app_context()
    next_ctx = grip_ctx.make_or_find_child(context_name)
    with app_context_override[GRIP_LOCAL_CONTEXT](next_ctx):
        func(**kwargs)
```

The real implementation details can vary, but the behavior should be:

- read the current effective grip context
- derive or look up a child by some stable parameter
- publish that child for the subtree
- invoke the supplied render function/component within that scope

The important point is that this is a PyRolyze-transformed helper, not a
special compiler feature.


## Why This Helper Matters

It gives us an expedient but useful application-building pattern:

- the caller does not need to drill grip contexts manually
- local graph meaning is still explicit in authored code
- destination-parameter contexts can be introduced where needed
- context changes stay lexical and subtree-bounded

It also creates a natural place to centralize:

- `make_or_find_child(...)`
- naming policy
- child-context reuse semantics
- any later context-massaging behavior


## Context Requirements

The ambient value should be `GripContextLike`, not a raw `GripContext`.

That leaves room for context wrappers or matcher-like context objects later.

The minimum required operations are:

```python
ctx.get_grip_consumer_context()
ctx.get_grip_home_context()
ctx.get_grok()
```

For the context-pusher helper, we also need an authored way to derive or reuse
children. Phase 1 can keep this simple with a method like:

```python
ctx.make_or_find_child(name: str) -> GripContextLike
```

If that ends up not belonging directly on `GripContextLike`, the helper can use
an adapter function instead. The design point is the same.


## Recommended API Surface

Phase 1 should stay small:

```python
GRIP_LOCAL_CONTEXT
GRIP_PYROLYZE_SESSION_KEY
use_grip(...)
push_grip_context(...)
```

Optional helper:

```python
use_grip_app_context()
```

That helper would just return the current ambient grip context or session
fallback, and exists only to keep `push_grip_context(...)` readable.


## Placement

The context-pusher helper should live in `grip-pyrolyze` as a normal
`@pyrolyze` function so it is transformed by the standard PyRolyze pipeline.

That is preferable to inventing a special runtime-only control path.

In other words, the design target is:

- ordinary author-facing helper
- ordinary PyRolyze transformation
- ordinary app-context override

No extra compiler work should be required.


## What This Document Is Not Trying To Solve

This does not settle:

- the full Grok registry/bootstrap policy
- the final application-side graph design vocabulary
- richer context-massaging combinators
- whether child lookup should eventually support typed names or richer keys

Those can come later.

For now, the practical bootstrap story is:

1. `use_grip(...)` reads reactively
2. `push_grip_context(...)` changes the ambient grip scope for a subtree
3. apps can start building real graph-shaped behavior without prop drilling
