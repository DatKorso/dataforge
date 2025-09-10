from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import toml


SECRETS_PATH = Path(".streamlit/secrets.toml")


def load_secrets() -> Dict[str, Any]:
    """Load secrets from `.streamlit/secrets.toml`.

    Returns an empty dict if the file does not exist or is empty.
    """
    if not SECRETS_PATH.exists():
        return {}
    try:
        return toml.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    except Exception:
        # If parse fails, don't crash the UI; present empty.
        return {}


def save_secrets(update: Dict[str, Any]) -> None:
    """Merge and save secrets to `.streamlit/secrets.toml`.

    - Reads existing TOML (if present)
    - Updates with provided key/values
    - Writes the merged TOML back
    """
    current = load_secrets()
    current.update({k: v for k, v in update.items() if v is not None})

    SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SECRETS_PATH.write_text(toml.dumps(current), encoding="utf-8")

