from __future__ import annotations

import io
from typing import List, Optional

import pandas as pd
import streamlit as st

from dataforge.ui import setup_page
from dataforge.matching import search_matches


setup_page(title="DataForge", icon="🛠️")
st.title("🔎 Поиск соответствий карточек (Ozon ↔ WB)")
st.caption(
    "Найдите общие карточки между маркетплейсами по штрихкодам. Поддерживается массовый ввод."
)


def _sget(key: str) -> Optional[str]:
    try:
        return st.secrets[key]  # type: ignore[index]
    except Exception:
        return None


md_token = st.session_state.get("md_token") or _sget("md_token")
md_database = st.session_state.get("md_database") or _sget("md_database")

if not md_token:
    st.warning("MD токен не найден. Укажите его на странице Настройки.")


def parse_input(text: str) -> List[str]:
    # Разбиваем по любым пробелам и переводам строки; фильтруем пустые
    tokens = [t.strip() for t in text.replace(",", " ").split()]  # запятые тоже считаем разделителем
    return [t for t in tokens if t]


DEFAULT_COLUMNS = [
    "oz_sku",
    "oz_vendor_code",
    "oz_primary_barcode",
    "wb_sku",
    "wb_primary_barcode",
    "wb_size",
    "oz_is_primary_hit",
    "wb_is_primary_hit",
    "barcode_hit",
    "matched_by",
    "match_score",
]

ALL_COLUMNS = [
    # OZ
    "oz_sku",
    "oz_vendor_code",
    "oz_product_name",
    "oz_russian_size",
    "oz_brand",
    "oz_color",
    "oz_primary_barcode",
    # WB
    "wb_sku",
    "wb_article",
    "wb_brand",
    "wb_color",
    "wb_size",
    "wb_primary_barcode",
    # Match
    "oz_is_primary_hit",
    "wb_is_primary_hit",
    "barcode_hit",
    "matched_by",
    "match_score",
]


with st.form(key="mp_match_form"):
    col1, col2 = st.columns([1, 1])
    with col1:
        input_type = st.selectbox(
            "Тип входных данных",
            options=[
                ("Артикул Ozon (oz_sku)", "oz_sku"),
                ("Артикул WB (wb_sku)", "wb_sku"),
                ("Штрихкод", "barcode"),
                ("Артикул поставщика Ozon (oz_vendor_code)", "oz_vendor_code"),
            ],
            format_func=lambda x: x[0],
        )[1]

    with col2:
        limit_per_input = st.number_input(
            "Лимит кандидатов (0 — без лимита)",
            min_value=0,
            max_value=10000,
            value=int(st.session_state.get("limit_per_input", 0)),
        )

    text_value = st.text_area(
        "Значения для поиска",
        value=st.session_state.get("mp_input_text", ""),
        height=140,
        help=(
            "Вставьте список значений через пробел или с новой строки. "
            "Поддерживаются 10–300+ значений."
        ),
    )

    selected_cols = st.multiselect(
        "Поля для вывода",
        options=ALL_COLUMNS,
        default=st.session_state.get("mp_selected_cols", DEFAULT_COLUMNS),
        help="Можно менять набор колонок без повторного поиска.",
    )

    submitted = st.form_submit_button("Найти", type="primary")

    # Сохраняем состояние инпутов
    st.session_state["mp_input_text"] = text_value
    st.session_state["mp_selected_cols"] = selected_cols
    st.session_state["limit_per_input"] = int(limit_per_input)

if submitted:
    values = parse_input(text_value)
    if not values:
        st.warning("Введите хотя бы одно значение для поиска.")
        st.stop()

    if len(values) > 300:
        st.info(
            f"Передано {len(values)} значений. Это может занять время, дождитесь завершения."
        )

    try:
        with st.spinner("Поиск соответствий..."):
            df_res = search_matches(
                values,
                input_type=input_type,
                limit_per_input=(None if int(limit_per_input) <= 0 else int(limit_per_input)),
                md_token=md_token,
                md_database=md_database,
            )
        st.session_state["mp_match_result"] = df_res
    except Exception as exc:  # noqa: BLE001
        st.exception(exc)


df_show: pd.DataFrame = st.session_state.get("mp_match_result", pd.DataFrame())

if df_show.empty:
    st.info("Результаты будут показаны здесь после нажатия кнопки ‘Найти’.")
    st.stop()

# Применяем выбранные пользователем колонки (если отсутствуют, игнорируем)
cols_to_show = [c for c in st.session_state.get("mp_selected_cols", DEFAULT_COLUMNS) if c in df_show.columns]
if not cols_to_show:
    cols_to_show = [c for c in DEFAULT_COLUMNS if c in df_show.columns]

st.subheader("Результаты")
m1, m2 = st.columns(2)
with m1:
    st.metric("Всего строк", len(df_show))
with m2:
    st.metric("Уникальных штрихкодов", df_show["barcode_hit"].nunique() if "barcode_hit" in df_show else 0)

st.dataframe(df_show[cols_to_show], width="stretch", height=600)

csv_buf = io.StringIO()
df_show[cols_to_show].to_csv(csv_buf, index=False)
st.download_button(
    "Скачать CSV",
    data=csv_buf.getvalue().encode("utf-8"),
    file_name="mp_matches.csv",
    mime="text/csv",
)
