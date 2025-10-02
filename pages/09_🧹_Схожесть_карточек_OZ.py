from __future__ import annotations

import pandas as pd
import streamlit as st
from dataforge.db import get_connection
from dataforge.similarity_config import SimilarityScoringConfig
from dataforge.ui import setup_page

setup_page(title="DataForge — Схожесть карточек OZ", icon="🧹")

st.title("🧹 Схожесть карточек OZ")
st.caption("Сравнение схожести между двумя WB товарами по алгоритму похожести.")


def get_product_data(wb_sku: str, md_token: str | None = None, md_database: str | None = None) -> pd.DataFrame:
    """Получить данные товара из wb_products и punta_google."""
    try:
        with get_connection(md_token=md_token, md_database=md_database) as con:
            # Получаем данные из wb_products
            wb_query = """
            SELECT
                wb_sku,
                product_name,
                seller_category,
                brand,
                gender,
                color,
                primary_barcode,
                size,
                russian_size
            FROM wb_products
            WHERE wb_sku = ?
            """
            wb_df = con.execute(wb_query, [wb_sku]).fetch_df()

            if wb_df.empty:
                return pd.DataFrame()

            # Получаем данные из punta_google (если таблица существует)
            punta_data = {}
            try:
                punta_query = """
                SELECT
                    season,
                    color,
                    lacing_type,
                    material_short,
                    mega_last,
                    best_last,
                    new_last,
                    model_name
                FROM punta_google
                WHERE wb_sku = ?
                """
                punta_df = con.execute(punta_query, [wb_sku]).fetch_df()
                if not punta_df.empty:
                    punta_data = punta_df.iloc[0].to_dict()
            except Exception:
                # Таблица punta_google может не существовать
                pass

            # Объединяем данные
            result = wb_df.iloc[0].to_dict()
            result.update(punta_data)
            return pd.DataFrame([result])

    except Exception as e:
        st.error(f"Ошибка при получении данных товара: {e}")
        return pd.DataFrame()


def calculate_similarity_details(product_left: pd.Series, product_right: pd.Series) -> dict:
    """Рассчитать подробную схожесть между двумя товарами."""
    cfg = SimilarityScoringConfig()

    # Извлекаем данные товаров
    left_data = product_left.to_dict()
    right_data = product_right.to_dict()

    details = {
        "parameters": [],
        "total_score": 0.0,
        "final_score": 0.0
    }

    # Базовый скор
    base_score = cfg.base_score
    details["parameters"].append({
        "parameter": "Базовый скор",
        "left_value": "—",
        "right_value": "—",
        "match": True,
        "score": base_score
    })

    total_score = base_score

    # Сезон
    left_season = left_data.get("season")
    right_season = right_data.get("season")
    season_score = 0

    if left_season and right_season:
        season_score = cfg.season_match_bonus if left_season == right_season else cfg.season_mismatch_penalty
    elif left_season or right_season:
        # Если только один сезон указан, не применяем штраф/бонус
        season_score = 0

    details["parameters"].append({
        "parameter": "Сезон",
        "left_value": left_season or "—",
        "right_value": right_season or "—",
        "match": left_season == right_season if left_season and right_season else None,
        "score": season_score
    })
    total_score += season_score

    # Цвет (из punta_google)
    left_color = left_data.get("color")
    right_color = right_data.get("color")
    color_score = cfg.color_match_bonus if left_color and left_color == right_color else 0

    details["parameters"].append({
        "parameter": "Цвет (Punta)",
        "left_value": left_color or "—",
        "right_value": right_color or "—",
        "match": left_color == right_color if left_color and right_color else None,
        "score": color_score
    })
    total_score += color_score

    # Материал
    left_material = left_data.get("material_short")
    right_material = right_data.get("material_short")
    material_score = cfg.material_match_bonus if left_material and left_material == right_material else 0

    details["parameters"].append({
        "parameter": "Материал",
        "left_value": left_material or "—",
        "right_value": right_material or "—",
        "match": left_material == right_material if left_material and right_material else None,
        "score": material_score
    })
    total_score += material_score

    # Крепление
    left_fastener = left_data.get("lacing_type")
    right_fastener = right_data.get("lacing_type")
    fastener_score = cfg.fastener_match_bonus if left_fastener and left_fastener == right_fastener else 0

    details["parameters"].append({
        "parameter": "Крепление",
        "left_value": left_fastener or "—",
        "right_value": right_fastener or "—",
        "match": left_fastener == right_fastener if left_fastener and right_fastener else None,
        "score": fastener_score
    })
    total_score += fastener_score

    # Колодка
    left_mega = left_data.get("mega_last")
    left_best = left_data.get("best_last")
    left_new = left_data.get("new_last")
    right_mega = right_data.get("mega_last")
    right_best = right_data.get("best_last")
    right_new = right_data.get("new_last")

    last_score = 0
    last_match = False

    if left_mega and left_mega == right_mega:
        last_score = cfg.mega_last_bonus
        last_match = True
    elif left_best and left_best == right_best:
        last_score = cfg.best_last_bonus
        last_match = True
    elif left_new and left_new == right_new:
        last_score = cfg.new_last_bonus
        last_match = True

    last_left = left_mega or left_best or left_new or "—"
    last_right = right_mega or right_best or right_new or "—"

    details["parameters"].append({
        "parameter": "Колодка",
        "left_value": last_left,
        "right_value": last_right,
        "match": last_match,
        "score": last_score
    })
    total_score += last_score

    # Модель
    left_model = left_data.get("model_name")
    right_model = right_data.get("model_name")
    model_score = cfg.model_match_bonus if left_model and left_model == right_model else 0

    details["parameters"].append({
        "parameter": "Модель",
        "left_value": left_model or "—",
        "right_value": right_model or "—",
        "match": left_model == right_model if left_model and right_model else None,
        "score": model_score
    })
    total_score += model_score

    # Применяем штраф за отсутствие колодки
    adjusted_score = total_score * cfg.no_last_penalty_multiplier if last_score == 0 else total_score

    # Ограничиваем максимальным скором
    final_score = min(cfg.max_score, adjusted_score)

    details["total_score"] = total_score
    details["final_score"] = final_score

    return details


