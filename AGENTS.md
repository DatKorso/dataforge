# Repository Guidelines

## Project Structure & Module Organization
- `app.py` — Streamlit entry point and global page config.
- `pages/` — auto‑discovered pages named `NN_Icon_Title.py` (e.g., `01_📊_Обзор.py`). UI text is Russian; avoid cross‑imports between pages.
- `dataforge/` — shared package (e.g., `utils.py`, validators). Keep reusable logic here; avoid side effects.
- `.streamlit/` — `config.toml` (theme/server), `secrets.toml` (local secrets).
- `tests/` — pytest suite; fixtures in `tests/fixtures/`.

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
- Minimize globals; prefer `st.session_state` for state. Keep page modules self‑contained; import shared helpers from `dataforge/`.

## Testing Guidelines
- Framework: `pytest`. Test files: `tests/test_*.py`; fixtures: `tests/fixtures/`.
- Focus on `dataforge` utilities and page‑level helpers.
- Keep tests fast and isolated; avoid network calls and unnecessary I/O.

## Commit & Pull Request Guidelines
- Commits: concise, present tense with scope (e.g., `pages: add data preview tab`, `dataforge: add load_csv helper`).
- PRs: clear description, steps to verify, linked issues (e.g., `Closes #123`), and screenshots for UI changes. Keep diffs focused.

## Security & Configuration Tips
- Never commit secrets; use env vars or `.streamlit/secrets.toml`.
- Validate and limit file uploads (size/type). Never execute user‑provided content.
- Centralize parsing/validation in `dataforge/` to reduce risk.

## Agent‑Specific Instructions
- This file applies repo‑wide; deeper `AGENTS.md` overrides for its subtree.
- Activate the current directory as project (Serena). Prefer symbol‑level tools for edits; index large repos when needed.
- Keep changes minimal and consistent; update docs/tests when behavior changes.

## Session bootstrap
- Activate the current dir as project using serena
- If Serena tools are not visible, send message to user in chat about it
- For large repos, index the project to speed up semantic operations
- Prefer symbol-level tools (find_symbol, find_referencing_symbols, insert_after_symbol, replace_symbol_body) over grep-like edits
