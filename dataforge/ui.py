from __future__ import annotations

import streamlit as st

"""UI helpers for Streamlit pages.

Expose a single setup function to enforce a consistent, wide layout
across all pages in the multipage app.
"""


def setup_page(
    *,
    title: str = "DataForge",
    icon: str = "🛠️",
    sidebar_state: str = "expanded",
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
