"""Excel merge page v2 - improved version with clean architecture."""

from __future__ import annotations

import logging
import traceback

import streamlit as st
from dataforge.excel_merge import (
    ExcelMergeError,
    MergeConfig,
    SheetConfig,
    get_sheet_info,
    merge_excel_files,
)
from dataforge.ui import guard_page, setup_page

logger = logging.getLogger(__name__)

setup_page(title="Объединение Excel", icon="📎")
guard_page("enable_excel_merge", default=True, message="Страница объединения Excel отключена.")

st.title("📎 Объединение Excel файлов")
st.caption(
    "Выберите начальный файл, настройте параметры объединения и фильтрации, "
    "затем добавьте дополнительные файлы для объединения."
)

# Preset configurations for known sheet types
SHEET_PRESETS = {
    "Шаблон": {
        "header_rows": 4,
        "include_by_default": True,
        "supports_brand_filter": True,
    },
    "Озон.Видео": {
        "header_rows": 4,
        "include_by_default": True,
        "supports_article_filter": True,
    },
    "Озон.Видеообложка": {
        "header_rows": 4,
        "include_by_default": True,
        "supports_article_filter": True,
    },
}

# Sidebar instructions
st.sidebar.header("📖 Инструкция")
st.sidebar.markdown(
    """
1. **Загрузите начальный файл** (.xlsx)
2. **Настройте листы**: выберите какие листы объединять, укажите количество строк заголовка
3. **Настройте фильтры** (опционально): укажите бренд для фильтрации
4. **Добавьте файлы** для объединения
5. **Нажмите "Объединить"**
"""
)

# Main file uploader
st.subheader("1️⃣ Начальный файл")
uploaded_initial = st.file_uploader(
    "Выберите начальный .xlsx файл (шаблон)",
    type=["xlsx"],
    key="merge_initial",
    help="Этот файл будет использован как шаблон. Его структура определит конфигурацию объединения.",
)

if uploaded_initial is None:
    st.info("👆 Загрузите начальный файл для продолжения")
    st.stop()

# Read initial file
try:
    initial_bytes = uploaded_initial.read()
    sheets_info = get_sheet_info(initial_bytes)
except Exception as exc:
    st.error(f"❌ Не удалось прочитать файл: {exc}")
    logger.error(f"Failed to read initial file: {exc}", exc_info=True)
    st.stop()

if not sheets_info:
    st.error("❌ Не удалось получить информацию о листах файла")
    st.stop()

st.success(f"✅ Файл загружен: {len(sheets_info)} лист(ов) найдено")

# Sheet configuration section
st.subheader("2️⃣ Настройка листов")
st.caption(
    "Выберите какие листы объединять и укажите количество строк заголовка для каждого. "
    "**Невыбранные листы останутся в файле без изменений.**"
)

sheet_configs: dict[str, SheetConfig] = {}

for sheet_name, row_count in sheets_info:
    preset = SHEET_PRESETS.get(sheet_name, {})
    default_include = preset.get("include_by_default", False)
    default_headers = preset.get("header_rows", 1)

    with st.expander(f"📄 **{sheet_name}** (строк: {row_count})", expanded=default_include):
        cols = st.columns([2, 2, 3])

        with cols[0]:
            include = st.checkbox(
                "Включить лист",
                value=default_include,
                key=f"include_{sheet_name}",
                help="Отметьте, чтобы включить этот лист в объединение",
            )

        with cols[1]:
            header_rows = st.number_input(
                "Строк заголовка",
                min_value=0,
                max_value=20,
                value=default_headers,
                step=1,
                key=f"headers_{sheet_name}",
                disabled=not include,
                help="Количество строк в начале листа, которые считаются заголовком",
            )

        with cols[2]:
            # Filter options based on preset
            filter_brand = False
            filter_articles = False

            if include:
                if preset.get("supports_brand_filter"):
                    filter_brand = st.checkbox(
                        "Фильтровать по бренду",
                        value=True,
                        key=f"filter_brand_{sheet_name}",
                        help="Применить фильтр по бренду к этому листу",
                    )
                if preset.get("supports_article_filter"):
                    filter_articles = st.checkbox(
                        "Фильтровать по артикулам из Шаблона",
                        value=True,
                        key=f"filter_articles_{sheet_name}",
                        help="Оставить только строки с артикулами, присутствующими в листе Шаблон",
                    )

        sheet_configs[sheet_name] = SheetConfig(
            name=sheet_name,
            include=include,
            header_rows=header_rows,
            filter_by_brand=filter_brand,
            filter_by_articles=filter_articles,
        )

