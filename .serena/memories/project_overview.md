# Project Overview

- Purpose: Streamlit multi‑page dashboard. Reusable logic lives in `dataforge/`; page modules are self‑contained in `pages/` with UI text in Russian.
- Entrypoint: `app.py` (sets Streamlit global page config and routes to pages).
- Tech stack: Python, Streamlit; tooling: `uv` (dependency management), `ruff` (lint), `pytest` (tests).
- OS context: Darwin (macOS).
- Configuration: `.streamlit/config.toml` (theme/server), `.streamlit/secrets.toml` (secrets; not committed).