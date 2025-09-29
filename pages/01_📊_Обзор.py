from __future__ import annotations

from collections.abc import Generator, Iterable
from typing import Any

import pandas as pd
import streamlit as st
from dataforge.db import get_connection
from dataforge.ui import setup_page

setup_page(title="DataForge", icon="🛠️")

st.title("📊 Обзор MotherDuck")
st.caption(
    "Краткая сводка по использованию хранилища MotherDuck в текущей базе данных."
)


def _sget(key: str) -> str | None:
    try:
        return st.secrets[key]  # type: ignore[index]
    except Exception:
        return None


md_token = st.session_state.get("md_token") or _sget("md_token")
md_database = st.session_state.get("md_database") or _sget("md_database")

if not md_token:
    st.warning("MD токен не найден. Укажите его на странице Настройки.")
    st.stop()


@st.cache_data(ttl=60)
def load_database_size(
    *, md_token: str | None, md_database: str | None
) -> pd.DataFrame:
    with get_connection(md_token=md_token, md_database=md_database) as con:
        return con.execute("PRAGMA database_size;").fetch_df()


def friendly_label(key: str) -> str:
    labels: dict[str, str] = {
        "database_name": "База данных",
        "database_size": "Общий размер",
        "storage_bytes": "Объём хранения",
        "total_blocks": "Всего блоков",
        "free_blocks": "Свободные блоки",
        "used_blocks": "Используемые блоки",
        "block_size": "Размер блока",
        "wal_size": "Размер WAL",
        "memory_usage": "Использование памяти",
        "freelist": "Свободный список",
        "schema_name": "Схема",
        "total_entries": "Всего записей",
        "compression_ratio": "Коэффициент сжатия",
        "timestamp": "Метка времени",
    }
    return labels.get(key, key.replace("_", " ").capitalize())


def humanize_bytes(value: float) -> str:
    units = ["Б", "КБ", "МБ", "ГБ", "ТБ", "ПБ"]
    val = float(value)
    for unit in units:
        if abs(val) < 1024 or unit == units[-1]:
            return f"{val:.0f} {unit}" if unit == "Б" else f"{val:.1f} {unit}"
        val /= 1024
    return f"{val:.1f} ПБ"


def format_value(key: str, value: Any) -> str:
    if value is None:
        return "—"

    if isinstance(value, int | float):
        if key.endswith("_ratio"):
            return f"{float(value):.2f}"

        if any(key.endswith(suffix) for suffix in ("_size", "_bytes", "_usage")):
            return humanize_bytes(float(value))

        if isinstance(value, int) or float(value).is_integer():
            return f"{int(value):,}".replace(",", " ")
        return f"{float(value):,.2f}".replace(",", " ")

    return str(value)


def chunked(values: Iterable[dict[str, str]], size: int) -> Generator[list[dict[str, str]], None, None]:
    bucket: list[dict[str, str]] = []
    for item in values:
        bucket.append(item)
        if len(bucket) == size:
            yield bucket
            bucket = []
    if bucket:
        yield bucket


try:
    stats_df = load_database_size(md_token=md_token, md_database=md_database)
except Exception as exc:  # noqa: BLE001
    st.error(f"Не удалось получить статистику MotherDuck: {exc}")
    st.stop()

if stats_df.empty:
    st.info("Запрос PRAGMA database_size не вернул данных для текущей базы.")
    st.stop()

record = stats_df.iloc[0].to_dict()

metrics = [
    {
        "label": friendly_label(key),
        "value": format_value(key, value),
    }
    for key, value in record.items()
]

st.subheader("Основные показатели")
for group in chunked(metrics, 3):
    cols = st.columns(len(group))
    for col, metric in zip(cols, group, strict=False):
        col.metric(metric["label"], metric["value"])

formatted_rows = [
    {
        "Параметр": friendly_label(key),
        "Значение": format_value(key, value),
        "Сырой параметр": key,
        "Сырое значение": value,
    }
    for key, value in record.items()
]

st.subheader("Детали PRAGMA database_size")
st.dataframe(
    pd.DataFrame(formatted_rows),
    width="stretch",
    hide_index=True,
)
