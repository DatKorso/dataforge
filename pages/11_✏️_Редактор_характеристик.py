"""
Attributes mapping editor page.

This page allows users to manage attribute mappings between Punta products
and various marketplaces (Wildberries, Ozon, Lamoda).
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st
from dataforge.attributes import (
    CATEGORY_COLUMNS,
    CATEGORY_NAMES,
    export_attributes_to_excel,
    get_attributes_by_category,
    get_next_id_for_category,
    import_unique_values_from_punta,
    merge_with_existing_mappings,
    save_category_mappings,
)
from dataforge.ui import setup_page

setup_page(title="Редактор характеристик", icon="✏️")

st.title("✏️ Редактор характеристик")
st.caption(
    "Справочник соответствия характеристик товаров между Punta и маркетплейсами (ВБ, Ozon, Lamoda)."
)


def _sget(key: str) -> str | None:
    """Get secret value safely."""
    try:
        return st.secrets[key]  # type: ignore[index]
    except Exception:
        return None


# Get credentials
md_token = st.session_state.get("md_token") or _sget("md_token")
md_database = st.session_state.get("md_database") or _sget("md_database")

# Export button at the top
col_export, col_info = st.columns([1, 4])
with col_export:
    if st.button("📥 Экспорт в Excel", width="stretch"):
        try:
            excel_file = export_attributes_to_excel(md_token=md_token, md_database=md_database)
            st.download_button(
                label="💾 Скачать Excel",
                data=excel_file,
                file_name=f"attributes_mapping_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
            )
        except Exception as exc:
            st.error(f"Ошибка экспорта: {exc}")

with col_info:
    st.info(
        "💡 Используйте вкладки ниже для редактирования соответствий. "
        "Изменения сохраняются при нажатии кнопки **Сохранить изменения**."
    )

st.divider()

# Create tabs for each category
tabs = st.tabs([CATEGORY_NAMES[cat] for cat in CATEGORY_NAMES])

for tab_idx, (category_key, category_name) in enumerate(CATEGORY_NAMES.items()):
    with tabs[tab_idx]:
        st.subheader(f"📋 {category_name}")
        
        # Show import button for material categories
        material_categories = ["upper_material", "lining_material", "insole_material", "outsole_material"]
        if category_key in material_categories:
            col_import, col_spacer = st.columns([2, 3])
            with col_import:
                if st.button(
                    f"📥 Импорт из Punta",
                    key=f"import_{category_key}",
                    width="stretch",
                    help="Загрузить уникальные значения из таблицы punta_products",
                ):
                    try:
                        # Import unique values
                        new_values = import_unique_values_from_punta(
                            category_key,
                            md_token=md_token,
                            md_database=md_database,
                        )
                        
                        if new_values.empty:
                            st.warning("⚠️ Не найдено значений для импорта из punta_products")
                        else:
                            # Load existing to compute how many will be added
                            existing_before = get_attributes_by_category(
                                category_key, md_token=md_token, md_database=md_database
                            )

                            # Merge with existing (function will deduplicate and reassign IDs)
                            merged_df = merge_with_existing_mappings(
                                category_key,
                                new_values,
                                md_token=md_token,
                                md_database=md_database,
                            )

                            # Save merged data
                            save_category_mappings(
                                category_key,
                                merged_df,
                                md_token=md_token,
                                md_database=md_database,
                            )

                            added_count = len(merged_df) - len(existing_before)
                            total_count = len(merged_df)
                            st.success(f"✅ Импортировано {added_count} новых значений. Всего записей: {total_count}")
                            st.rerun()
                    except Exception as exc:
                        st.error(f"❌ Ошибка импорта: {exc}")
            st.divider()
        
        # Get column configuration for this category
        column_config = CATEGORY_COLUMNS.get(category_key, {})
        
        # Load data
        try:
            df = get_attributes_by_category(
                category_key,
                md_token=md_token,
                md_database=md_database,
            )
        except Exception as exc:
            st.error(f"Ошибка загрузки данных: {exc}")
            continue
        
        # Prepare columns for editing
        edit_columns = ["id", "punta_value", "wb_value", "oz_value", "lamoda_value"]
        
        # Add optional columns based on configuration
        if column_config.get("additional_field"):
            edit_columns.append("additional_field")
        if column_config.get("description"):
            edit_columns.append("description")
        
        # Prepare DataFrame with proper types
        if df.empty:
            # Create empty DataFrame with correct dtypes
            dtype_dict = {col: "object" if col != "id" else "int64" for col in edit_columns}
            df = pd.DataFrame(columns=edit_columns).astype(dtype_dict)
        else:
            # Ensure all required columns exist
            for col in edit_columns:
                if col not in df.columns:
                    df[col] = None
            df = df[edit_columns].copy()
            # Convert all non-id columns to object type for proper text editing
            for col in df.columns:
                if col != "id":
                    df[col] = df[col].astype("object")
        
        # Configure column display names
        column_display_config = {
            "id": st.column_config.NumberColumn(
                "ID",
                help="Уникальный идентификатор записи",
                disabled=False,
                required=True,
                min_value=1,
                step=1,
            ),
            "punta_value": st.column_config.TextColumn(
                column_config.get("punta_value", "Punta"),
                help="Значение из Punta",
                max_chars=200,
            ),
            "wb_value": st.column_config.TextColumn(
                column_config.get("wb_value", "Wildberries"),
                help="Значение для Wildberries",
                max_chars=200,
            ),
            "oz_value": st.column_config.TextColumn(
                column_config.get("oz_value", "Ozon"),
                help="Значение для Ozon",
                max_chars=200,
            ),
            "lamoda_value": st.column_config.TextColumn(
                column_config.get("lamoda_value", "Lamoda"),
                help="Значение для Lamoda",
                max_chars=200,
            ),
        }
        
        # Add optional columns to config
        if "additional_field" in edit_columns:
            column_display_config["additional_field"] = st.column_config.TextColumn(
                column_config.get("additional_field", "Дополнительно"),
                help="Дополнительное поле",
                max_chars=200,
            )
        if "description" in edit_columns:
            column_display_config["description"] = st.column_config.TextColumn(
                column_config.get("description", "Описание"),
                help="Описание или примечание",
                max_chars=500,
            )
        
        # Data editor
        edited_df = st.data_editor(
            df,
            column_config=column_display_config,
            num_rows="dynamic",
            width="stretch",
            key=f"editor_{category_key}",
            hide_index=True,
        )
        
        # Action buttons
        col_save, col_add, col_clear = st.columns([2, 2, 1])
        
        with col_save:
            if st.button(
                "💾 Сохранить изменения",
                key=f"save_{category_key}",
                width="stretch",
                type="primary",
            ):
                try:
                    # Validate IDs are unique and positive
                    if edited_df["id"].isna().any():
                        st.error("❌ Все записи должны иметь ID")
                    elif edited_df["id"].duplicated().any():
                        st.error("❌ ID должны быть уникальными")
                    elif (edited_df["id"] <= 0).any():
                        st.error("❌ ID должны быть положительными числами")
                    else:
                        # Save to database
                        save_category_mappings(
                            category_key,
                            edited_df,
                            md_token=md_token,
                            md_database=md_database,
                        )
                        st.success(f"✅ Данные для категории '{category_name}' успешно сохранены!")
                        st.rerun()
                except Exception as exc:
                    st.error(f"❌ Ошибка сохранения: {exc}")
        
        with col_add:
            if st.button(
                "➕ Добавить пустую строку",
                key=f"add_{category_key}",
                width="stretch",
            ):
                try:
                    next_id = get_next_id_for_category(
                        category_key,
                        md_token=md_token,
                        md_database=md_database,
                    )
                    st.info(f"💡 Следующий доступный ID: {next_id}")
                except Exception as exc:
                    st.warning(f"Не удалось определить следующий ID: {exc}")
        
        with col_clear:
            if st.button(
                "🗑️ Очистить",
                key=f"clear_{category_key}",
                width="stretch",
            ):
                if st.session_state.get(f"confirm_clear_{category_key}", False):
                    try:
                        # Save empty dataframe to clear the category
                        empty_df = pd.DataFrame(columns=edit_columns)
                        save_category_mappings(
                            category_key,
                            empty_df,
                            md_token=md_token,
                            md_database=md_database,
                        )
                        st.success(f"✅ Категория '{category_name}' очищена")
                        st.session_state[f"confirm_clear_{category_key}"] = False
                        st.rerun()
                    except Exception as exc:
                        st.error(f"❌ Ошибка очистки: {exc}")
                else:
                    st.session_state[f"confirm_clear_{category_key}"] = True
                    st.warning("⚠️ Нажмите ещё раз для подтверждения очистки всей категории")
        
        # Display current row count
        st.caption(f"Всего записей: {len(edited_df)}")
        
        st.divider()

# Help section
with st.expander("❓ Справка"):
    st.markdown("""
    ### Как использовать редактор характеристик
    
    1. **Навигация**: Переключайтесь между категориями с помощью вкладок
    2. **Редактирование**: 
       - Нажмите на ячейку для редактирования значения
       - Используйте **➕ Добавить строку** для создания новой записи
       - Используйте **🗑️ Удалить** для удаления строки
    3. **Сохранение**: Нажмите **💾 Сохранить изменения** для записи в базу данных
    4. **Экспорт**: Используйте кнопку **📥 Экспорт в Excel** для выгрузки всего справочника
    
    ### Структура категорий
    
    - **Материал верха**: Соответствия для материалов верха обуви
    - **Материал подкладки**: Соответствия для материалов подкладки
    - **Материал стельки**: Соответствия для материалов стельки
    - **Материал подошвы**: Соответствия для материалов подошвы
    - **Сезон**: Соответствия для сезонности (зима, лето, демисезон)
    - **Пол**: Соответствия для пола (мужской, женский, унисекс)
    - **Предмет**: Соответствия для типов обуви (ботинки, туфли, кроссовки)
    - **Цвет**: Соответствия для цветов
    - **Застежка**: Соответствия для типов застежек
    - **Каблук**: Соответствия для типов каблуков
    
    ### Важные примечания
    
    - ID должны быть уникальными в рамках каждой категории
    - Пустые значения допускаются (если характеристика не применима для маркетплейса)
    - Изменения сохраняются только после нажатия кнопки **Сохранить изменения**
    """)
