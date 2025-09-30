from __future__ import annotations

import pandas as pd
import streamlit as st
from dataforge.campaign_selection import select_campaign_candidates
from dataforge.ui import setup_page

setup_page(title="DataForge", icon="🛠️")

st.title("🎯 Подбор РК для Ozon")
st.caption(
    "Подбор кандидатов для рекламных кампаний на основе артикулов WB. "
    "Система находит соответствующие товары Ozon с учетом остатков и заказов."
)


def _sget(key: str) -> str | None:
    """Получить значение из secrets с обработкой ошибок."""
    try:
        return st.secrets[key]  # type: ignore[index]
    except Exception:
        return None


def parse_input(text: str) -> list[str]:
    """Разбить текст на список артикулов (разделители: пробелы, переносы, запятые)."""
    tokens = [t.strip() for t in text.replace(",", " ").split()]
    return [t for t in tokens if t]


# Получение токена и базы данных
md_token = st.session_state.get("md_token") or _sget("md_token")
md_database = st.session_state.get("md_database") or _sget("md_database")

if not md_token:
    st.warning("⚠️ MD токен не найден. Укажите его на странице Настройки.")
    st.stop()

# --- Форма ввода параметров ---
st.subheader("📝 Параметры подбора")

wb_skus_input = st.text_area(
    "Артикулы WB (wb_sku)",
    placeholder="123456789\n987654321\n...",
    height=150,
    help="Введите артикулы WB через пробел, запятую или с новой строки",
)

col1, col2, col3 = st.columns(3)
with col1:
    min_stock = st.number_input(
        "Min остаток",
        min_value=0,
        value=5,
        help="Минимальный остаток товара для включения в подбор",
    )
with col2:
    min_candidates = st.number_input(
        "Min кандидатов",
        min_value=1,
        value=1,
        help="Минимальное количество кандидатов в группе (иначе группа исключается)",
    )
with col3:
    max_candidates = st.number_input(
        "Max кандидатов",
        min_value=1,
        value=10,
        help="Максимальное количество кандидатов на одну группу",
    )

search_btn = st.button("🔍 Подбор", type="primary")

# --- Обработка запроса ---
if search_btn:
    wb_skus = parse_input(wb_skus_input)

    if not wb_skus:
        st.warning("⚠️ Введите хотя бы один артикул WB")
    elif min_candidates > max_candidates:
        st.error("❌ Min кандидатов не может быть больше Max кандидатов")
    else:
        with st.spinner("🔄 Поиск кандидатов..."):
            try:
                results = select_campaign_candidates(
                    wb_skus=wb_skus,
                    min_stock=min_stock,
                    min_candidates=min_candidates,
                    max_candidates=max_candidates,
                    md_token=md_token,
                    md_database=md_database,
                )

                if results:
                    df = pd.DataFrame(results)

                    # Переименование колонок для UI
                    df_display = df.rename(
                        columns={
                            "group_number": "№ группы",
                            "wb_sku": "Артикул WB",
                            "oz_sku": "Артикул OZ",
                            "oz_vendor_code": "Артикул поставщика OZ",
                            "size_stock": "Остаток размера",
                            "model_stock": "Остаток модели",
                            "size_orders": "Заказы размера (14д)",
                            "model_orders": "Заказы модели (14д)",
                        }
                    )

                    # Информация о результатах
                    unique_groups = df["group_number"].nunique()
                    st.success(
                        f"✅ Найдено **{len(results)}** кандидатов в **{unique_groups}** группах"
                    )

                    # Статистика по группам
                    st.markdown("### 📊 Статистика по группам")
                    group_stats = (
                        df.groupby("wb_sku")
                        .agg(
                            {
                                "oz_vendor_code": "count",
                                "size_stock": "sum",
                                "size_orders": "sum",
                                "model_stock": "first",
                                "model_orders": "first",
                            }
                        )
                        .rename(
                            columns={
                                "oz_vendor_code": "Кандидатов",
                                "size_stock": "Сумма остатков выбранных",
                                "size_orders": "Сумма заказов выбранных",
                                "model_stock": "Остаток модели",
                                "model_orders": "Заказы модели",
                            }
                        )
                    )
                    st.dataframe(group_stats, width="stretch")

                    # Таблица результатов
                    st.markdown("### 📋 Результаты подбора")
                    st.dataframe(df_display, width="stretch", height=400)

                    # Экспорт в CSV
                    csv = df_display.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        label="📥 Скачать CSV",
                        data=csv,
                        file_name="campaign_candidates.csv",
                        mime="text/csv",
                    )

                else:
                    st.info(
                        "ℹ️ Нет подходящих кандидатов по заданным критериям. "
                        "Попробуйте изменить параметры подбора."
                    )

            except Exception as e:
                st.error(f"❌ Ошибка при подборе кандидатов: {e}")
                st.exception(e)