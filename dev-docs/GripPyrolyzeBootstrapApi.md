# Grip-Pyrolyze Bootstrap API

## Purpose

This document defines the smallest useful `grip-pyrolyze` API for getting real
PyRolyze + `grip-py` app work moving without waiting for a full
application-graph design to settle.

The goal is not to solve the entire "how should application dataflow graphs be
modeled?" problem.

The goal is to provide a thin bridge so that:

- PyRolyze components can read grip values reactively
- apps can create and reuse stable grip contexts
- one selected Grok can be bound cleanly into one PyRolyze app/render root
- the grip graph stays a first-class graph, not something inferred from the UI
  tree


## Core Observation

The current `src/grip_pyrolyze/core.py` is aiming at the wrong problem.

It tries to make:

```python
count, set_count = use_grip(0)
```

behave like `use_state(...)` backed by a grip atom tap.

That hides graph meaning and overloads the word "grip" into "component-local
state with a different storage backend".

That is not how the working systems are structured:

- `grip-react` uses explicit grips, explicit contexts, and explicit tap
  registration
- `grip-py-demo` uses explicit runtime/session orchestration plus explicit drips
  and taps
- PyRolyze already has `ExternalStoreRef` and invalidation machinery, so it
  does not need a second subscription system

So the first step should not be "state backed by grip".

It should be:

- a Grok selection/bootstrap path
- a read hook
- a stable local-context helper


## Design Constraints

### Must-Have

1. No AST/compiler changes required.
2. No hidden coupling between the grip graph and the PyRolyze UI tree.
3. Multiple Groks must be supported.
4. One selected grip session per PyRolyze app/render root unless the app
   explicitly opts into something else.
5. Proper lifecycle cleanup through PyRolyze app-context teardown.
6. Stable context identity across rerenders where requested.
7. App code must still be able to build arbitrary grip DAG edges directly.

### Strong Preference

1. Keep the public surface tiny.
2. Reuse PyRolyze runtime primitives rather than duplicating them.
3. Keep grips explicit in authored code so graph meaning stays visible.


## Existing Runtime Pieces We Should Reuse

PyRolyze already gives us the important low-level pieces:

- `AppContextKey` for app-scoped lifetime objects
- `app_context_override[...]` for lexical subtree context publication
- `use_app_context(key)` for reactive inherited reads
- `RenderContext(app_context_store=...)` for bootstrap injection
- `PlainCallRuntimeContext` for slot-stable locals
- `ExternalStoreRef` plus built-in invalidation binding

That means `grip-pyrolyze` does not need its own subscription kernel.

It only needs to adapt `grip-py` drips into `ExternalStoreRef` and publish the
current grip scope through PyRolyze app context.


## Recommended Phase-1 Model

## 1. Global Grok Container, Separate From PyRolyze

The design should not center on a per-runtime wrapper object.

Instead, `grip-pyrolyze` should expose a small module-level Grok container with
at least:

```python
set_default_grok(grok)
get_default_grok()
```

Recommended additional named helpers:

```python
register_grok("weather", grok)
get_grok("weather")
```

This container is deliberately separate from PyRolyze. It only answers:

- what Groks exist?
- which one is the default?

PyRolyze then binds one selected Grok into one app/render root through
app-context bootstrap.


## 2. Session Object

The selected Grok should be wrapped in one app-scoped session object.

Suggested shape:

```python
@dataclass(slots=True)
class GripPyrolyzeSession:
    grok: Grok
    main_home_context: GripContext
    main_presentation_context: GripContext
    host_app: object | None = None
```

Important notes:

- do not store `registry` here
- if you have `grok`, you already have access to the registry when needed
- most app code should never need the registry after bootstrap anyway

The important point is that the selected session is explicit and app-scoped.


## 3. RenderContext Bootstrap

The package should provide a concrete way to create a PyRolyze render context
with the selected Grok/session bound into app context:

```python
ctx = create_render_context(host_app=host)
```

Equivalent lower-level shape:

```python
ctx = RenderContext(app_context_store=create_app_context_store(host_app=host))
```

Explicit-grok override should also be supported:

```python
ctx = create_render_context(
    grok=my_grok,
    main_home_context=my_grok.main_home_context,
    main_presentation_context=my_grok.main_presentation_context,
    host_app=host,
)
```

So the bootstrap rule is:

