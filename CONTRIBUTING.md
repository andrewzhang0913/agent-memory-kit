# Contributing to agent-memory-kit

Thanks for your interest in improving agent-memory-kit.

## Development setup

```bash
python3.12 -m venv .venv && source .venv/bin/activate   # any interpreter >= 3.10
pip install -e ".[dev]"
pytest -q            # expect all green
python examples/quickstart.py
```

The core is intentionally **stdlib-only with zero runtime dependencies** and
must run offline. Please do not add required dependencies to the core, and do
not weaken `requires-python = ">=3.10"`.

## Running the checks

- `pytest -q` — the full test suite must stay green.
- `python examples/quickstart.py` — must run to completion. With no local LLM
  reachable, the distill step degrades gracefully and the script still finishes;
  that is a PASS.

## Pull requests

1. Fork, branch from `main`.
2. Add a test that fails before your change and passes after.
3. Keep the core dependency-free; put optional integrations behind extras.
4. Update `CHANGELOG.md` under `[Unreleased]`.
5. Confirm no personal data / secrets / private hosts are introduced.

## Welcome contributions

An embedded vector recall backend (e.g. **sqlite-vec**) implementing the
`RecallBackend` protocol is explicitly welcome — see
[`docs/recall-backends.md`](docs/recall-backends.md). The shipped Hermes/LanceDB
path is only a reference adapter for the backend contract.
