from __future__ import annotations

from typing import TypedDict

import duckdb
import pandas as pd
from dataforge.db import get_connection
from dataforge.matching import find_oz_by_wb


def calculate_margin_percentage(
    oz_price: float,
    cost_usd: float,
    commission_percent: float,
    acquiring_percent: float,
    advertising_percent: float,
    vat_percent: float,
    exchange_rate: float,
) -> float:
    """Расчет процента маржинальности по формуле.

    Формула:
    margin_percentage = (((oz_price/(1+VAT) -
                          (oz_price*((Commission+Acquiring+Advertising)/100))/1.2) /
                          ExchangeRate) - cost_price_usd) / cost_price_usd * 100

    Args:
        oz_price: Цена Ozon в рублях (current_price)
        cost_usd: Себестоимость в USD
        commission_percent: Комиссия Ozon (%)
        acquiring_percent: Эквайринг (%)
        advertising_percent: Реклама (%)
        vat_percent: НДС (%)
        exchange_rate: Курс USD/RUB

    Returns:
        Процент маржинальности
    """
    if cost_usd <= 0 or oz_price <= 0 or exchange_rate <= 0:
        return 0.0

    # Шаг 1: Цена без НДС
    price_after_vat = oz_price / (1 + vat_percent / 100)

    # Шаг 2-3: Сумма комиссий с коэффициентом 1.2
    total_fees_percent = commission_percent + acquiring_percent + advertising_percent
    fees_amount = oz_price * (total_fees_percent / 100)
    fees_adjusted = fees_amount / 1.2

    # Шаг 4: Чистая выручка в рублях
    net_price_rub = price_after_vat - fees_adjusted

    # Шаг 5: Конвертация в USD
    net_price_usd = net_price_rub / exchange_rate

    # Шаг 6-7: Маржа и процент
    margin_usd = net_price_usd - cost_usd
    return (margin_usd / cost_usd) * 100


class CandidateResult(TypedDict):
    """Результат подбора кандидата для рекламной кампании.

    Размер = товар Ozon (1 oz_vendor_code = 1 размер/товар).
    Модель = группа товаров Ozon, соответствующих одному wb_sku.
    """
    group_number: int       # Номер группы (1 wb_sku = 1 группа)
    wb_sku: str            # Артикул WB
    oz_sku: str            # Артикул OZ
    oz_vendor_code: str    # Артикул поставщика OZ (размер)
    gender: str | None     # Пол из punta_google
    season: str | None     # Сезон из punta_google
    material_short: str | None  # Материал из punta_google
    item_type: str | None  # Категория из punta_google
    size_stock: int        # Остаток размера (fbo_available)
    model_stock: int       # Остаток модели (сумма всех fbo_available для wb_sku)
    size_orders: int       # Заказы размера за 14 дней
    model_orders: int      # Заказы модели за 14 дней (сумма всех заказов для wb_sku)
    oz_price: float | None  # Цена Ozon (current_price)
    cost_usd: float | None  # Себестоимость USD из punta_products
    margin_percent: float | None  # Процент маржинальности