- if explicit Grok/session info is supplied, use it
- otherwise resolve the default Grok from the global container


## 4. Ambient Grip Scope Should Use PyRolyze App Context

This is the important update from the earlier version of this document.

PyRolyze now has a real hierarchical app-context mechanism:

- providers publish lexically with `app_context_override[...]`
- readers consume reactively with `use_app_context(key)`
- the runtime already handles subtree inheritance and rerender invalidation

`grip-pyrolyze` should use that instead of inventing a second ambient-context
mechanism.

So phase 1 should define one authored app-context key:

```python
GRIP_CONTEXT_KEY: AppContextKey[GripContextLike]
```

Meaning:

- this key represents the current ambient grip consumer scope for a subtree
- `use_grip(GRIP)` should read from this key when no explicit `ctx` is passed
- callers that need a subtree-local grip scope should publish it lexically with
  `app_context_override[GRIP_CONTEXT_KEY](ctx)`

This gives us a no-prop-drilling story without adding a `grip-pyrolyze`
specific hidden graph or provider runtime.


## Required Public Helpers

## `use_grip`

Phase-1 meaning:

- read a grip value reactively from the current or supplied grip context

Author-facing shape:

```python
value = use_grip(GRIP)
value = use_grip(GRIP, ctx)
```

Runtime/lowering contract:

```python
def use_grip(
    grip: Grip[T],
    ctx: GripContextLike | None = None,
    *,
    __pyrolyze_ctx: PlainCallRuntimeContext = ...,
) -> ExternalStoreRef[T | None]:
    ...
```

Important points:

- it returns `ExternalStoreRef` at the runtime-helper level
- PyRolyze already knows how to bind that and rerender on updates
- this avoids compiler changes
- the implementation can cache the `Drip`/`ExternalStoreRef` in slot-local
  runtime locals

Semantics:

- if `ctx` is supplied, use `ctx.get_grip_consumer_context()`
- otherwise try `use_app_context(GRIP_CONTEXT_KEY)`
- if no authored override exists, fall back to the selected session's
  `main_presentation_context`
- the ref identity should be stable for `(grok, grip, context.id)`

This is the most important helper in the package.


## `use_local_context`

Phase-1 meaning:

- create one stable child grip context for the current component slot

Suggested signature:

```python
def use_local_context(
    parent: GripContextLike | None = None,
    *,
    priority: int = 0,
    __pyrolyze_ctx: PlainCallRuntimeContext = ...,
) -> GripContext:
    ...
```

Semantics:

- default parent resolution order should be:
  1. explicit `parent`
  2. authored `use_app_context(GRIP_CONTEXT_KEY)`
  3. selected session `main_presentation_context`
- the created child is cached in slot-local runtime state
- on rerender, the same context object is returned

Naming note:

- `grip-react` has `useChildContext(...)` and `useLocalContext(...)`
- the stable slot-cached behavior here is closer to `useLocalContext(...)`
- `use_grip_context(...)` is therefore the wrong name

Why this is needed:

- real apps need stable local contexts
- passing contexts down manually everywhere is noisy
- weather-column-like scenarios need explicit local context identity

What it must not do:

- it must not pretend the grip graph is a tree
- apps are still free to call `add_parent(...)` and `unlink_parent(...)`
  themselves for richer DAG behavior

What it pairs with:

```python
local_ctx = use_local_context()

with app_context_override[GRIP_CONTEXT_KEY](local_ctx):
    ...
```

That is the new default pattern for subtree-local grip scope.


## Explicitly Not Part Of Phase 1

## No Dedicated Grip Context Provider Helper

Phase 1 should not add a custom `grip_scope(...)` or `provide_grip_context(...)`
helper just to wrap what PyRolyze already provides generically.

Use the generic surface directly:

```python
with app_context_override[GRIP_CONTEXT_KEY](ctx):
    ...
```

A convenience wrapper can be added later if real app code proves it is worth
having.

## No `use_grip_tap`

This should not be part of the bootstrap API.

Reasoning:

- taps are where application-side graph meaning gets created
- that should stay explicit for now
- app-scoped taps should be registered in app bootstrap/runtime code
- if a tap genuinely needs component lifecycle, plain PyRolyze effects can do
  that directly without a dedicated `grip-pyrolyze` helper

So phase 1 should not add a tap helper just to save a little boilerplate.


## Optional But Not Required For Phase 1

