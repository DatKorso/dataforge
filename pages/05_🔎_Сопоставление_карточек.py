from __future__ import annotations

import io
from dataclasses import dataclass, field

import pandas as pd
import streamlit as st
from dataforge.matching import search_matches
from dataforge.ui import setup_page

setup_page(title="DataForge", icon="🛠️")

DEFECT_PREFIX = "БракSH"

@dataclass
class MatchConfig:
    """Configuration for marketplace matching search."""

    md_token: str | None = None
    md_database: str | None = None
    filter_no_defect: bool = True
    filter_unique_sizes: bool = True
    limit_per_input: int = 0
    selected_cols: list[str] = field(default_factory=lambda: DEFAULT_COLUMNS.copy())


def get_config() -> MatchConfig:
    """Load configuration from session state and secrets."""
    return MatchConfig(
        md_token=st.session_state.get("md_token") or _sget("md_token"),
        md_database=st.session_state.get("md_database") or _sget("md_database"),
        filter_no_defect=st.session_state.get("mp_filter_no_defect", True),
        filter_unique_sizes=st.session_state.get("mp_filter_unique_sizes", True),
        limit_per_input=int(st.session_state.get("limit_per_input", 0)),
        selected_cols=st.session_state.get("mp_selected_cols", DEFAULT_COLUMNS.copy()),
    )
st.title("🔎 Поиск соответствий карточек (Ozon ↔ WB)")
st.caption(
    "Найдите общие карточки между маркетплейсами по штрихкодам. Поддерживается массовый ввод."
)


def _sget(key: str) -> str | None:
    try:
        return st.secrets[key]  # type: ignore[index]
    except Exception:
        return None


md_token = st.session_state.get("md_token") or _sget("md_token")
md_database = st.session_state.get("md_database") or _sget("md_database")

if "mp_filter_no_defect" not in st.session_state:
    st.session_state["mp_filter_no_defect"] = True

if "mp_filter_unique_sizes" not in st.session_state:
    st.session_state["mp_filter_unique_sizes"] = True

if not md_token:
    st.warning("MD токен не найден. Укажите его на странице Настройки.")


def parse_input(text: str) -> list[str]:
    # Разбиваем по любым пробелам и переводам строки; фильтруем пустые
    tokens = [t.strip() for t in text.replace(",", " ").split()]  # запятые тоже считаем разделителем
    return [t for t in tokens if t]


def _dedupe_sizes(df: pd.DataFrame, input_type: str) -> pd.DataFrame:
    """Remove duplicate sizes keeping the highest match_score per size group.

    Rules:
    - If input_type is 'wb_sku': keep unique wb_size within each wb_sku
    - If input_type is 'oz_sku' or 'oz_vendor_code': keep unique oz_manufacturer_size within each oz_sku
    - Otherwise (e.g., barcode), leave as is
    """
    if df.empty:
        return df

    if input_type == "wb_sku":
        size_col = "wb_size"
        group_cols = ["wb_sku", size_col]
    elif input_type in ("oz_sku", "oz_vendor_code"):
        size_col = "oz_manufacturer_size"
        group_cols = ["oz_sku", size_col]
    else:
        return df

    if "match_score" not in df.columns or any(col not in df.columns for col in group_cols):
        return df

    # Work only with rows where size is non-empty/non-null; keep others intact
    mask_known_size = df[size_col].notna() & (df[size_col].astype(str).str.strip() != "")
    df_known = df.loc[mask_known_size].copy()
    df_unknown = df.loc[~mask_known_size].copy()

    if df_known.empty:
        return df

    # Sort to keep the highest score first; tie-breakers stay stable
    df_known = df_known.sort_values(["match_score"], ascending=[False])
    df_known = df_known.drop_duplicates(subset=group_cols, keep="first")

    # Preserve original order as much as possible: place known first by score, then unknown
    return pd.concat([df_known, df_unknown], axis=0, ignore_index=True)


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
    "input_external_code",
    "matched_by",
    "match_score",
    # Punta
    "punta_external_code_oz",
    "punta_collection_oz",
    "punta_external_code_wb",
    "punta_collection_wb",
    "punta_external_equal",
]