def select_campaign_candidates(
    wb_skus: list[str],
    min_stock: int,
    min_candidates: int,
    max_candidates: int,
    *,
    commission_percent: float = 36.0,
    acquiring_percent: float = 0.0,
    advertising_percent: float = 3.0,
    vat_percent: float = 20.0,
    exchange_rate: float = 90.0,
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

            # Подготовим карту external_code, если matcher его вернул
            external_code_by_oz: dict[str, str] = {}
            for match in matches:
                oz_sku_match = match.get("oz_sku")
                external_code = match.get("punta_external_code_oz")
                if oz_sku_match and external_code:
                    key = str(oz_sku_match)
                    external_code_by_oz.setdefault(key, str(external_code))

            # 2. Получаем данные о товарах: остатки + заказы + цена + себестоимость + punta_google
            # JOIN с punta_google по wb_sku для получения характеристик
            # JOIN с punta_products_codes по "barcode-primary" → punta_barcodes → external_code для получения себестоимости
            placeholders = ",".join(["?"] * len(oz_skus))

            # Проверяем существование таблиц punta_google, punta_barcodes и punta_products_codes
            pg_exists = con.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'punta_google'"
            ).fetchone()[0] > 0

            pb_exists = con.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'punta_barcodes'"
            ).fetchone()[0] > 0

            ppc_exists = con.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'punta_products_codes'"
            ).fetchone()[0] > 0

            punta_join = ""
            punta_select = ""
            if pg_exists:
                # Используем литерал вместо параметра для wb_sku в JOIN
                punta_join = f"LEFT JOIN punta_google pg ON pg.wb_sku = '{wb_sku}'"
                punta_select = """
                    , pg.gender
                    , pg.season
                    , pg.material_short
                    , pg.item_type
                """

            # JOIN с punta_products_codes для получения себестоимости через "barcode-primary" → punta_barcodes → external_code
            punta_prod_join = ""
            punta_prod_select = ""
            if pb_exists and ppc_exists:
                punta_prod_join = """
                LEFT JOIN punta_barcodes pb ON pb.barcode = p."barcode-primary"
                LEFT JOIN punta_products_codes ppc ON ppc.external_code = pb.external_code
                """
                punta_prod_select = ", ppc.cost_usd"

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
                COALESCE(o.total_orders, 0) AS total_orders,
                p.current_price AS oz_price
                {punta_select}
                {punta_prod_select}
            FROM oz_products p
            LEFT JOIN orders_14d o ON p.oz_vendor_code = o.oz_vendor_code
            {punta_join}
            {punta_prod_join}
            WHERE p.oz_sku IN ({placeholders})
            """

            df = con.execute(query, oz_skus).fetch_df()

            if df.empty:
                continue

            # Добавляем себестоимость по external_code, если matcher предоставил данные
            if "cost_usd" not in df.columns:
                df["cost_usd"] = pd.NA

            cost_by_external: dict[str, float | None] = {}
            external_codes = sorted({code for code in external_code_by_oz.values() if code})
            if ppc_exists and external_codes:
                placeholders_ext = ",".join(["?"] * len(external_codes))
                cost_df = con.execute(
                    f"SELECT external_code, cost_usd FROM punta_products_codes WHERE external_code IN ({placeholders_ext})",
                    external_codes,
                ).fetch_df()
                for _, cost_row in cost_df.iterrows():
                    ext_code = str(cost_row["external_code"])
                    value = float(cost_row["cost_usd"]) if pd.notna(cost_row["cost_usd"]) else None
                    cost_by_external[ext_code] = value

            if external_code_by_oz:
                oz_sku_str = df["oz_sku"].astype(str)
                matched_codes = oz_sku_str.map(external_code_by_oz)
                if cost_by_external:
                    cost_from_match = matched_codes.map(cost_by_external)
                    df["cost_usd"] = cost_from_match.combine_first(df["cost_usd"])

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

            # 5. Расчёт агрегатов на уровне модели (для всех товаров группы, не только выбранных)
            model_stock = int(df["fbo_available"].sum())
            model_orders = int(df["total_orders"].sum())

            # 6. Формируем результаты с расчётом маржинальности
            group_number += 1
            for _, row in df_selected.iterrows():
                # Извлекаем цену и себестоимость
                oz_price = float(row["oz_price"]) if "oz_price" in row and pd.notna(row["oz_price"]) else None
                cost_usd = float(row["cost_usd"]) if "cost_usd" in row and pd.notna(row["cost_usd"]) else None

                # Рассчитываем маржу
                margin_percent = None
                if oz_price is not None and cost_usd is not None and oz_price > 0 and cost_usd > 0:
                    margin_percent = calculate_margin_percentage(
                        oz_price=oz_price,
                        cost_usd=cost_usd,
                        commission_percent=commission_percent,
                        acquiring_percent=acquiring_percent,
                        advertising_percent=advertising_percent,
                        vat_percent=vat_percent,
                        exchange_rate=exchange_rate,
                    )

                results.append(
                    CandidateResult(
                        group_number=group_number,
                        wb_sku=wb_sku,
                        oz_sku=str(row["oz_sku"]) if pd.notna(row["oz_sku"]) else "",
                        oz_vendor_code=str(row["oz_vendor_code"]),
                        gender=str(row["gender"]) if "gender" in row and pd.notna(row["gender"]) else None,
                        season=str(row["season"]) if "season" in row and pd.notna(row["season"]) else None,
                        material_short=str(row["material_short"]) if "material_short" in row and pd.notna(row["material_short"]) else None,
                        item_type=str(row["item_type"]) if "item_type" in row and pd.notna(row["item_type"]) else None,
                        size_stock=int(row["fbo_available"]),
                        model_stock=model_stock,
                        size_orders=int(row["total_orders"]),
                        model_orders=model_orders,
                        oz_price=oz_price,
                        cost_usd=cost_usd,
                        margin_percent=margin_percent,
                    )
                )

        return results

    finally:
        if own_con and con is not None:
            con.close()