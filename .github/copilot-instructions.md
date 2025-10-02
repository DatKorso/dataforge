<!-- Guidance for AI coding agents working on DataForge -->
# DataForge — Copilot playbook

## Quick orientation
- Streamlit multipage app (`app.py`) that orchestrates pages under `pages/` and central helpers in `dataforge/`.
- MotherDuck-hosted DuckDB is the single source of data; every workflow flows through `dataforge.db.get_connection` and `dataforge.schema`.
- Toolchain is UV-managed: run commands as `uv run ...` to pick up the project venv and pins.

## Architecture map
- `app.py` boots Streamlit, applies theme, and reads tokens into `st.session_state`; real work happens inside pages.
- `pages/` modules follow the pattern `setup_page(...)` ➜ optional `guard_page(...)` feature flag ➜ UI + calls into `dataforge.*`. Use `pages/02_📥_Импорт_файлов.py` as the canonical import workflow.
- `dataforge/imports/` is the ingestion pipeline: `reader.read_any` and `google_sheets` fetch files, `validator.normalize_and_validate` standardises them, and `loader.load_dataframe[_partitioned]` writes into DuckDB while recording metadata via `imports.metadata` and `imports.punta_priority`.
- Matching stack lives in `dataforge/matching.py`, `matching_sql.py`, and `similarity_matching.py`; `search_matches` and friends perform batched lookups that power the 🔎 and 🧹 pages.
- Analytics/ops helpers sit in dedicated modules: `campaign_selection.select_campaign_candidates`, `collections.*` for punta collections, `similarity_config.py` for thresholds, and `utils.py` for shared dataframe utilities.

## DuckDB + MotherDuck workflow
- Always open connections through `get_connection(md_token, md_database)`; tokens are injected into `os.environ` and can come from secrets or the Settings page.
- Bootstrap schemas with `schema.init_schema()` before any import or query; it also performs light migrations (e.g. punta column renames).
- After CTAS or partition replaces, call `schema.rebuild_indexes(table=...)` to restore materialised indexes defined in `TableSchema.index_sql`.
- Long-running queries reuse an existing connection (`con` kwarg) instead of reconnecting per call; see `matching._ensure_connection`.

## Import pipeline playbook
- UI collects files + metadata, then `registry.ReportSpec` (see `imports/registry.py`) tells you which assembler + validator combo to run.
- Use `_arrow_safe` (pages/02) before showing frames in Streamlit to coerce binary/object columns to strings and avoid Arrow crashes.
- `load_dataframe_partitioned` wraps DELETE+INSERT in an explicit DuckDB transaction, rebuilds indexes, and logs the import via `set_last_import`; replicate this pattern for new loaders.
- Punta reports often require enriching with collections priority (`collections.get_punta_priority`) and post-load rebuild of `punta_products_codes` via `schema.rebuild_punta_products_codes`.

## Matching and analytics patterns
- Matching inputs are normalised once in `_normalize_barcodes`; reuse it when introducing new query surfaces.
- Batch lookups (`search_matches`, `select_campaign_candidates`) register temp tables and work in one round trip—prefer composing SQL this way over Python loops.
- Confidence and provenance (`matched_by`, `match_score`, `punta_external_code_oz`) travel through the `Match` dataclass, so extend it rather than passing loose dicts.
- Similarity workflows read tuning defaults from `similarity_config.py`; update both config and tests (`test_similarity_matching.py`) together.

## Streamlit conventions
- Call `setup_page()` first and use `guard_page("feature_flag")` to respect `[features]` flags stored in `.streamlit/secrets.toml`.
- Stash MotherDuck credentials and user inputs inside `st.session_state`; the Settings page persists them via `dataforge.secrets.save_secrets`.
- Build complex forms with `st.form`/`st.columns` and clean DataFrames with helpers in `utils.py` (`filter_df_by_brands`, `parse_brand_list`).

## Dev workflow & quality gates
- Install deps: `uv sync` (editable) or `uv venv` + `uv pip install -e .` for ad-hoc envs.
- Run locally: `uv run streamlit run app.py` (see `scripts/start_dataforge.sh` for deployment flags).
- Lint/format: `uv run ruff check --fix .`; type-check with `uv run basedpyright` (config in `pyrightconfig.json`).
- Tests: `uv run pytest -q` (use `-k` for targeted suites like `test_matching.py`). Tests assume DuckDB available but mock MotherDuck credentials.

## When extending the system
- New tables: add a `TableSchema` entry in `schema.py`, populate `index_sql`, update `docs/DB_relations.md`, and write a regression test under `tests/`.
- New imports: register a `ReportSpec`, provide assembler + validator, and ensure the import page exposes user inputs (study Punta flows for reference).
- New analytics pages: gate behind feature flags, lean on existing matching/collections helpers, and log diagnostics to `logs/` similar to Punta workflows.

## Serena MCP automation guidance
- Use Serena project name `dataforge`.
- Use Serena for symbol-level edits (find/replace function bodies, insert helpers).
- Use Serena-run snippets to init schema and run quick DB checks.
- Pass `md_token` and `md_database` explicitly to avoid leaking secrets.

# Use Serena MCP
- If Serena MCP is available, use its tools as the primary way to search and edit code (symbol-level: find symbols/references, targeted insertions/replacements) instead of reading entire files.
- If Serena is not activated or the project is not indexed — ask me to activate the project `dataforge` and start indexing, then continue.
- Before major changes: briefly outline a plan, ask for confirmation, and show a minimal unified diff patch in the response.
- After edits: check build/tests and suggest next steps.