ALL_COLUMNS = [
    # OZ
    "oz_sku",
    "oz_vendor_code",
    "oz_product_name",
    "oz_manufacturer_size",
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
    "input_external_code",
    "matched_by",
    "match_score",
    # Punta (optional enrichment)
    "punta_external_code_oz",
    "punta_collection_oz",
    "punta_external_code_wb",
    "punta_collection_wb",
    "punta_external_equal",
]


with st.form(key="mp_match_form"):
    col1, col2 = st.columns([1, 1])
    with col1:
        # Используем ключ для надёжной синхронизации состояния формы
        mp_input_option = st.selectbox(
            "Тип входных данных",
            options=[
                ("Артикул Ozon (oz_sku)", "oz_sku"),
                ("Артикул WB (wb_sku)", "wb_sku"),
                ("Штрихкод", "barcode"),
                ("Артикул поставщика Ozon (oz_vendor_code)", "oz_vendor_code"),
                ("Punta external code (external_code)", "punta_external_code"),
            ],
            format_func=lambda x: x[0],
            key="mp_input_option",
        )

    with col2:
        st.number_input(
            "Лимит кандидатов (0 — без лимита)",
            min_value=0,
            max_value=10000,
            value=int(st.session_state.get("limit_per_input", 0)),
            key="limit_per_input",
        )

    st.text_area(
        "Значения для поиска",
        value=st.session_state.get("mp_input_text", ""),
        height=140,
        help=(
            "Вставьте список значений через пробел или с новой строки. "
            "Поддерживаются 10–300+ значений."
        ),
        key="mp_input_text",
    )

    st.checkbox(
        "Без брака Озон",
        key="mp_filter_no_defect",
        help="Исключить артикулы Ozon, начинающиеся на «БракSH».",
    )

    st.checkbox(
        "Без дублей размеров",
        key="mp_filter_unique_sizes",
        help=(
            "Оставлять по одному значению размера с наивысшим match_score "
            "в пределах выбранного идентификатора (wb_sku или oz_sku)."
        ),
    )

    st.multiselect(
        "Поля для вывода",
        options=ALL_COLUMNS,
        default=st.session_state.get("mp_selected_cols", DEFAULT_COLUMNS),
        help="Можно менять набор колонок без повторного поиска.",
        key="mp_selected_cols",
    )

    submitted = st.form_submit_button("Найти", type="primary")

if submitted:
    # Читаем значения из session_state после submit — иначе берётся предыдущее состояние
    input_type = st.session_state.get("mp_input_option", (None, ""))[1]
    text_value = st.session_state.get("mp_input_text", "")
    limit_per_input = int(st.session_state.get("limit_per_input", 0))

    values = parse_input(text_value)
    if not values:
        st.warning("Введите хотя бы одно значение для поиска.")
        st.stop()

    if len(values) > 300:
        st.info(
            f"Передано {len(values)} значений. Это может занять время, дождитесь завершения."
        )

    if not md_token:
        st.error("MD токен отсутствует. Укажите его на странице Настройки.")
        st.stop()

    try:
        with st.spinner("Поиск соответствий..."):
            df_res = search_matches(
                values,
                input_type=input_type,
                limit_per_input=(None if int(limit_per_input) <= 0 else int(limit_per_input)),
                md_token=md_token,
                md_database=md_database,
            )
        # Apply filters immediately
        filter_no_defect = st.session_state.get("mp_filter_no_defect", True)
        if filter_no_defect and "oz_vendor_code" in df_res.columns:
            starts_with_brak = (
                df_res["oz_vendor_code"].fillna("").astype(str).str.startswith(DEFECT_PREFIX)
            )
            df_res = df_res.loc[~starts_with_brak]

        # Apply deduplication before storing
        if st.session_state.get("mp_filter_unique_sizes", True):
            df_res = _dedupe_sizes(df_res, input_type=input_type)

        st.session_state["mp_match_result"] = df_res
        st.session_state["mp_input_type"] = input_type
    except ValueError as exc:
        st.error(f"❌ Ошибка валидации данных: {exc}")
    except (ConnectionError, TimeoutError) as exc:
        st.error(f"🔌 Ошибка подключения к базе данных: {exc}")
    except Exception as exc:
        st.error("⚠️ Неожиданная ошибка при поиске соответствий:")
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
