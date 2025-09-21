from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from dataforge.db import get_connection
from dataforge.imports.assemblers import (
    assemble_ozon_products_full,
    assemble_wb_prices,
    assemble_wb_products,
)
from dataforge.imports.google_sheets import (
    check_access as gs_check_access,
)
from dataforge.imports.google_sheets import (
    dedup_by_wb_sku_first as gs_dedup,
)
from dataforge.imports.google_sheets import (
    read_csv_first_sheet as gs_read_csv,
)
from dataforge.imports.loader import load_dataframe, load_dataframe_partitioned
from dataforge.imports.reader import read_any
from dataforge.imports.registry import ReportSpec, get_registry
from dataforge.imports.validator import ValidationResult, normalize_and_validate
from dataforge.secrets import save_secrets
from dataforge.ui import setup_page
from dataforge.utils import filter_df_by_brands, parse_brand_list

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

# Define _arrow_safe early so it can be used in all branches
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


def _select_barcode(raw: Any, prefer_last: bool = False) -> str | None:
    """Pick first/last non-empty barcode from JSON text or iterable."""
    if raw in (None, ""):
        return None

    if isinstance(raw, (list, tuple)):
        candidates = list(raw)
    else:
        candidates: list[Any]
        parsed: Any = None
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                parsed = None
        if isinstance(parsed, list):
            candidates = parsed
        elif parsed not in (None, ""):
            candidates = [parsed]
        elif isinstance(raw, str):
            candidates = [part.strip() for part in raw.split(";")]
        else:
            return None

    cleaned = [str(item).strip() for item in candidates if str(item).strip()]
    if not cleaned:
        return None
    return cleaned[-1] if prefer_last else cleaned[0]


# Дополнительные параметры для отдельных отчётов
punta_collection: str | None = None
if report_id == "punta_barcodes":
    punta_collection = st.text_input(
        "Коллекция",
        value=st.session_state.get("punta_collection", ""),
        help="Укажите название коллекции. Перед загрузкой данные этой коллекции будут очищены.",
    )
    st.session_state["punta_collection"] = punta_collection

uploaded = None
gs_url: str | None = None
if report_id != "punta_google":
    uploaded = st.file_uploader(
        "Загрузите файл(ы) отчёта",
        type=spec.allowed_extensions,
        accept_multiple_files=spec.multi_file,
        help=(
            "Поддерживаются .csv и .xlsx (Excel). Для полных товаров Ozon допустима загрузка нескольких файлов."
        ),
    )
else:
    # Один источник Google Sheets — ссылка сохраняется в secrets.toml
    def _sget_secret(key: str) -> str | None:
        try:
            return st.secrets[key]  # type: ignore[index]
        except Exception:
            return None

    gs_url = st.text_input(
        "Ссылка на Google Sheets",
        value=st.session_state.get("punta_google_url") or _sget_secret("punta_google_url") or "",
        placeholder="https://docs.google.com/spreadsheets/d/.../edit?usp=sharing",
        help="Вставьте публичную ссылку на документ. Используется первый лист. 2-я строка будет пропущена.",
    )
    st.session_state["punta_google_url"] = gs_url
    cols_gs = st.columns(3)
    with cols_gs[0]:
        if st.button("Сохранить ссылку"):
            save_secrets({"punta_google_url": gs_url})
            st.success("Ссылка сохранена в .streamlit/secrets.toml")
    with cols_gs[1]:
        if st.button("Проверить доступ"):
            with st.spinner("Проверка доступа к документу..."):
                ok, msg, df_prev = gs_check_access(gs_url)
            if ok:
                st.success(msg)
                if df_prev is not None and not df_prev.empty:
                    st.caption("Превью первых 10 строк")
                    st.dataframe(_arrow_safe(df_prev.head(10)), width="stretch")
            else:
                st.error(msg)
    with cols_gs[2]:
        st.caption("Импорт полностью заменит содержимое таблицы punta_google")


