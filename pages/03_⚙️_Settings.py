from __future__ import annotations

import streamlit as st
from dataforge.ui import setup_page

from dataforge.db import check_connection
from dataforge.secrets import load_secrets, save_secrets
from dataforge.schema import init_schema, rebuild_indexes


setup_page(title="DataForge", icon="🛠️")
st.title("⚙️ Settings")

# --- MotherDuck configuration ---
st.subheader("MotherDuck")
st.caption("Укажите MD токен и название базы данных.")

existing = load_secrets()

def _secret_from_streamlit(key: str) -> str | None:
    try:
        # st.secrets behaves like a dict; use indexing to avoid relying on .get
        return st.secrets[key]  # type: ignore[index]
    except Exception:
        return None

default_token = (
    st.session_state.get("md_token")
    or _secret_from_streamlit("md_token")
    or existing.get("md_token", "")
)
default_db = (
    st.session_state.get("md_database")
    or _secret_from_streamlit("md_database")
    or existing.get("md_database", "")
)

md_token = st.text_input("MD токен", value=default_token, type="password")
md_database = st.text_input("MD база данных", value=default_db, placeholder="my_database")

cols = st.columns(2)
with cols[0]:
    if st.button("Сохранить в secrets.toml"):
        save_secrets({"md_token": md_token, "md_database": md_database})
        st.session_state["md_token"] = md_token
        st.session_state["md_database"] = md_database
        st.success("Секреты сохранены в .streamlit/secrets.toml")

with cols[1]:
    if st.button("Проверить подключение"):
        with st.spinner("Проверка подключения к MotherDuck..."):
            ok, msg = check_connection(md_token=md_token or None, md_database=md_database or None)
        if ok:
            st.success(msg)
        else:
            st.error(msg)

st.divider()
st.subheader("Схема БД")
st.caption("Схема захардкожена в коде проекта для простоты сопровождения.")

cols2 = st.columns(2)
with cols2[0]:
    if st.button("Инициализировать схему БД"):
        with st.spinner("Создание таблиц (если отсутствуют)..."):
            msgs = init_schema(md_token=md_token or None, md_database=md_database or None)
        st.success("Выполнено:")
        for m in msgs:
            st.write(f"• {m}")

with cols2[1]:
    if st.button("Перестроить индексы"):
        with st.spinner("Перестройка индексов для всех известных таблиц..."):
            msgs = rebuild_indexes(md_token=md_token or None, md_database=md_database or None)
        st.success("Выполнено:")
        for m in msgs:
            st.write(f"• {m}")
