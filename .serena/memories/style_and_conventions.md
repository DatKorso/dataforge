# Style and Conventions

- PEP 8; 4‑space indents; max line length 100.
- Public functions use type hints; concise, focused docstrings.
- Naming: modules/functions `snake_case`, classes `PascalCase`, constants `UPPER_SNAKE_CASE`.
- Minimize globals; prefer `st.session_state` for UI/page state.
- Keep page modules self‑contained; import shared logic from `dataforge/`.
- Avoid side effects in `dataforge/` utilities.