with st.expander("Параметры импорта", expanded=False):
    if report_id != "punta_google":
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
        if report_id == "punta_barcodes":
            st.caption("Для Punta очистка применяется только к выбранной коллекции.")
    else:
        st.caption("Для Punta Google данные читаются из Google Sheets; 2-я строка пропускается; импорт всегда заменяет таблицу.")
        # Placeholders to avoid UnboundLocalError below for non-GS branches
        delim_label = "Авто"
        encoding = "utf-8"
        header_row = spec.header_row + 1
        clear_table = True

def _ext_from_name(name: str) -> str:
    return Path(name).suffix.lstrip(".").lower()


def _delimiter_value(label: str) -> str | None:
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

has_input = False
if report_id == "punta_google":
    has_input = bool(gs_url)
else:
    if spec.multi_file:
        has_input = isinstance(uploaded, list) and len(uploaded) > 0
    else:
        has_input = uploaded is not None

if has_input and report_id != "punta_google":
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

                # Подстановка значения коллекции для отчёта Punta
                if report_id == "punta_barcodes":
                    if not punta_collection:
                        st.warning("Укажите значение поля 'Коллекция' перед предпросмотром.")
                        st.stop()
                    df_src = df_src.copy()
                    # Всегда подставляем единое значение; игнорируем содержимое файла при наличии колонки
                    df_src["Коллекция"] = punta_collection

                st.session_state["last_src_preview"] = df_src.head(5)
                st.dataframe(_arrow_safe(df_src.head(10)), width="stretch")

                with st.spinner("Нормализация и валидация..."):
                    vr: ValidationResult = normalize_and_validate(df_src, spec)

                # Apply brand filter (if configured and applicable)
                def _sget(key: str) -> str | None:
                    try:
                        return st.secrets[key]  # type: ignore[index]
                    except Exception:
                        return None

                brand_raw = st.session_state.get("brand_whitelist") or _sget("brand_whitelist")
                allowed_brands = parse_brand_list(brand_raw)

                df_norm = vr.df_normalized
                if spec.id == "wb_products" and "barcodes" in df_norm.columns:
                    df_norm = df_norm.copy()
                    df_norm["primary_barcode"] = df_norm["barcodes"].map(
                        lambda v: _select_barcode(v, prefer_last=True)
                    )
                df_filtered = (
                    filter_df_by_brands(df_norm, allowed_brands)
                    if ("brand" in df_norm.columns and allowed_brands)
                    else df_norm
                )

                st.session_state["norm_df"] = df_filtered
                st.session_state["norm_errors"] = vr.errors

                st.subheader("Сводка")
                m1, m2, m3 = st.columns(3)
                m1.metric("Всего строк", vr.rows_total)
                m2.metric("Валидных строк", vr.rows_valid)
                m3.metric("Ошибок", len(vr.errors))

                if "brand" in df_norm.columns and allowed_brands:
                    st.info(
                        f"Применён фильтр брендов (в списке: {len(allowed_brands)}). "
                        f"К загрузке после фильтра: {len(df_filtered)} строк."
                    )

                if vr.errors:
                    st.warning("Обнаружены ошибки. Строки с ошибками будут пропущены при импорте.")
                    st.dataframe(_arrow_safe(pd.DataFrame(vr.errors)), width="stretch")

                    # Логирование ошибок в файл (только для Punta)
                    if report_id == "punta_barcodes":
                        from datetime import datetime
                        from pathlib import Path as _Path

                        log_dir = _Path("logs")
                        log_dir.mkdir(exist_ok=True)
                        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
                        log_path = log_dir / f"punta_barcodes_{ts}.log"
                        lines = [
                            f"row={e.get('row')} | errors={e.get('errors')}" for e in vr.errors
                        ]
                        log_path.write_text("\n".join(lines), encoding="utf-8")
                        st.info(f"Лог ошибок сохранён: {log_path}")

                st.subheader("Нормализованные данные (превью)")
                st.dataframe(_arrow_safe(df_filtered.head(20)), width="stretch")

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
                    def _sget(key: str) -> str | None:
                        try:
                            return st.secrets[key]  # type: ignore[index]
                        except Exception:
                            return None

                    md_token = st.session_state.get("md_token") or _sget("md_token")
                    md_database = st.session_state.get("md_database") or _sget("md_database")
                    if not md_token:
                        st.warning("MD токен не найден. Укажите его на странице Настройки.")

                    # Re-apply brand filter using the latest settings just before import (safety net)
                    brand_raw = st.session_state.get("brand_whitelist") or _sget("brand_whitelist")
                    allowed_brands = parse_brand_list(brand_raw)
                    if "brand" in df_ready.columns and allowed_brands:
                        df_ready = filter_df_by_brands(df_ready, allowed_brands)

                    with st.spinner("Загрузка в MotherDuck..."):
                        if report_id == "punta_barcodes":
                            # Для Punta всегда заменяем данные конкретной коллекции
                            coll = st.session_state.get("punta_collection")
                            if not coll:
                                st.error("Не указана коллекция для загрузки.")
                                st.stop()
                            msg = load_dataframe_partitioned(
                                df_ready,
                                table=spec.table,
                                partition_field="collection",
                                partition_value=str(coll),
                                md_token=md_token,
                                md_database=md_database,
                            )
                        else:
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

