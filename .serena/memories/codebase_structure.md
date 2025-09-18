# Codebase Structure

- `app.py` — Streamlit entry point and global page config.
- `pages/` — auto‑discovered modules named `NN_Icon_Title.py` (e.g., `01_📊_Обзор.py`). UI text in Russian; no cross‑module imports between pages.
- `dataforge/` — shared package for reusable helpers (e.g., `utils.py`, validators). Prefer helpers here; avoid side effects.
- `.streamlit/config.toml` — theme/server settings.
- `.streamlit/secrets.toml` — secrets (never committed).
- `tests/` — pytest suite mirroring `dataforge/` paths.
- `tests/fixtures/` — shared pytest fixtures.