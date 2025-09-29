#!/usr/bin/env bash
set -euo pipefail

# Change to repository root
cd "$(dirname "$0")/.."

# Ensure unbuffered output for logs
export PYTHONUNBUFFERED=1

# Run Streamlit via UV using project config (.streamlit/config.toml)
exec uv run streamlit run app.py --server.port 40287 --server.address 0.0.0.0
