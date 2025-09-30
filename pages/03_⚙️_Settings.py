from __future__ import annotations

import time

import streamlit as st
from dataforge.db import check_connection, get_connection
from dataforge.schema import init_schema, rebuild_indexes, rebuild_punta_products_codes
from dataforge.secrets import load_secrets, save_secrets
from dataforge.ui import setup_page

setup_page(title="DataForge", icon="🛠️")
st.title("⚙️ Settings")

# --- MotherDuck configuration ---
st.subheader("MotherDuck")
st.caption("Укажите MD токен и название базы данных.")

existing = load_secrets()

def _secret_from_streamlit(key: str) -> str | None:
    try:
        # st.secrets behaves like a dict; use indexing to avoid relying on .get
        return st.secrets[key]  # type: ignore[index]
    except Exception:
        return None

# Никогда не подставляем сохранённый токен в инпут, чтобы его нельзя было увидеть
# (даже в скрытом поле). Будем использовать сохранённый токен только как
# невидимый источник по умолчанию при действиях.
_stored_md_token = (
    st.session_state.get("md_token")
    or _secret_from_streamlit("md_token")
    or existing.get("md_token", "")
)
default_db = (
    st.session_state.get("md_database")
    or _secret_from_streamlit("md_database")
    or existing.get("md_database", "")
)

md_token_input = st.text_input(
    "MD токен",
    value="",
    type="password",
    placeholder="Введите токен (значение не отображается)",
)
effective_md_token = md_token_input or _stored_md_token
md_database = st.text_input("MD база данных", value=default_db, placeholder="my_database")

cols = st.columns(2)
with cols[0]:
    if st.button("Сохранить в secrets.toml"):
        # Persist MD creds and brand filter in secrets for convenience
        save_secrets(
            {
                # Пустое значение не перезаписывает токен (save_secrets игнорирует None)
                "md_token": (md_token_input or None),
                "md_database": md_database,
                "brand_whitelist": st.session_state.get("brand_whitelist", ""),
            }
        )
        if md_token_input:
            st.session_state["md_token"] = md_token_input
        st.session_state["md_database"] = md_database
        st.success("Секреты сохранены в .streamlit/secrets.toml")

with cols[1]:
    if st.button("Проверить подключение"):
        with st.spinner("Проверка подключения к MotherDuck..."):
            ok, msg = check_connection(
                md_token=(effective_md_token or None),
                md_database=(md_database or None),
            )
        if ok:
            st.success(msg)
        else:
            st.error(msg)

st.divider()
st.subheader("Схема БД")
st.caption("Схема захардкожена в коде проекта для простоты сопровождения.")

cols2 = st.columns(2)
with cols2[0]:
    if st.button("Инициализировать схему БД"):
        with st.spinner("Создание таблиц (если отсутствуют)..."):
            msgs = init_schema(
                md_token=(effective_md_token or None),
                md_database=(md_database or None),
            )
        st.success("Выполнено:")
        for m in msgs:
            st.write(f"• {m}")

st.divider()
st.subheader("Фильтр брендов")
st.caption(
    "Укажите бренды, которые вы ведёте. При импорте будут загружены только строки с этими брендами. "
    "Список через точку с запятой, например: Nike; Puma; Adidas"
)

# Read persisted value or session state
_brand_default = (
    st.session_state.get("brand_whitelist")
    or _secret_from_streamlit("brand_whitelist")
    or existing.get("brand_whitelist", "")
)
brand_text = st.text_input("Список брендов", value=_brand_default)
st.session_state["brand_whitelist"] = brand_text

with cols2[1]:
    if st.button("Перестроить индексы"):
        with st.spinner("Перестройка индексов для всех известных таблиц..."):
            msgs = rebuild_indexes(
                md_token=(effective_md_token or None),
                md_database=(md_database or None),
            )
        st.success("Выполнено:")
        for m in msgs:
            st.write(f"• {m}")

st.divider()
st.subheader("Настройки маржинальности")
st.caption(
    "Параметры для расчета маржи в подборе кандидатов РК. "
    "Используются для расчета чистой прибыли после всех комиссий и НДС."
)

# Загрузить текущие значения
margin_defaults = {
    "commission_percent": 36.0,
    "acquiring_percent": 0.0,
    "advertising_percent": 3.0,
    "vat_percent": 20.0,
    "exchange_rate": 90.0,
}

