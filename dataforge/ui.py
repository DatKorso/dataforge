from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any, Literal

import streamlit as st

"""UI helpers for Streamlit pages.

Expose a single setup function to enforce a consistent, wide layout
across all pages in the multipage app, plus lightweight feature flag helpers
to enable/disable access to specific pages in different environments.
"""


def setup_page(
    *,
    title: str = "DataForge",
    icon: str = "🛠️",
    sidebar_state: Literal["expanded", "collapsed", "auto"] = "expanded",
) -> None:
    """Configure the page with a shared, wide layout.

    This should be the first Streamlit call in each page module
    to ensure consistent container width regardless of navigation.

    Parameters
    - title: Заголовок страницы/приложения
    - icon: Иконка страницы (эмодзи/символ)
    - sidebar_state: Состояние сайдбара ("expanded" или "collapsed")
    """

    st.set_page_config(
        page_title=title,
        page_icon=icon,
        layout="wide",
        initial_sidebar_state=sidebar_state,
    )


def _get_secret(key: str, default: Any = None) -> Any:
    """Safely read a secret from Streamlit, returning default if missing."""
    try:
        return st.secrets[key]  # type: ignore[index]
    except Exception:
        return default


def _to_bool(val: Any, *, default: bool = False) -> bool:
    if isinstance(val, bool):
        return val
    if val is None:
        return default
    try:
        s = str(val).strip().lower()
    except Exception:
        return default
    return s in {"1", "true", "yes", "y", "on"}


def feature_enabled(flag: str, *, default: bool = True) -> bool:
    """Check whether a feature flag is enabled.

    Precedence:
    1) secrets.toml -> [features].[flag]
    2) environment variable FEATURE_<FLAG> ("1", "true", "yes" -> True)
    3) provided default
    """
    # 1) secrets
    features = _get_secret("features", {})
    if isinstance(features, Mapping) and flag in features:
        try:
            return _to_bool(features[flag], default=default)
        except Exception:
            return default

    # 2) environment
    env_key = f"FEATURE_{flag.upper()}"
    env_val = os.getenv(env_key)
    if env_val is not None:
        return _to_bool(env_val, default=default)

    # 3) default
    return default


def guard_page(flag: str, *, default: bool = True, message: str | None = None) -> None:
    """Block page access if a feature flag is disabled.

    Parameters
    - flag: имя флага в секции [features] secrets.toml (напр., "enable_imports")
    - default: значение по умолчанию при отсутствии флага
    - message: текст сообщения при блокировке
    """
    if not feature_enabled(flag, default=default):
        st.error(message or "Эта страница отключена в текущем окружении.")
        st.stop()
