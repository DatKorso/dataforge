# Security and Configuration

- Never commit secrets; use environment variables or `.streamlit/secrets.toml`.
- Validate and limit file uploads (size, type). Never execute user‑provided content.
- Centralize parsing/validation in `dataforge/` to reduce risk.
- Theme/server settings: `.streamlit/config.toml`.
- Secrets and credentials live in `.streamlit/secrets.toml` (local/dev).