These are useful, but not required to get real app work moving:

- `use_atom_value_tap(...)`
- `use_multi_atom_value_tap(...)`
- `use_grip_setter(...)`
- `use_grip_updater(...)`
- `use_grip_session(...)`
- graph dump / diagnostics helpers
- named-Grok convenience beyond a very small container API

All of these can wait until there is real application pressure.


## Explicit Non-Goals

The bootstrap API should **not** do these in phase 1:

### 1. No `use_grip(initial)` State Helper

Reject this shape:

```python
count, set_count = use_grip(0)
```

Why:

- it hides graph meaning
- it overloads "grip" to mean "state cell"
- it is too easy to build a large app that uses grip as a slower `use_state`
- it makes it harder to tell what belongs in the explicit grip graph

Use `pyrolyze.use_state(...)` for ordinary component-local state.

Use explicit grips plus `use_grip(...)` when something belongs in the grip
graph.

### 2. No Automatic Graph Inference From UI Structure

Do not infer grip parentage from component nesting or mount layout.

The grip graph is a separate graph on purpose.

### 3. No Large Convenience Zoo Yet

Do not start with React-scale helper breadth. Start with the minimum.


## Recommended Authoring Pattern

Application bootstrap module:

```python
from grip_py import GripRegistry, Grok
from grip_pyrolyze import set_default_grok

REGISTRY = GripRegistry()
GROK = Grok(REGISTRY)
set_default_grok(GROK)
```

App code:

```python
from pyrolyze.api import app_context_override, pyrolyze
from grip_pyrolyze import GRIP_CONTEXT_KEY, use_grip, use_local_context
from .grips import COUNT

@pyrolyze
def counter_panel():
    count = use_grip(COUNT)
    local_ctx = use_local_context()

    with app_context_override[GRIP_CONTEXT_KEY](local_ctx):
        ...
```

Runner:

```python
ctx = create_render_context(host_app=host)
```

Tap registration remains explicit application code:

```python
home = GROK.main_home_context
home.register_tap(my_tap)
```

or, when component lifecycle really matters, plain PyRolyze effects can do it
directly without a dedicated `grip-pyrolyze` helper.


## Why This Is Enough To Start

With just these pieces, an app can already:

- define a registry and grip catalog
- create one or more Groks
- pick one Grok as the default or inject one explicitly
- create taps for state, async data, and action/function grips
- build stable local or shared contexts
- read values reactively in PyRolyze components
- use normal PyRolyze event handlers to call action grips or tap handles

That is enough to start building non-toy apps and discover what higher-level
helpers are genuinely missing.


## Implementation Notes

### `use_grip` can stay very thin

Implementation should be roughly:

1. get selected session from `AppContextKey`
2. if explicit `ctx` exists, use it
3. otherwise try `use_app_context(GRIP_CONTEXT_KEY)`
4. otherwise fall back to `session.main_presentation_context`
5. resolve or create cached `Drip`
6. return `ExternalStoreRef(identity=..., subscribe=..., get=...)`

No custom subscription kernel is needed.

### Keep raw grip types visible

Do not hide `Grip`, `GripContext`, `Grok`, or `Tap` behind a large adapter wall.
The package is a bridge, not a replacement runtime.


## Follow-Up Questions For Later

These should stay out of the bootstrap API decision:

- Should there be atom convenience helpers?
- Should there be a graph visualizer/debug panel integration?
- Should there be a more opinionated application-runtime pattern?
- Should action-grip helpers get first-class ergonomics?

Answer these only after real app code pushes on them.


## Note On The Open-Meteo Demo Concern

The `grip-py-demo` Open-Meteo taps already have both TTL caches and inflight
request tracking for geocode and weather fetches.

So if the demo is still getting throttled, the likely problem is not simply
"there is no cache at all". It is more likely one of:

- request cadence
- key churn
- repeated polling before cached values are reused as expected
- a bug in how async updates are being driven

That should be treated as a separate bug investigation, not folded into the
bootstrap `grip-pyrolyze` API.


## Bottom Line

The first `grip-pyrolyze` API should be deliberately small:

1. global/default Grok container helpers
2. `GripPyrolyzeSession`
3. `create_render_context(...)`
4. `use_grip(...)`
5. `GRIP_CONTEXT_KEY` for authored ambient scope
6. `use_local_context(...)`

Everything else should wait until real app work proves it is necessary.
