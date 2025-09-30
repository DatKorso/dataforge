<!-- .github/copilot-instructions.md - Guidance for AI coding agents working on DataForge -->
# DataForge — Copilot instructions (concise)

This file gives focused, actionable instructions for AI coding agents to be immediately productive in this repository.

1. Project overview
   - Multipage Streamlit dashboard (entry: `app.py`) with UI pages under `pages/` and reusable logic in `dataforge/`.
   - Uses UV as the package manager; DB integration is with MotherDuck (DuckDB cloud).

2. Where to look first (high value files)
   - `app.py` — streamlit bootstrap and page registration.
   - `pages/` — self-contained UI pages (Russian copy). No cross-page imports.
   - `dataforge/` — core business logic: `db.py`, `schema.py`, `matching.py`, `collections.py`, `secrets.py`, `utils.py`, `ui.py`.
   - `tests/` — pytest suites mirroring `dataforge/` structure; fixtures in `tests/fixtures/`.

3. Editing rules and boundaries
   - Keep pages thin; import shared behavior from `dataforge/`.
   - Avoid module-level globals; use `st.session_state` for Streamlit state.
   - Database operations must use `dataforge.db.get_connection()` context manager and accept `md_token/md_database` where appropriate.
   - Do not commit secrets; use `.streamlit/secrets.toml` or environment variables.

4. Developer workflows & commands
   - Install & manage deps: use UV commands (`uv sync`, `uv venv`, `uv pip install -e .`).
   - Run app: `uv run streamlit run app.py` (or `streamlit run app.py`).
   - Lint: `ruff check .` (auto-fix: `ruff check --fix .`).
   - Tests: `pytest -q` (target: `pytest -k test_matching` or specific files under `tests/`).

5. Important project patterns (do these exactly)
   - MotherDuck connections: always use `with get_connection(...) as con:` then `con.execute(...).fetch_df()`.
   - Schema init: call `dataforge.schema.init_schema()` before running table-dependent operations or tests that require tables.
   - Matching API: prefer `dataforge.matching.search_matches()` / `find_wb_by_oz()` — they return TypedDict `Match` objects with `match_score` and `matched_by`.
   - Collection updates: Punta imports replace data for a single `collection` key; look at `dataforge/collections.py` and `docs/README.md` for specific behavior.

6. Tests and fixtures
   - Tests mirror implementation; use fixtures in `tests/fixtures/` to stub DB and file IO.
   - Keep tests hermetic — avoid network I/O; stub MotherDuck with fixtures or small in-memory duckdb instances.

7. Commit and PR conventions
   - Commit message format: `scope: action` (e.g., `matching: add barcode normalization`).
   - Update tests and docs alongside behavior changes.

8. When editing code as an AI agent
   - Activate project with Serena MCP before edits; prefer symbol-level edits (e.g., replace_symbol_body) over global text edits.
   - Run `ruff` and `pytest` locally after changes; keep commits small and targeted.
   - If you can't confirm a runtime (MotherDuck) behavior locally, add integration notes and a small unit test that isolates logic.

9. Quick examples to reference
   - DB usage: see `dataforge/db.py` and examples in `CLAUDE.md`.
   - Schema patterns: `dataforge/schema.py` (init, rebuild_indexes).
   - Matching logic: `dataforge/matching.py` (search_matches, rebuild_matches).

10. Ask for clarification when:
    - You need production credentials (do not request or log secrets).
    - A change affects Streamlit UI state across pages — ask how state should persist.

If anything here is unclear or you want additional examples (small tests, expanded patterns, or a checklist for PR reviewers), tell me which areas to expand.

## Session bootstrap
- Activate the current dir as project using serena.
- If Serena tools are not visible, send message to user in chat about it.
- For large repos, index the project to speed up semantic operations.
- Prefer symbol-level tools (find_symbol, find_referencing_symbols, insert_after_symbol, replace_symbol_body) over grep-like edits.

## Actual package documentation
- Use context7 MCP to get actual data about the package (like 'streamlit', 'pandas', 'duckdb') if needed.