margin_cols = st.columns(3)
with margin_cols[0]:
    commission = st.number_input(
        "Комиссия Ozon (%)",
        min_value=0.0,
        max_value=100.0,
        value=float(
            st.session_state.get("commission_percent")
            or _secret_from_streamlit("commission_percent")
            or existing.get("commission_percent", margin_defaults["commission_percent"])
        ),
        step=0.1,
        help="Процент комиссии маркетплейса Ozon",
    )
    acquiring = st.number_input(
        "Эквайринг (%)",
        min_value=0.0,
        max_value=100.0,
        value=float(
            st.session_state.get("acquiring_percent")
            or _secret_from_streamlit("acquiring_percent")
            or existing.get("acquiring_percent", margin_defaults["acquiring_percent"])
        ),
        step=0.1,
        help="Процент эквайринга (обработка платежей)",
    )

with margin_cols[1]:
    advertising = st.number_input(
        "Реклама (%)",
        min_value=0.0,
        max_value=100.0,
        value=float(
            st.session_state.get("advertising_percent")
            or _secret_from_streamlit("advertising_percent")
            or existing.get("advertising_percent", margin_defaults["advertising_percent"])
        ),
        step=0.1,
        help="Процент затрат на рекламу",
    )
    vat = st.number_input(
        "НДС (%)",
        min_value=0.0,
        max_value=100.0,
        value=float(
            st.session_state.get("vat_percent")
            or _secret_from_streamlit("vat_percent")
            or existing.get("vat_percent", margin_defaults["vat_percent"])
        ),
        step=0.1,
        help="Налог на добавленную стоимость",
    )

with margin_cols[2]:
    exchange_rate = st.number_input(
        "Курс USD/RUB",
        min_value=1.0,
        max_value=200.0,
        value=float(
            st.session_state.get("exchange_rate")
            or _secret_from_streamlit("exchange_rate")
            or existing.get("exchange_rate", margin_defaults["exchange_rate"])
        ),
        step=0.1,
        help="Курс конвертации доллара к рублю",
    )

if st.button("Сохранить настройки маржи"):
    save_secrets(
        {
            "commission_percent": commission,
            "acquiring_percent": acquiring,
            "advertising_percent": advertising,
            "vat_percent": vat,
            "exchange_rate": exchange_rate,
        }
    )
    st.session_state.update(
        {
            "commission_percent": commission,
            "acquiring_percent": acquiring,
            "advertising_percent": advertising,
            "vat_percent": vat,
            "exchange_rate": exchange_rate,
        }
    )
    st.success("Настройки маржинальности сохранены в .streamlit/secrets.toml")

st.divider()
st.subheader("Punta")
st.caption("Ручное обновление нормализованной связки external_code ↔ продукты Punta.")

if st.button("Обновить связку Punta"):
    try:
        t0 = time.perf_counter()
        with st.spinner("Пересборка punta_products_codes..."):
            msgs = rebuild_punta_products_codes(
                md_token=(effective_md_token or None),
                md_database=(md_database or None),
            )
        dt = time.perf_counter() - t0

        # Подсчёт размера таблицы (строк и уникальных external_code)
        rows = codes = None
        try:
            with get_connection(
                md_token=(effective_md_token or None),
                md_database=(md_database or None),
            ) as con:
                stats = con.execute(
                    "SELECT COUNT(*) AS rows, COUNT(DISTINCT external_code) AS codes FROM punta_products_codes"
                ).fetch_df()
                if not stats.empty:
                    rows = int(stats.loc[0, "rows"]) if stats.loc[0, "rows"] is not None else None
                    codes = int(stats.loc[0, "codes"]) if stats.loc[0, "codes"] is not None else None
        except Exception:
            pass

        st.success(
            f"Готово за {dt:.2f} c. "
            + (f"Строк: {rows}. Уникальных external_code: {codes}." if rows is not None and codes is not None else "")
        )
        if rows and rows > 1_000_000:
            st.warning("Размер таблицы >1 млн строк — проверьте нагрузку и индексы.")
        if msgs:
            with st.expander("Логи пересборки"):
                for m in msgs:
                    st.write(f"• {m}")
    except Exception as exc:  # noqa: BLE001
        st.exception(exc)
