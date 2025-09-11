from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
import streamlit as st

from dataforge.ui import setup_page
from dataforge.imports.loader import load_dataframe
from dataforge.imports.assemblers import (
    assemble_ozon_products_full,
    assemble_wb_products,
    assemble_wb_prices,
)
from dataforge.imports.reader import read_any
from dataforge.imports.registry import ReportSpec, get_registry
from dataforge.imports.validator import ValidationResult, normalize_and_validate


setup_page(title="DataForge", icon="🛠️")
st.title("📥 Импорт файлов")
st.caption(
    "Загрузочный хаб для обновления таблиц БД. Добавляйте отчёты маркетплейсов и загружайте в MotherDuck."
)

REGISTRY = get_registry()
SPEC_OPTIONS = {spec.name: spec.id for spec in REGISTRY.values()}

report_name = st.selectbox("Тип отчёта", options=list(SPEC_OPTIONS.keys()))
report_id = SPEC_OPTIONS[report_name]
spec: ReportSpec = REGISTRY[report_id]

st.info(spec.description)

uploaded = st.file_uploader(
    "Загрузите файл(ы) отчёта",
    type=spec.allowed_extensions,
    accept_multiple_files=spec.multi_file,
    help=(
        "Поддерживаются .csv и .xlsx (Excel). Для полных товаров Ozon допустима загрузка нескольких файлов."
    ),
)


def _arrow_safe(df: pd.DataFrame) -> pd.DataFrame:
    """Sanitize a DataFrame to avoid Arrow serialization issues in Streamlit.

    - For object columns, convert bytes/bytearray to UTF-8 strings
    - Cast mixed-type object columns to strings, preserving NaN as None
    """
    if df is None or df.empty:
        return df
    out = df.copy()
    for c in out.columns:
        s = out[c]
        if s.dtype == object:
            def _to_str(x: Any) -> Any:
                if x is None or (isinstance(x, float) and pd.isna(x)):
                    return None
                if isinstance(x, (bytes, bytearray)):
                    try:
                        return x.decode("utf-8", errors="replace")
                    except Exception:
                        return str(x)
                if isinstance(x, str):
                    return x
                return str(x)

            out[c] = s.map(_to_str)
    return out

with st.expander("Параметры импорта", expanded=False):
    col1, col2, col3 = st.columns(3)
    with col1:
        delim_label = st.selectbox(
            "Разделитель (CSV)",
            options=["Авто", "Запятая ,", "Точка с запятой ;", "Табуляция \t"],
            index=0,
        )
    with col2:
        encoding = st.selectbox("Кодировка", options=["utf-8", "cp1251", "auto"], index=0)
    with col3:
        header_row = st.number_input("Строка заголовков", min_value=1, value=spec.header_row + 1)

    clear_table = st.checkbox(
        "Очищать таблицу перед загрузкой",
        value=True,
        help="Рекомендуется для отчётов, которые представляют полное состояние (например, список товаров)",
    )

def _ext_from_name(name: str) -> str:
    return Path(name).suffix.lstrip(".").lower()


def _delimiter_value(label: str) -> Optional[str]:
    if label.startswith("Авто"):
        return None
    if "," in label:
        return ","
    if ";" in label:
        return ";"
    if "\t" in label:
        return "\t"
    return None


MAX_SIZE = 200 * 1024 * 1024  # 200MB

preview_col, import_col = st.columns([1, 1])

has_files = False
if spec.multi_file:
    has_files = isinstance(uploaded, list) and len(uploaded) > 0
else:
    has_files = uploaded is not None

if has_files:
    size = getattr(uploaded, "size", None)
    if spec.multi_file:
        total_size = sum(getattr(f, "size", 0) or 0 for f in uploaded)
        if total_size > MAX_SIZE:
            st.error("Суммарный размер файлов слишком большой. Максимум 200MB.")
        else:
            st.write(f"Выбрано файлов: {len(uploaded)}; суммарно {total_size} байт")
    else:
        if size and size > MAX_SIZE:
            st.error("Файл слишком большой. Максимальный размер 200MB.")
        else:
            st.write(f"Файл: {uploaded.name} — {size or 0} байт")

    with preview_col:
        if st.button("Предпросмотр и валидация", type="primary"):
            try:
                if spec.assembler:
                    with st.spinner("Сбор данных из файла(ов)..."):
                        if spec.assembler == "ozon_products_full":
                            df_src = assemble_ozon_products_full(uploaded)
                        elif spec.assembler == "wb_products":
                            df_src = assemble_wb_products(uploaded)
                        elif spec.assembler == "wb_prices":
                            files = uploaded if isinstance(uploaded, list) else [uploaded]
                            df_src = assemble_wb_prices(files)
                        else:
                            raise ValueError(f"Неизвестный сборщик для отчёта: {spec.assembler}")
                else:
                    ext = _ext_from_name(uploaded.name)
                    delimiter = _delimiter_value(delim_label)
                    enc = None if encoding == "auto" else encoding
                    with st.spinner("Чтение файла..."):
                        df_src = read_any(
                            uploaded, ext, delimiter=delimiter, encoding=enc, header_row=int(header_row) - 1
                        )

                st.session_state["last_src_preview"] = df_src.head(5)
                st.dataframe(_arrow_safe(df_src.head(10)), width="stretch")

                with st.spinner("Нормализация и валидация..."):
                    vr: ValidationResult = normalize_and_validate(df_src, spec)

                st.session_state["norm_df"] = vr.df_normalized
                st.session_state["norm_errors"] = vr.errors

                st.subheader("Сводка")
                m1, m2, m3 = st.columns(3)
                m1.metric("Всего строк", vr.rows_total)
                m2.metric("Валидных строк", vr.rows_valid)
                m3.metric("Ошибок", len(vr.errors))

                if vr.errors:
                    st.warning("Обнаружены ошибки. Строки с ошибками будут пропущены при импорте.")
                    st.dataframe(_arrow_safe(pd.DataFrame(vr.errors)), width="stretch")

                st.subheader("Нормализованные данные (превью)")
                st.dataframe(_arrow_safe(vr.df_normalized.head(20)), width="stretch")

                csv_buf = io.StringIO()
                vr.df_normalized.to_csv(csv_buf, index=False)
                st.download_button(
                    "Скачать нормализованный CSV",
                    data=csv_buf.getvalue().encode("utf-8"),
                    file_name=f"{spec.table}_normalized.csv",
                    mime="text/csv",
                )
            except Exception as exc:  # noqa: BLE001
                st.exception(exc)

    with import_col:
        if st.button("Импортировать в БД", disabled="norm_df" not in st.session_state):
            try:
                df_ready: pd.DataFrame = st.session_state.get("norm_df", pd.DataFrame())
                if df_ready.empty:
                    st.error("Нет валидных данных для импорта. Сначала выполните предпросмотр.")
                else:
                    def _sget(key: str) -> Optional[str]:
                        try:
                            return st.secrets[key]  # type: ignore[index]
                        except Exception:
                            return None

                    md_token = st.session_state.get("md_token") or _sget("md_token")
                    md_database = st.session_state.get("md_database") or _sget("md_database")
                    if not md_token:
                        st.warning("MD токен не найден. Укажите его на странице Настройки.")

                    with st.spinner("Загрузка в MotherDuck..."):
                        msg = load_dataframe(
                            df_ready,
                            table=spec.table,
                            md_token=md_token,
                            md_database=md_database,
                            replace=clear_table,
                        )
                    st.success(msg)
            except Exception as exc:  # noqa: BLE001
                st.exception(exc)

else:
    st.info("Загрузите файл для начала работы.")
