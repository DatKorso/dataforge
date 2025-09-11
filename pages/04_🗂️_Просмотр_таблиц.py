from __future__ import annotations

from typing import List, Optional, Tuple

import pandas as pd
import streamlit as st

from dataforge.ui import setup_page
from dataforge.db import get_connection
from dataforge.imports.loader import quote_ident


setup_page(title="DataForge", icon="🛠️")
st.title("🗂️ Просмотр таблиц БД")
st.caption("Выберите таблицу MotherDuck, выполните поиск и просматривайте данные постранично.")


def _sget(key: str) -> Optional[str]:
    try:
        return st.secrets[key]  # type: ignore[index]
    except Exception:
        return None


md_token = st.session_state.get("md_token") or _sget("md_token")
md_database = st.session_state.get("md_database") or _sget("md_database")

if not md_token:
    st.warning("MD токен не найден. Укажите его на странице Настройки.")


@st.cache_data(ttl=30)
def list_tables(md_token: Optional[str], md_database: Optional[str]) -> pd.DataFrame:
    with get_connection(md_token=md_token, md_database=md_database) as con:
        df = con.execute(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
              AND table_catalog = current_database()
              AND table_schema NOT IN ('information_schema')
            ORDER BY table_schema, table_name
            """
        ).fetch_df()
    return df


@st.cache_data(ttl=30)
def list_columns(
    schema: Optional[str], table: str, *, md_token: Optional[str], md_database: Optional[str]
) -> pd.DataFrame:
    with get_connection(md_token=md_token, md_database=md_database) as con:
        if schema:
            df = con.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = ? AND table_name = ?
                  AND table_catalog = current_database()
                ORDER BY ordinal_position
                """,
                [schema, table],
            ).fetch_df()
        else:
            df = con.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = ?
                  AND table_catalog = current_database()
                ORDER BY ordinal_position
                """,
                [table],
            ).fetch_df()
    return df


def qualified_name(schema: Optional[str], table: str) -> str:
    return f"{quote_ident(schema)}.{quote_ident(table)}" if schema else quote_ident(table)


def build_search_clause(cols: List[str]) -> Tuple[str, List[str]]:
    """Build an ILIKE search across provided columns.

    Returns (sql_fragment, params) where fragment like '(CAST(col AS VARCHAR) ILIKE ? OR ...)'.
    """
    if not cols:
        return "", []
    parts = [
        f"LOWER(CAST({quote_ident(c)} AS VARCHAR)) LIKE LOWER(?) ESCAPE '\\'" for c in cols
    ]
    frag = "(" + " OR ".join(parts) + ")"
    return frag, []


def escape_like(s: str) -> str:
    # Escape LIKE wildcards and backslash
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


try:
    tables_df = list_tables(md_token, md_database)
except Exception as exc:  # noqa: BLE001
    st.error(f"Не удалось получить список таблиц: {exc}")
    tables_df = pd.DataFrame(columns=["table_schema", "table_name"])

if tables_df.empty:
    st.info("В текущей базе данных таблиц не найдено.")
    st.stop()

tables_df["label"] = tables_df.apply(
    lambda r: f"{r['table_schema']}.{r['table_name']}" if pd.notna(r["table_schema"]) else str(r["table_name"]),
    axis=1,
)

choice = st.selectbox("Таблица", options=tables_df["label"].tolist())

sel = tables_df[tables_df["label"] == choice].iloc[0]
schema = sel["table_schema"] if pd.notna(sel["table_schema"]) else None
table = str(sel["table_name"])

# Controls
cols_ctrl = st.columns([2, 1, 1])
with cols_ctrl[0]:
    query_text = st.text_input("Поиск по всем колонкам", value=st.session_state.get("df_search", ""))
    st.session_state["df_search"] = query_text
with cols_ctrl[1]:
    per_page = st.selectbox("Строк на странице", options=[25, 50, 100, 200], index=1)
with cols_ctrl[2]:
    if "page_num" not in st.session_state:
        st.session_state["page_num"] = 1
    # Reset page on search change
    if st.session_state.get("_last_search", "") != query_text:
        st.session_state["page_num"] = 1
        st.session_state["_last_search"] = query_text

# Fetch columns for search
cols_df = list_columns(schema, table, md_token=md_token, md_database=md_database)
all_cols: List[str] = cols_df["column_name"].astype(str).tolist()

search = query_text.strip()
pattern = f"%{escape_like(search)}%" if search else None

where_sql = ""
params: List[str] = []
if search:
    where_frag, _ = build_search_clause(all_cols)
    where_sql = f"WHERE {where_frag}"
    params = [pattern] * len(all_cols)

qname = qualified_name(schema, table)

try:
    with get_connection(md_token=md_token, md_database=md_database) as con:
        # Total rows (filtered)
        cnt_sql = f"SELECT COUNT(*) AS n FROM {qname} {where_sql}"
        total_rows = int(con.execute(cnt_sql, params).fetchone()[0])

        # Pagination
        total_pages = max(1, (total_rows + per_page - 1) // per_page)
        st.session_state["page_num"] = max(1, min(st.session_state["page_num"], total_pages))

        nav1, nav2, nav3, nav4 = st.columns([1, 1, 2, 3])
        with nav1:
            if st.button("⟵ Предыдущая", disabled=st.session_state["page_num"] <= 1):
                st.session_state["page_num"] -= 1
        with nav2:
            if st.button("Следующая ⟶", disabled=st.session_state["page_num"] >= total_pages):
                st.session_state["page_num"] += 1
        with nav3:
            st.write(
                f"Страница {st.session_state['page_num']} из {total_pages} — записей: {total_rows}"
            )
        with nav4:
            st.caption("Поиск применяется ко всей таблице, а не только текущей странице")

        offset = (st.session_state["page_num"] - 1) * per_page
        data_sql = f"SELECT * FROM {qname} {where_sql} LIMIT ? OFFSET ?"
        df_page = con.execute(data_sql, params + [per_page, offset]).fetch_df()
except Exception as exc:  # noqa: BLE001
    st.exception(exc)
    st.stop()

st.dataframe(df_page, width="stretch", height=600)

csv = df_page.to_csv(index=False).encode("utf-8")
st.download_button(
    "Скачать эту страницу в CSV",
    data=csv,
    file_name=f"{table}_page_{st.session_state['page_num']}.csv",
    mime="text/csv",
)