# Получение токенов
md_token = st.session_state.get("md_token") or st.secrets.get("md_token") if hasattr(st, "secrets") else None
md_database = st.session_state.get("md_database") or st.secrets.get("md_database") if hasattr(st, "secrets") else None

if not md_token:
    st.warning("MD токен не найден. Укажите его на странице Настройки.")


# Основной UI
st.header("Сравнение товаров")

with st.form(key="similarity_compare_form"):
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Товар слева")
        wb_sku_left = st.text_input(
            "WB SKU товара слева",
            value=st.session_state.get("similarity_wb_sku_left", ""),
            key="similarity_wb_sku_left",
            help="Введите WB SKU первого товара для сравнения"
        )

    with col2:
        st.subheader("Товар справа")
        wb_sku_right = st.text_input(
            "WB SKU товара справа",
            value=st.session_state.get("similarity_wb_sku_right", ""),
            key="similarity_wb_sku_right",
            help="Введите WB SKU второго товара для сравнения"
        )

    submitted = st.form_submit_button("Сравнить", type="primary")

if submitted:
    if not md_token:
        st.error("MD токен отсутствует. Укажите его на странице Настройки.")
        st.stop()

    wb_sku_left_val = wb_sku_left.strip() if wb_sku_left else ""
    wb_sku_right_val = wb_sku_right.strip() if wb_sku_right else ""

    if not wb_sku_left_val or not wb_sku_right_val:
        st.error("Введите оба WB SKU для сравнения")
        st.stop()

    if wb_sku_left_val == wb_sku_right_val:
        st.error("Введите разные WB SKU для сравнения")
        st.stop()

    # Получаем данные товаров
    with st.spinner("Получение данных товаров..."):
        left_data = get_product_data(wb_sku_left_val, md_token, md_database)
        right_data = get_product_data(wb_sku_right_val, md_token, md_database)

    if left_data.empty:
        st.error(f"Товар с WB SKU {wb_sku_left_val} не найден")
        st.stop()

    if right_data.empty:
        st.error(f"Товар с WB SKU {wb_sku_right_val} не найден")
        st.stop()

    # Рассчитываем схожесть
    similarity_details = calculate_similarity_details(left_data.iloc[0], right_data.iloc[0])

    # Отображаем результаты
    st.success("✅ Сравнение выполнено")

    # Side-by-side карточки товаров
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🏷️ Товар слева")
        product_info = left_data.iloc[0]
        st.markdown(f"**WB SKU:** {product_info.get('wb_sku', '—')}")
        st.markdown(f"**Название:** {product_info.get('product_name', '—')}")
        st.markdown(f"**Бренд:** {product_info.get('brand', '—')}")
        st.markdown(f"**Категория:** {product_info.get('seller_category', '—')}")
        st.markdown(f"**Пол:** {product_info.get('gender', '—')}")
        st.markdown(f"**Цвет (WB):** {product_info.get('color', '—')}")
        st.markdown(f"**Размер:** {product_info.get('size', '—')} / {product_info.get('russian_size', '—')}")

    with col2:
        st.subheader("🏷️ Товар справа")
        product_info = right_data.iloc[0]
        st.markdown(f"**WB SKU:** {product_info.get('wb_sku', '—')}")
        st.markdown(f"**Название:** {product_info.get('product_name', '—')}")
        st.markdown(f"**Бренд:** {product_info.get('brand', '—')}")
        st.markdown(f"**Категория:** {product_info.get('seller_category', '—')}")
        st.markdown(f"**Пол:** {product_info.get('gender', '—')}")
        st.markdown(f"**Цвет (WB):** {product_info.get('color', '—')}")
        st.markdown(f"**Размер:** {product_info.get('size', '—')} / {product_info.get('russian_size', '—')}")

    # Таблица сравнения параметров
    st.subheader("📊 Сравнение параметров схожести")

    comparison_data = []
    for param in similarity_details["parameters"]:
        status = ""
        if param["match"] is True:
            status = "✅ Совпадает"
        elif param["match"] is False:
            status = "❌ Не совпадает"
        else:
            status = "➖ Не сравнивается"

        comparison_data.append({
            "Параметр": param["parameter"],
            "Товар слева": param["left_value"],
            "Товар справа": param["right_value"],
            "Статус": status,
            "Баллы": f"{param['score']:+.0f}"
        })

    comparison_df = pd.DataFrame(comparison_data)
    st.dataframe(comparison_df, width='stretch', hide_index=True)

    # Итоговый скор схожести
    st.subheader("🎯 Итоговый скор схожести")

    col_score1, col_score2, col_score3 = st.columns(3)

    with col_score1:
        st.metric("Сырой скор", f"{similarity_details['total_score']:.1f}")

    with col_score2:
        st.metric("Скор с штрафами", f"{similarity_details['final_score']:.1f}")

    with col_score3:
        # Определяем уровень схожести
        final_score = similarity_details['final_score']
        if final_score >= 400:
            level = "Высокая"
            color = "🟢"
        elif final_score >= 250:
            level = "Средняя"
            color = "🟡"
        else:
            level = "Низкая"
            color = "🔴"
        st.metric("Уровень схожести", f"{color} {level}")