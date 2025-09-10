# Repository Guidelines

This repository contains a Streamlit multipage dashboard. Use `dataforge/` for shared
logic, keep page modules self-contained, and verify changes with linting and tests.

## Project Structure & Module Organization
- `app.py` — Streamlit entry point and global page config.
- `pages/` — multipage modules auto-discovered by Streamlit. Name as
  `NN_Icon_Title.py` (e.g., `01_📊_Overview.py`). Keep code self-contained; UI text in
  Russian.
- `dataforge/` — shared Python package (e.g., `utils.py`). Put reusable logic and
  validation here; import from pages.
- `.streamlit/config.toml` — theme/server settings. Secrets via
  `.streamlit/secrets.toml`.
- `pyproject.toml` — project metadata, `uv` config, and `ruff` settings.

## Build, Test, and Development Commands
- Install deps (editable): `uv sync`
- Run app: `uv run streamlit run app.py`
- Lint: `ruff check .`  (auto-fix: `ruff check --fix .`)
- Add dev tools (once): `uv pip install -U ruff pytest`
- Run tests: `pytest -q`

## Coding Style & Naming Conventions
- PEP 8, 4-space indents, max line length 100.
- Type hints on public functions; concise, focused docstrings.
- Naming: modules/functions `snake_case`, classes `PascalCase`, constants `UPPER_SNAKE_CASE`.
- Prefer helpers in `dataforge/` over duplicating logic. Avoid side effects; limit globals to
  `st.session_state` when necessary.

## Testing Guidelines
- Framework: `pytest`. Place tests under `tests/`, mirroring package paths.
- Filenames: `tests/test_*.py`; fixtures under `tests/fixtures/`.
- Focus on `dataforge` utilities and page-level helpers. Keep tests fast and isolated; avoid
  network and unnecessary I/O.
- Run locally with `pytest -q` before submitting.

## Commit & Pull Request Guidelines
- Commits: concise, present tense (e.g., `pages: add data preview tab`,
  `dataforge: add load_csv helper`).
- PRs: clear description, screenshots for UI changes, steps to verify, and linked issues
  (e.g., `Closes #123`). Keep diffs focused and aligned with this guide.

## Security & Configuration Tips
- Do not commit secrets. Use env vars or `.streamlit/secrets.toml`.
- Validate and limit file uploads (size, type). Never execute user-provided content.
- Centralize validation and parsing in `dataforge/` to reduce risk.

## Agent-Specific Instructions
- These guidelines apply repo-wide. If nested `AGENTS.md` files exist, the deepest one
  takes precedence for its subtree.
- Keep changes minimal and consistent with existing code. Update docs/tests when changing
  behavior.