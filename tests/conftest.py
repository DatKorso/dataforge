from __future__ import annotations

import sys
from pathlib import Path

# Make project importable without installing the package
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os
import toml
import pytest


@pytest.fixture(scope="session")
def md_token_md_database():
    """Return tuple (md_token, md_database) for tests.

    Prefers environment variables MOTHERDUCK_TOKEN / MD_DATABASE, falls back to
    .streamlit/secrets.toml if present.
    """
    md_token = os.environ.get("MOTHERDUCK_TOKEN")
    md_database = os.environ.get("MD_DATABASE")
    if md_token and md_database:
        return md_token, md_database
    try:
        s = toml.load(ROOT / ".streamlit" / "secrets.toml")
        return s.get("md_token"), s.get("md_database")
    except Exception:
        return md_token, md_database

