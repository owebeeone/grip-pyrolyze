# grip-pyrolyze

Python package for GRIP integration with [PyRolyze](https://github.com/owebeeone/pyrolyze) (or your upstream fork).

- **PyPI project name:** `grip-pyrolyze`
- **Import package:** `grip_pyrolyze`
- **Build backend:** hatchling
- **License:** LGPL-2.1-or-later (see `LICENSE`)

## `use_grip`

`grip_pyrolyze.core.use_grip` mirrors `pyrolyze.hooks.use_state` (same `PlainCallRuntimeContext` signature) but stores each value in a `grip-py` atom tap registered on a per–`RenderContext` GRIP session (`AppContextKey`). PyRolyze examples can `from grip_pyrolyze import use_grip` and compile like `use_state`.

## Local development

```bash
git clone git@github.com:owebeeone/grip-pyrolyze.git
cd grip-pyrolyze
pip install -e .
```

## Tests

```bash
uv run --with pytest --with pytest-cov pytest -q
```

Or with `PYTHONPATH=src`:

```bash
pytest
```

## Build distributions

```bash
python -m pip install build
python -m build
```
