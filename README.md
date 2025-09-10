# DataForge – Multipage Streamlit Dashboard (UV)

This is a minimal, production-friendly scaffold for a multipage Streamlit app, using the UV package manager.

## Quickstart

1) Create a virtual environment with UV and install deps:

```
uv venv
uv pip install -r <(uv pip compile pyproject.toml)
```

Alternatively, to install directly from `pyproject.toml`:

```
uv pip install -e .
```

2) Run the app:

```
streamlit run app.py
```

The multipage routes live under `pages/` and will appear in the sidebar automatically.

## Structure

```
.
├─ app.py                 # Landing page
├─ pages/                 # Additional pages auto-discovered by Streamlit
│  ├─ 01_📊_Overview.py
│  ├─ 02_🧾_Data.py
│  └─ 03_⚙️_Settings.py
├─ dataforge/             # Python package for shared code
│  ├─ __init__.py
│  ├─ utils.py
│  ├─ db.py               # MotherDuck connection helper
│  └─ secrets.py          # Read/write .streamlit/secrets.toml
├─ .streamlit/config.toml # Theme and server settings
├─ pyproject.toml         # UV / project config
└─ README.md
```

## Notes

- Modify `.streamlit/config.toml` for theme/server tweaks.
- Add your datasets and business logic under `dataforge/` and import in pages.
- Use `uv pip install <pkg>` to add more dependencies and keep `pyproject.toml` as the single source of truth.

## MotherDuck Integration

- Configure MD Token and Database on the `⚙️ Settings` page.
- Values are saved to `.streamlit/secrets.toml` (ignored by git).
- Connection is verified from the Settings page via a test query.

Local development tip: you can also set `MOTHERDUCK_TOKEN` in your environment; the app will use the token provided on the Settings page if present.
