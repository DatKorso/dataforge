# Repository Guidelines

This repository hosts a Streamlit multi‑page dashboard. Keep reusable logic in `dataforge/` and page code self‑contained under `pages/`.

## Project Structure & Module Organization
- `app.py` — Streamlit entry point and global page config.
- `pages/` — modules auto‑discovered by Streamlit, named `NN_Icon_Title.py` (e.g., `01_📊_Обзор.py`). UI text in Russian; no cross‑module imports.
- `dataforge/` — shared package (e.g., `utils.py`, validators). Prefer helpers here over duplication; avoid side effects.
- `.streamlit/config.toml` and `.streamlit/secrets.toml` — theme/server and secrets.
- `tests/` — pytest suite mirroring package paths; fixtures in `tests/fixtures/`.

## Build, Test, and Development Commands
- `uv sync` — install project dependencies (editable mode).
- `uv run streamlit run app.py` — run the app locally.
- `ruff check .` / `ruff check --fix .` — lint and auto‑fix style issues.
- `uv pip install -U ruff pytest` — one‑time install of dev tools.
- `pytest -q` — run tests quietly.

## Coding Style & Naming Conventions
- PEP 8; 4‑space indents; max line length 100.
- Public functions use type hints; concise, focused docstrings.
- Names: modules/functions `snake_case`, classes `PascalCase`, constants `UPPER_SNAKE_CASE`.
- Minimize globals; use `st.session_state` for state when needed.
- Keep page modules self‑contained; import shared logic from `dataforge/`.

## Testing Guidelines
- Framework: `pytest`. File names `tests/test_*.py`; fixtures in `tests/fixtures/`.
- Focus on `dataforge` utilities and page‑level helpers.
- Keep tests fast and isolated; avoid network calls and unnecessary I/O.

## Commit & Pull Request Guidelines
- Commits: concise, present tense with scope (e.g., `pages: add data preview tab`, `dataforge: add load_csv helper`).
- PRs: clear description, screenshots for UI changes, steps to verify, and linked issues (e.g., `Closes #123`). Keep diffs focused.

## Security & Configuration Tips
- Never commit secrets; use env vars or `.streamlit/secrets.toml`.
- Validate and limit file uploads (size, type). Never execute user‑provided content.
- Centralize parsing/validation in `dataforge/` to reduce risk.

## Agent‑Specific Instructions
- This file applies repo‑wide. If nested `AGENTS.md` files exist, the deepest one overrides for its subtree.
- Keep changes minimal and consistent; update docs/tests when behavior changes.

## Session bootstrap
- Activate the current dir as project using serena
- If Serena tools are not visible, send message to user in chat about it
- For large repos, index the project to speed up semantic operations
- Prefer symbol-level tools (find_symbol, find_referencing_symbols, insert_after_symbol, replace_symbol_body) over grep-like edits
