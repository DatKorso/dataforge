# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Environment Setup
```bash
uv sync                              # Install all dependencies in editable mode
```

### Running the Application
```bash
uv run streamlit run app.py          # Launch the dashboard locally
streamlit run app.py                 # Alternative (if activated in shell)
```

### Code Quality
```bash
ruff check .                         # Run linter
ruff check --fix .                   # Auto-fix linting issues
```

### Testing
```bash
pytest -q                            # Run all tests (quiet mode)
pytest -k test_matching              # Run specific test module
pytest tests/test_collections.py    # Run single test file
```

## Architecture Overview

### Application Structure
This is a **multipage Streamlit dashboard** connected to **MotherDuck** (cloud DuckDB). The architecture separates UI pages from reusable business logic:

- **`app.py`**: Entry point that configures Streamlit's global page settings and displays the landing page
- **`pages/`**: Auto-discovered page modules following the naming pattern `NN_Icon_Title.py` (e.g., `01_📊_Обзор.py`)
  - Pages contain Russian UI text and are self-contained
  - **No cross-imports between pages**; import shared logic from `dataforge/` instead
- **`dataforge/`**: Python package containing all reusable business logic, organized by concern:
  - `db.py` — MotherDuck connection management
  - `secrets.py` — Read/write `.streamlit/secrets.toml` for credentials
  - `schema.py` — Table schema definitions and initialization
  - `matching.py` — Cross-platform product matching (Ozon ↔ Wildberries via barcodes)
  - `collections.py` — Punta collection priority management
  - `utils.py` — General-purpose utilities
  - `ui.py` — Shared UI components and helpers
  - `imports/` — Import-specific logic (subdirectory)

### Key Architectural Patterns

#### MotherDuck Connection Pattern
All database operations use the connection helper from `dataforge/db.py`:
```python
from dataforge.db import get_connection

with get_connection(md_token=token, md_database=db) as con:
    df = con.execute("SELECT ...").fetch_df()
```
- Connection parameters can come from environment (`MOTHERDUCK_TOKEN`) or explicit arguments
- Use context manager (`with`) to ensure proper connection cleanup
- `check_connection()` validates connectivity without executing business logic

#### Schema Initialization Pattern
Database tables are defined in `dataforge/schema.py` as `TableSchema` dataclasses:
- `init_schema()` creates all tables and indexes if they don't exist
- Call `init_schema()` at the start of database-dependent operations
- `rebuild_indexes()` recreates indexes for performance optimization
- Table schemas are hardcoded for stability and explicit control

#### Product Matching System
The `dataforge/matching.py` module implements cross-platform matching:
- Matches products between Ozon (oz) and Wildberries (wb) using barcode overlap
- Primary logic: `search_matches()`, `find_wb_by_oz()`, `find_oz_by_wb()`
- Returns `Match` TypedDict with confidence scoring (`match_score`, `matched_by`, `confidence_note`)
- Matching strategies: primary-to-primary (highest confidence) down to any-to-any (lowest)
- `rebuild_matches()` and `rebuild_barcode_index()` regenerate denormalized match tables

#### Session State Management
Streamlit pages use `st.session_state` for maintaining UI state across reruns:
```python
if "my_key" not in st.session_state:
    st.session_state.my_key = initial_value
```
- Avoid module-level globals; prefer `st.session_state` for stateful data
- Keep session state keys scoped to the page when possible

### Code Organization Principles
1. **Separation of Concerns**: UI (pages) vs business logic (dataforge) vs configuration (.streamlit)
2. **No Side Effects**: Functions in `dataforge/` should be pure or explicit about side effects
3. **Explicit Dependencies**: All MotherDuck operations accept `md_token` and `md_database` parameters
4. **Type Safety**: Use type hints for public functions and dataclasses/TypedDict for structured data

## Coding Conventions

### Style
- **PEP 8** with 4-space indentation, max 100 characters per line
- Type hints required for public functions; explicit return types preferred
- Docstrings for public APIs; focus on parameters, returns, and behavior

### Naming
- `snake_case` for modules, functions, variables
- `PascalCase` for classes
- `UPPER_SNAKE_CASE` for constants
- Private helpers prefix with `_` (e.g., `_normalize_barcodes`)

### Imports
- Use `from __future__ import annotations` for forward references
- Group imports: standard library → third-party → local modules
- Prefer explicit imports over wildcards

## Testing Guidelines
- Test files mirror `dataforge/` structure in `tests/`
- Fixtures live in `tests/fixtures/` for shared test dependencies
- Focus tests on `dataforge` utilities; page-level logic is harder to unit test
- Keep tests **fast and isolated**: no network calls, no large file I/O
- Stub external services (DuckDB connections, file uploads) using pytest fixtures

## Security & Configuration
- **Never commit secrets**: Use `.streamlit/secrets.toml` (gitignored) or environment variables
- Validate file uploads: check size limits and file types before processing
- Avoid executing user-provided content or dynamic SQL without sanitization
- Centralize validation logic in `dataforge/` for consistency

## Session Bootstrap (for AI Agents)
- Activate the project using Serena MCP before editing: `activate_project("dataforge")`
- Prefer symbol-level operations (`find_symbol`, `replace_symbol_body`) over text-based edits
- Use Context7 MCP for up-to-date documentation on `streamlit`, `pandas`, `duckdb` APIs

## Commit Guidelines
- Format: `scope: action` in present tense (e.g., `matching: add barcode normalization`)
- Scopes: `app`, `pages`, `dataforge`, `tests`, `docs`, `config`
- Include test updates when changing behavior