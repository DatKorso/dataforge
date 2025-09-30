# Repository Guidelines

## Project Structure & Module Organization
- `app.py` configures Streamlit and dispatches to page modules; keep it thin.
- `pages/` auto-discovers `NN_Icon_Title.py` modules (e.g., `01_📊_Обзор.py`); keep Russian UI copy local and avoid inter-page imports.
- `dataforge/` hosts shared helpers, validation, and IO; keep logic reusable and side-effect free.
- `.streamlit/` stores `config.toml` for theme/server tweaks and local secrets in `secrets.toml`.
- `tests/` collects pytest suites with fixtures in `tests/fixtures/`; mirror module names when practical.
- `docs/` and `scripts/` hold supporting materials and automation; update when behavior changes.

## Build, Test, and Development Commands
- `uv sync` installs all dependencies in editable mode; rerun after lockfile changes.
- `uv run streamlit run app.py` launches the app locally; watch terminal for runtime warnings.
- `ruff check .` (or `--fix`) enforces formatting and lint rules before commits.
- `pytest -q` runs the test suite quickly; use `-k` to target a module.

## Coding Style & Naming Conventions
- Follow PEP 8 with 4-space indents and ≤100 character lines.
- Public functions need type hints and focused docstrings; prefer explicit return types.
- Use `snake_case` for modules/functions, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants.
- Store state in `st.session_state` rather than module globals; import shared utilities from `dataforge`.

## Testing Guidelines
- Use pytest fixtures from `tests/fixtures/` to isolate IO and stateful dependencies.
- Add regression tests for `dataforge` helpers and any page-level data transforms.
- Keep tests hermetic—no network calls or large file writes; stub external services.

## Commit & Pull Request Guidelines
- Commit messages follow `scope: action` in present tense (e.g., `pages: add data preview tab`).
- Pull requests require a clear summary, verification steps, related issue links (e.g., `Closes #123`), and UI screenshots when relevant.

## Security & Configuration Tips
- Keep secrets in environment variables or `.streamlit/secrets.toml`; never commit them.
- Validate uploads for size and type, and avoid executing user-provided content.
- Centralize parsing and validation in `dataforge` to ensure consistent safeguards.

## Agent-Specific Instructions
- Activate the workspace with Serena tools before editing; prefer symbol-level operations for code.
- Index large repos when searches slow down, and keep diffs targeted with aligned tests/docs.

## Session bootstrap
- Activate the current dir as project using serena.
- If Serena tools are not visible, send message to user in chat about it.
- For large repos, index the project to speed up semantic operations.
- Prefer symbol-level tools (find_symbol, find_referencing_symbols, insert_after_symbol, replace_symbol_body) over grep-like edits.

## Actual package documentation
- Use context7 MCP to get actual data about the package (like 'streamlit', 'pandas', 'duckdb') if needed.