elif report_id == "punta_google":
    # Поток для Punta Google (без загрузчика файлов)
    with preview_col:
        if st.button("Предпросмотр", type="primary", disabled=not gs_url):
            try:
                with st.spinner("Чтение Google Sheets как CSV..."):
                    df_src = gs_read_csv(gs_url)
                # Дедупликация по wb_sku (оставляем первое вхождение)
                df_src = gs_dedup(df_src)

                st.session_state["norm_df"] = df_src
                st.session_state["norm_errors"] = []

                st.subheader("Сводка")
                m1, m2 = st.columns(2)
                m1.metric("Всего строк", len(df_src))
                m2.metric("Колонок", len(df_src.columns))

                st.subheader("Данные (превью)")
                st.dataframe(_arrow_safe(df_src.head(20)), width="stretch")

                csv_buf = io.StringIO()
                df_src.to_csv(csv_buf, index=False)
                st.download_button(
                    "Скачать CSV", data=csv_buf.getvalue().encode("utf-8"), file_name="punta_google.csv", mime="text/csv"
                )
            except Exception as exc:  # noqa: BLE001
                st.exception(exc)

    with import_col:
        if st.button("Импортировать в БД", disabled="norm_df" not in st.session_state or not gs_url):
            try:
                df_ready: pd.DataFrame = st.session_state.get("norm_df", pd.DataFrame())
                if df_ready.empty:
                    st.error("Нет данных для импорта. Сначала выполните предпросмотр.")
                else:
                    def _sget(key: str) -> str | None:
                        try:
                            return st.secrets[key]  # type: ignore[index]
                        except Exception:
                            return None

                    md_token = st.session_state.get("md_token") or _sget("md_token")
                    md_database = st.session_state.get("md_database") or _sget("md_database")
                    if not md_token:
                        st.warning("MD токен не найден. Укажите его на странице Настройки.")

                    with st.spinner("Загрузка в MotherDuck (полная замена)..."):
                        msg = load_dataframe(
                            df_ready,
                            table=spec.table,
                            md_token=md_token,
                            md_database=md_database,
                            replace=True,
                        )

                    # Создание индекса по wb_sku, если колонка присутствует
                    try:
                        with get_connection(md_token=md_token, md_database=md_database) as con:
                            info = con.execute('PRAGMA table_info("punta_google")').fetch_df()
                            cols = set(info["name"].astype(str).tolist())
                            if "wb_sku" in cols:
                                con.execute(
                                    'CREATE INDEX IF NOT EXISTS idx_punta_google_wb_sku ON "punta_google" (wb_sku)'
                                )
                    except Exception:
                        # Индекс необязателен; не прерываем импорт
                        pass

                    st.success(msg)
            except Exception as exc:  # noqa: BLE001
                st.exception(exc)
else:
    st.info("Загрузите файл для начала работы или укажите ссылку на Google Sheets.")
