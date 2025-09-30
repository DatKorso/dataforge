from __future__ import annotations

from typing import TypedDict

import duckdb
import pandas as pd
from dataforge.db import get_connection
from dataforge.matching import find_oz_by_wb


class CandidateResult(TypedDict):
    """Результат подбора кандидата для рекламной кампании.

    Размер = товар Ozon (1 oz_vendor_code = 1 размер/товар).
    Модель = группа товаров Ozon, соответствующих одному wb_sku.
    """
    group_number: int       # Номер группы (1 wb_sku = 1 группа)
    wb_sku: str            # Артикул WB
    oz_sku: str            # Артикул OZ
    oz_vendor_code: str    # Артикул поставщика OZ (размер)
    size_stock: int        # Остаток размера (fbo_available)
    model_stock: int       # Остаток модели (сумма всех fbo_available для wb_sku)
    size_orders: int       # Заказы размера за 14 дней
    model_orders: int      # Заказы модели за 14 дней (сумма всех заказов для wb_sku)


def select_campaign_candidates(
    wb_skus: list[str],
    min_stock: int,
    min_candidates: int,
    max_candidates: int,
    *,
    con: duckdb.DuckDBPyConnection | None = None,
    md_token: str | None = None,
    md_database: str | None = None,
) -> list[CandidateResult]:
    """Подбор кандидатов для рекламных кампаний Ozon на основе артикулов WB.

    Алгоритм:
    1. Для каждого wb_sku находим соответствующие товары Ozon через matching
    2. Получаем остатки (fbo_available) и заказы за последние 14 дней
    3. Сортируем товары по заказам (DESC), затем по остаткам (DESC)
    4. Фильтруем по min_stock и выбираем от min_candidates до max_candidates
    5. Если найдено < min_candidates, группа не включается в результат

    Args:
        wb_skus: Список артикулов WB для поиска кандидатов
        min_stock: Минимальный остаток для включения товара
        min_candidates: Минимальное количество кандидатов в группе (иначе группа исключается)
        max_candidates: Максимальное количество кандидатов на группу
        con: Существующее соединение DuckDB (опционально)
        md_token: MotherDuck токен (если con не указан)
        md_database: MotherDuck база данных (если con не указан)

    Returns:
        Список CandidateResult с подобранными кандидатами
    """
    if not wb_skus:
        return []

    if min_candidates > max_candidates:
        raise ValueError("min_candidates не может быть больше max_candidates")

    # Обеспечиваем соединение
    own_con = con is None
    if own_con:
        con = get_connection(md_token=md_token, md_database=md_database).__enter__()

    try:
        results: list[CandidateResult] = []
        group_number = 0

        for wb_sku in wb_skus:
            # 1. Получаем кандидатов OZ через matching
            matches = find_oz_by_wb(wb_sku, limit=None, con=con)
            if not matches:
                continue

            # Собираем oz_sku для запроса (oz_sku = BIGINT артикул Ozon)
            oz_skus = [m["oz_sku"] for m in matches if m.get("oz_sku")]
            if not oz_skus:
                continue

            # 2. Получаем данные о товарах: остатки + заказы за 14 дней
            # Соединяем по oz_sku, чтобы получить oz_vendor_code и остатки
            placeholders = ",".join(["?"] * len(oz_skus))
            query = f"""
            WITH orders_14d AS (
                SELECT
                    oz_vendor_code,
                    COALESCE(SUM(quantity), 0) AS total_orders
                FROM oz_orders
                WHERE processing_date >= CURRENT_DATE - INTERVAL 14 DAYS
                GROUP BY oz_vendor_code
            )
            SELECT
                p.oz_sku,
                p.oz_vendor_code,
                COALESCE(p.fbo_available, 0) AS fbo_available,
                COALESCE(o.total_orders, 0) AS total_orders
            FROM oz_products p
            LEFT JOIN orders_14d o ON p.oz_vendor_code = o.oz_vendor_code
            WHERE p.oz_sku IN ({placeholders})
            """

            df = con.execute(query, oz_skus).fetch_df()

            if df.empty:
                continue

            # 3. Сортировка: сначала по заказам (DESC), затем по остаткам (DESC)
            df = df.sort_values(
                by=["total_orders", "fbo_available"],
                ascending=[False, False]
            ).reset_index(drop=True)

            # 4. Фильтрация по min_stock
            df_filtered = df[df["fbo_available"] >= min_stock].copy()

            # Проверка min_candidates
            if len(df_filtered) < min_candidates:
                continue  # Пропускаем группу

            # Ограничение max_candidates
            df_selected = df_filtered.head(max_candidates)

            # 5. Расчет агрегатов на уровне модели (для всех товаров группы, не только выбранных)
            model_stock = int(df["fbo_available"].sum())
            model_orders = int(df["total_orders"].sum())

            # 6. Формируем результаты
            group_number += 1
            for _, row in df_selected.iterrows():
                results.append(
                    CandidateResult(
                        group_number=group_number,
                        wb_sku=wb_sku,
                        oz_sku=str(row["oz_sku"]) if pd.notna(row["oz_sku"]) else "",
                        oz_vendor_code=str(row["oz_vendor_code"]),
                        size_stock=int(row["fbo_available"]),
                        model_stock=model_stock,
                        size_orders=int(row["total_orders"]),
                        model_orders=model_orders,
                    )
                )

        return results

    finally:
        if own_con and con is not None:
            con.close()