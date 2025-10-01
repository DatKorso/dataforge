from __future__ import annotations

import io
from dataclasses import dataclass, field

import pandas as pd
import streamlit as st
from dataforge.matching import search_matches
from dataforge.matching_helpers import add_merge_fields
from dataforge.ui import setup_page
import math

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
            value=int(st.session_state.get("oz_merge_limit", 20)),
            key="oz_merge_limit",
        )

    st.text_area(
        "Список WB SKU",
        value=st.session_state.get("oz_merge_input_text", ""),
        height=140,
        help="Вставьте список wb_sku через пробел или новую строку.",
        key="oz_merge_input_text",
    )

    st.checkbox("Без брака Озон", key="oz_merge_filter_no_defect", value=True, help="Исключить oz_vendor_code начинающиеся на БракSH")
    st.checkbox("Без дублей размеров", key="oz_merge_filter_unique_sizes", value=True, help="Оставлять по одному значению размера с наивысшим match_score")
    st.write("---")
    st.markdown("**Параметры пакетной обработки (chunking)**")
    # calibrated defaults from autotune
    st.number_input("Размер батча (batch_size)", min_value=1, max_value=5000, value=int(st.session_state.get("oz_merge_batch_size", 1000)), key="oz_merge_batch_size")
    st.write(f"Лимит кандидатов на вход (limit_per_input): {int(st.session_state.get('oz_merge_limit', 20))}")
    st.info("Batch processing будет выполнять поиск партиями и обновлять результаты по мере получения данных.")

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
        # Batch processing with progress
        batch_size = int(st.session_state.get("oz_merge_batch_size", 1000))
        limit_per_input = int(st.session_state.get("oz_merge_limit", 20))
        total = len(values)
        n_chunks = math.ceil(total / batch_size)

        st.session_state["oz_merge_result"] = pd.DataFrame()
        progress = st.progress(0)
        fetched = 0

        for idx in range(n_chunks):
            start = idx * batch_size
            end = min(start + batch_size, total)
            chunk = values[start:end]
            with st.spinner(f"Запрос партии {idx+1}/{n_chunks} ({start+1}-{end})..."):
                df_chunk = search_matches(
                    chunk,
                    input_type="wb_sku",
                    limit_per_input=(None if limit_per_input <= 0 else limit_per_input),
                    md_token=md_token,
                    md_database=md_database,
                )

            if df_chunk is None or df_chunk.empty:
                df_chunk = pd.DataFrame()

            # Apply defect filter per-chunk to reduce memory
            if st.session_state.get("oz_merge_filter_no_defect", True) and "oz_vendor_code" in df_chunk.columns:
                starts_with_brak = df_chunk["oz_vendor_code"].fillna("").astype(str).str.startswith(DEFECT_PREFIX)
                df_chunk = df_chunk.loc[~starts_with_brak]

            # Add merge fields to the chunk
            if not df_chunk.empty and "oz_vendor_code" in df_chunk.columns:
                df_chunk = add_merge_fields(df_chunk, wb_sku_col="wb_sku", oz_vendor_col="oz_vendor_code")

            # accumulate safely
            df_result = st.session_state.get("oz_merge_result")
            if df_result is None or (hasattr(df_result, "empty") and df_result.empty):
                st.session_state["oz_merge_result"] = df_chunk.copy()
            else:
                st.session_state["oz_merge_result"] = pd.concat([df_result, df_chunk], ignore_index=True, copy=False)

            fetched += len(chunk)
            # Update progress
            progress.progress(int((end / total) * 100))

        # Final dedupe sizes similar to existing page
        if st.session_state.get("oz_merge_filter_unique_sizes", True) and not st.session_state["oz_merge_result"].empty:
            from dataforge.matching_helpers import dedupe_sizes

            st.session_state["oz_merge_result"] = dedupe_sizes(st.session_state["oz_merge_result"], input_type="wb_sku")

        # Ensure merge fields present (in case dedupe removed them)
        if not st.session_state["oz_merge_result"].empty:
            st.session_state["oz_merge_result"] = add_merge_fields(st.session_state["oz_merge_result"], wb_sku_col="wb_sku", oz_vendor_col="oz_vendor_code")

        # collect invalid oz_vendor_code rows for highlighting
        df = st.session_state["oz_merge_result"]
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
