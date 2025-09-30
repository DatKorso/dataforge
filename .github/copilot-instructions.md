<!-- .github/copilot-instructions.md - Guidance for AI coding agents working on DataForge -->
# DataForge — Copilot instructions (concise)

This document summarizes the DataForge project, best practices, and examples — adapted from the repository source and intended as a concise developer guide.

## Project summary & tech stack

- Language: Python 3.10+ (type hints, dataclasses).
- UI: Streamlit multipage app.
  - Entry point: `app.py`.
  - Pages live under `pages/` as modules.
- Data: DuckDB via the `duckdb-python` client; hosted as MotherDuck (dsn `md:`).
- Tooling: UV, ruff, pytest.

## Key repository layout

- `app.py` — Streamlit bootstrap and global page config.
- `pages/` — Streamlit page modules.
- `dataforge/` — core logic and utilities:
  - `db.py` — DuckDB / MotherDuck connection helpers.
  - `schema.py` — Table schemas and schema management.
  - `imports/` — file import pipeline (assemblers, loader, reader, registry, validator).
  - `ui.py` — Streamlit page helpers.
- `docs/` — technical notes.
- `tests/` — pytest suites.

## Streamlit best practices (project-specific)

- Call `dataforge.ui.setup_page()` at the top of a page for consistent layout.
- Use `st.session_state` for per-session state instead of module-level globals.
- Cache deterministic, read-heavy operations with `@st.cache_data`.
- Sanitize DataFrames for Streamlit display (avoid Arrow serialization issues).
- Keep page modules thin and delegate heavy logic to `dataforge/`.

## DuckDB patterns & recommendations

- Use `dataforge.db.get_connection(md_token, md_database)` inside `with` contexts.
- Call `dataforge.schema.init_schema()` before operations that require tables.
- Use `dataforge.imports.loader.load_dataframe` and `load_dataframe_partitioned` for robust loading.
- Rebuild indexes after CTAS/replace operations with `rebuild_indexes()`.
- Use explicit transactions for partitioned/atomic multi-step writes.

## Serena MCP automation guidance

- Use Serena for symbol-level edits (find/replace function bodies, insert helpers).
- Use Serena-run snippets to init schema and run quick DB checks.
- Pass `md_token` and `md_database` explicitly to avoid leaking secrets.

## Representative examples (abridged)

1) Connection helper

```python
# dataforge/db.py
import os
import duckdb

def get_connection(md_token: str | None = None, md_database: str | None = None):
    if md_token:
        os.environ["MOTHERDUCK_TOKEN"] = md_token
    dsn = f"md:{md_database}" if md_database else "md:"
    return duckdb.connect(dsn)
```

2) Safe schema init

```python
# dataforge/schema.py
with get_connection(md_token=..., md_database=...) as con:
    for tbl in get_all_schemas().values():
        con.execute(tbl.create_sql)
```

3) Loader pattern (abridged)

```python
# dataforge/imports/loader.py
con.register("df_to_load", df)
if replace:
    con.execute(f"CREATE OR REPLACE TABLE {quote_ident(table)} AS SELECT * FROM df_to_load")
    rebuild_indexes(...)
```

## Quick-start dev checklist

- `uv sync`
- `uv run streamlit run app.py`
- `ruff check --fix .`
- `pytest -q`