# Filter configuration section
st.subheader("3️⃣ Настройка фильтров")

cols = st.columns([2, 2])

with cols[0]:
    enable_brand_filter = st.checkbox(
        "Включить фильтр по бренду",
        value=True,
        key="enable_brand_filter",
        help="Фильтровать данные по бренду (применяется к листам с включённой опцией фильтрации)",
    )

with cols[1]:
    brand_value = st.text_input(
        "Значение бренда",
        value="Shuzzi",
        key="brand_value",
        disabled=not enable_brand_filter,
        help="Значение бренда для фильтрации (поиск подстроки, регистр не важен)",
    )

if enable_brand_filter and not brand_value.strip():
    st.warning("⚠️ Фильтр по бренду включён, но значение не указано")

# Additional files section
st.subheader("4️⃣ Дополнительные файлы")
uploaded_additional = st.file_uploader(
    "Добавьте файлы для объединения (можно несколько)",
    type=["xlsx"],
    accept_multiple_files=True,
    key="merge_additional",
    help="Эти файлы будут объединены с начальным файлом. Заголовки будут взяты из начального файла.",
)

if uploaded_additional:
    st.info(f"📁 Выбрано файлов для объединения: {len(uploaded_additional)}")
else:
    st.info("ℹ️ Дополнительные файлы не выбраны. Будет обработан только начальный файл с применением фильтров.")

# Merge button and processing
st.markdown("---")
st.subheader("5️⃣ Запуск объединения")

# Show summary
included_sheets = [name for name, cfg in sheet_configs.items() if cfg.include]
excluded_sheets = [name for name, cfg in sheet_configs.items() if not cfg.include]

if not included_sheets:
    st.error("❌ Не выбрано ни одного листа для объединения")
    st.stop()

with st.expander("📋 Сводка конфигурации", expanded=False):
    st.write("**Листы для объединения:**")
    for name in included_sheets:
        cfg = sheet_configs[name]
        filters = []
        if cfg.filter_by_brand:
            filters.append("бренд")
        if cfg.filter_by_articles:
            filters.append("артикулы")
        filter_text = f" (фильтры: {', '.join(filters)})" if filters else ""
        st.write(f"- {name}: {cfg.header_rows} строк заголовка{filter_text}")

    if excluded_sheets:
        st.write("**Листы без изменений:**")
        for name in excluded_sheets:
            st.write(f"- {name} (не будет объединяться, останется как в шаблоне)")

    if enable_brand_filter and brand_value.strip():
        st.write(f"**Фильтр по бренду:** `{brand_value}`")

    st.write(f"**Всего файлов:** {1 + len(uploaded_additional or [])}")

# Progress indicators
progress_bar = st.progress(0.0)
status_text = st.empty()

if st.button("🚀 Объединить файлы", type="primary", use_container_width=True):
    try:
        # Prepare file bytes
        additional_bytes = []
        if uploaded_additional:
            for f in uploaded_additional:
                additional_bytes.append(f.read())

        # Build config
        merge_config = MergeConfig(
            sheets=sheet_configs,
            brand_filter=brand_value.strip() if enable_brand_filter else None,
        )

        # Progress callback
        def progress_callback(pct: float, msg: str):
            progress_bar.progress(min(1.0, max(0.0, pct)))
            status_text.text(msg)

        status_text.text("🔄 Начинаю объединение...")

        # Perform merge
        result_bytes = merge_excel_files(
            template_bytes=initial_bytes,
            additional_files_bytes=additional_bytes,
            config=merge_config,
            progress_callback=progress_callback,
        )

        # Success
        progress_bar.progress(1.0)
        status_text.empty()
        st.success("✅ Файлы успешно объединены!")

        # Download button
        st.download_button(
            label="📥 Скачать объединённый файл",
            data=result_bytes,
            file_name="merged_excel.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
        )

    except ExcelMergeError as e:
        progress_bar.empty()
        status_text.empty()
        st.error(f"❌ Ошибка при объединении файлов: {e}")
        logger.error(f"Merge error: {e}", exc_info=True)

        with st.expander("🔍 Подробности ошибки"):
            st.code(traceback.format_exc())

    except Exception as e:
        progress_bar.empty()
        status_text.empty()
        st.error(f"❌ Неожиданная ошибка: {e}")
        logger.error(f"Unexpected error during merge: {e}", exc_info=True)

        with st.expander("🔍 Подробности ошибки"):
            st.code(traceback.format_exc())

# Footer with info
st.markdown("---")
st.caption(
    "💡 **Подсказка:** Используйте настройки фильтров для точной настройки результата объединения. "
    "Невыбранные листы останутся в файле без изменений."
)
