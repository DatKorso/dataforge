from __future__ import annotations

import io
from dataclasses import dataclass, field

import pandas as pd
import streamlit as st
from dataforge.matching import search_matches
from dataforge.matching_helpers import add_merge_fields
from dataforge.ui import setup_page

setup_page(title="DataForge — Склейка OZ", icon="🧩")

DEFECT_PREFIX = "БракSH"


@dataclass
class MergeConfig:
    md_token: str | None = None
    md_database: str | None = None
    filter_no_defect: bool = True
    filter_unique_sizes: bool = True
    limit_per_input: int = 0
    selected_cols: list[str] = field(default_factory=lambda: [
        "wb_sku",
        "oz_sku",
        "oz_vendor_code",
        "merge_code",
        "merge_color",
    ])


def parse_input(text: str) -> list[str]:
    tokens = [t.strip() for t in text.replace(",", " ").split()]
    return [t for t in tokens if t]


st.title("🧩 Склейка карточек OZ")
st.caption("Связываем карточки OZ между собой по выбранному алгоритму (базовый: общий wb_sku).")


md_token = st.session_state.get("md_token") or st.secrets.get("md_token") if hasattr(st, "secrets") else None
md_database = st.session_state.get("md_database") or st.secrets.get("md_database") if hasattr(st, "secrets") else None

if not md_token:
    st.warning("MD токен не найден. Укажите его на странице Настройки.")


with st.form(key="oz_merge_form"):
    col1, col2 = st.columns([1, 1])
    with col1:
        merge_algo = st.selectbox(
            "Алгоритм объединения",
            options=[("Объединить по общему WB артикулу", "wb_by_sku")],
            format_func=lambda x: x[0] if isinstance(x, tuple) else x,
            key="oz_merge_algo",
        )

    with col2:
        st.number_input(
            "Лимит кандидатов (0 — без лимита)",
            min_value=0,
            max_value=10000,
            value=int(st.session_state.get("oz_merge_limit", 0)),
            key="oz_merge_limit",
        )

    st.text_area(
        "Список WB SKU",
        value=st.session_state.get("oz_merge_input_text", ""),
        height=140,
        help="Вставьте список wb_sku через пробел или новую строку.",
        key="oz_merge_input_text",
    )

    st.checkbox("Без брака Озон", key="oz_merge_filter_no_defect", help="Исключить oz_vendor_code начинающиеся на БракSH")
    st.checkbox("Без дублей размеров", key="oz_merge_filter_unique_sizes", help="Оставлять по одному значению размера с наивысшим match_score")

    submitted = st.form_submit_button("Склеить", type="primary")

if submitted:
    if not md_token:
        st.error("MD токен отсутствует. Укажите его на странице Настройки.")
        st.stop()

    text_value = st.session_state.get("oz_merge_input_text", "")
    values = parse_input(text_value)
    if not values:
        st.warning("Введите хотя бы один WB SKU.")
        st.stop()

    if len(values) > 500:
        st.info("Передано много значений; операция может занять время.")

    try:
        with st.spinner("Поиск OZ карточек по WB SKU..."):
            df = search_matches(
                values,
                input_type="wb_sku",
                limit_per_input=(None if int(st.session_state.get("oz_merge_limit", 0)) <= 0 else int(st.session_state.get("oz_merge_limit", 0))),
                md_token=md_token,
                md_database=md_database,
            )

        # Apply defect filter
        if st.session_state.get("oz_merge_filter_no_defect", True) and "oz_vendor_code" in df.columns:
            starts_with_brak = df["oz_vendor_code"].fillna("").astype(str).str.startswith(DEFECT_PREFIX)
            df = df.loc[~starts_with_brak]

        # Deduplicate sizes similar to existing page
        if st.session_state.get("oz_merge_filter_unique_sizes", True):
            from dataforge.matching_helpers import dedupe_sizes

            df = dedupe_sizes(df, input_type="wb_sku")

        # Add merge fields
        df = add_merge_fields(df, wb_sku_col="wb_sku", oz_vendor_col="oz_vendor_code")

        st.session_state["oz_merge_result"] = df
        # collect invalid oz_vendor_code rows for highlighting
        if "oz_vendor_code" in df.columns:
            invalid_mask = ~df["oz_vendor_code"].astype(str).str.contains("-", regex=False)
            st.session_state["oz_merge_invalid_oz_vendor"] = df.loc[invalid_mask]
        else:
            st.session_state["oz_merge_invalid_oz_vendor"] = pd.DataFrame()
    except Exception as exc:
        st.error("Ошибка при поиске/обработке: ")
        st.exception(exc)

df_show: pd.DataFrame = st.session_state.get("oz_merge_result", pd.DataFrame())

if df_show.empty:
    st.info("Результаты будут показаны здесь после нажатия 'Склеить'.")
    st.stop()

cols_default = [
    "wb_sku",
    "oz_sku",
    "oz_vendor_code",
    "merge_code",
    "merge_color",
    "match_score",
]

cols_to_show = [c for c in st.session_state.get("oz_merge_selected_cols", cols_default) if c in df_show.columns]
if not cols_to_show:
    cols_to_show = [c for c in cols_default if c in df_show.columns]

st.subheader("Результаты склейки OZ")
st.dataframe(df_show[cols_to_show], width="stretch", height=600)

csv_buf = io.StringIO()
df_show[cols_to_show].to_csv(csv_buf, index=False)
st.download_button(
    "Скачать CSV",
    data=csv_buf.getvalue().encode("utf-8"),
    file_name="oz_merge.csv",
    mime="text/csv",
)
