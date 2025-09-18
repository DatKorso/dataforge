# Testing Guidelines

- Framework: `pytest`.
- Test file names: `tests/test_*.py`; fixtures in `tests/fixtures/`.
- Focus on testing `dataforge` utilities and page‑level helpers.
- Keep tests fast and isolated; avoid network calls and unnecessary I/O.
- Mirror `dataforge/` package paths in `tests/` for clarity.