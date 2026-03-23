# grip-pyrolyze

Python package for GRIP integration with [PyRolyze](https://github.com/owebeeone/pyrolyze) (or your upstream fork).

- **PyPI project name:** `grip-pyrolyze`
- **Import package:** `grip_pyrolyze`
- **Build backend:** hatchling
- **License:** LGPL-2.1-or-later (see `LICENSE`)

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
