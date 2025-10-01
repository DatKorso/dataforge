from __future__ import annotations

from typing import TypedDict, Any, Sequence

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
    margin_percentage = (((oz_price/(1+VAT)
                          - (oz_price*((Commission+Acquiring+Advertising)/100)) / (1+VAT))
                          / ExchangeRate)
                         - cost_price_usd) / cost_price_usd * 100

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

    # Шаг 2-3: Сумма комиссий с коэффициентом (1 + vat)
    total_fees_percent = commission_percent + acquiring_percent + advertising_percent
    fees_amount = oz_price * (total_fees_percent / 100)
    fees_adjusted = fees_amount / (1 + vat_percent / 100)

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

    # Гарантируем, что у нас есть валидное соединение (убирает предупреждения статического анализатора и
    # предотвращает ошибку "execute" не является известным атрибутом "None")
    assert con is not None, "Failed to obtain a DuckDB connection (con is None)"

    try:
        results: list[CandidateResult] = []
        group_number = 0

        # 0) Проверяем существование таблиц один раз (вне цикла)
        def _table_exists(table: str) -> bool:
            # Используем параметризованный запрос и проверяем, что fetchone() вернул строку.
            res = con.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
                [table],
            ).fetchone()
            if not res or len(res) == 0 or res[0] is None:
                return False
            try:
                return int(res[0]) > 0
            except Exception:
                return False

        pg_exists = _table_exists("punta_google")
        pb_exists = _table_exists("punta_barcodes")
        ppc_exists = _table_exists("punta_products_codes")

        # 1) Собираем все матчинги разом, а затем батчим запрос по товарам
        matches_by_wb: dict[str, Sequence[Any]] = {}
        external_code_by_oz_all: dict[str, str] = {}
        all_oz_skus: list[str] = []
        for wb_sku in wb_skus:
            matches = find_oz_by_wb(wb_sku, limit=None, con=con)
            if not matches:
                matches_by_wb[wb_sku] = []
                continue
            matches_by_wb[wb_sku] = matches
            for m in matches:
                oz = m.get("oz_sku")
                if oz:
                    all_oz_skus.append(str(oz))
                    ext = m.get("punta_external_code_oz")
                    if ext:
                        external_code_by_oz_all.setdefault(str(oz), str(ext))

        if not all_oz_skus:
            return []

        # 2) Единый запрос по всем oz_sku
        placeholders = ",".join(["?"] * len(all_oz_skus))
        punta_prod_join = ""
        punta_prod_select = ""
        if pb_exists and ppc_exists:
            punta_prod_join = (
                "\n                LEFT JOIN punta_barcodes pb ON pb.barcode = p.\"barcode-primary\"\n"
                "                LEFT JOIN punta_products_codes ppc ON ppc.external_code = pb.external_code\n"
            )
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
            {punta_prod_select}
        FROM oz_products p
        LEFT JOIN orders_14d o ON p.oz_vendor_code = o.oz_vendor_code
        {punta_prod_join}
        WHERE p.oz_sku IN ({placeholders})
        """

        df_all = con.execute(query, all_oz_skus).fetch_df()

        if "cost_usd" not in df_all.columns:
            df_all["cost_usd"] = pd.NA

        # В некоторых случаях JOIN'ы (например с punta_barcodes/punta_products_codes)
        # могут создать дублированные строки для одного и того же oz_vendor_code.
        # Это приведёт к дублированию размеров в итоговой выборке. Чтобы избежать
        # этого, оставим только одну строку на oz_vendor_code, предпочтительно
        # сохраняя агрегированные числовые поля (fbo_available, total_orders)
        # — здесь аккуратно агрегируем по сумме/максимуму, затем заменяем df_all.
        try:
            if not df_all.empty and "oz_vendor_code" in df_all.columns:
                # Агрегируем: суммируем остатки и заказы, берём max цены и first cost_usd
                df_agg = (
                    df_all.groupby("oz_vendor_code", as_index=False)
                    .agg(
                        {
                            "oz_sku": lambda s: s.astype(str).dropna().unique()[0] if len(s.dropna().unique()) > 0 else pd.NA,
                            "fbo_available": "sum",
                            "total_orders": "sum",
                            "oz_price": "max",
                            "cost_usd": lambda s: s.dropna().iloc[0] if s.dropna().shape[0] > 0 else pd.NA,
                        }
                    )
                )
                # Переименуем oz_sku обратно к строковому виду и используем агрегированный df
                df_all = df_agg
        except Exception:
            # Если агрегирование по какой-то причине не удалось, оставим оригинальный df_all
            pass

        # 3) Загружаем себестоимости по external_code (единоразово)
        cost_by_external: dict[str, float | None] = {}
        if ppc_exists and external_code_by_oz_all:
            external_codes = sorted(set(external_code_by_oz_all.values()))
            placeholders_ext = ",".join(["?"] * len(external_codes))
            cost_df = con.execute(
                f"SELECT external_code, cost_usd FROM punta_products_codes WHERE external_code IN ({placeholders_ext})",
                external_codes,
            ).fetch_df()
            for _, cost_row in cost_df.iterrows():
                ext_code = str(cost_row["external_code"])
                value = float(cost_row["cost_usd"]) if pd.notna(cost_row["cost_usd"]) else None
                cost_by_external[ext_code] = value

        # 4) Загружаем характеристики из punta_google по wb_sku (без небезопасных f-string)
        pg_map: dict[str, dict[str, str | None]] = {}
        if pg_exists:
            placeholders_wb = ",".join(["?"] * len(wb_skus))
            pg_df = con.execute(
                f"SELECT wb_sku, gender, season, material_short, item_type FROM punta_google WHERE wb_sku IN ({placeholders_wb})",
                wb_skus,
            ).fetch_df()
            for _, r in pg_df.iterrows():
                key = str(r["wb_sku"]) if pd.notna(r["wb_sku"]) else None
                if key is None:
                    continue
                pg_map[key] = {
                    "gender": str(r["gender"]) if pd.notna(r["gender"]) else None,
                    "season": str(r["season"]) if pd.notna(r["season"]) else None,
                    "material_short": str(r["material_short"]) if pd.notna(r["material_short"]) else None,
                    "item_type": str(r["item_type"]) if pd.notna(r["item_type"]) else None,
                }

        # 5) Обрабатываем группы по исходным wb_sku
        for wb_sku in wb_skus:
            matches = matches_by_wb.get(wb_sku) or []
            if not matches:
                continue

            oz_skus_group = [m.get("oz_sku") for m in matches if m.get("oz_sku")]
            if not oz_skus_group:
                continue

            # Фильтруем общий датафрейм по sku группы
            try:
                oz_skus_group_int = {int(str(x)) for x in oz_skus_group}
                df_g = df_all[df_all["oz_sku"].astype(int).isin(oz_skus_group_int)].copy()
            except Exception:
                # На случай неожиданного типа `oz_sku` — используем строковое сравнение
                df_g = df_all[df_all["oz_sku"].astype(str).isin([str(x) for x in oz_skus_group])].copy()

            if df_g.empty:
                continue

            # Сортировка: по заказам, затем по остаткам
            df_g = df_g.sort_values(by=["total_orders", "fbo_available"], ascending=[False, False]).reset_index(drop=True)

            # Фильтрация по min_stock
            df_filtered = df_g[df_g["fbo_available"] >= min_stock].copy()
            if len(df_filtered) < min_candidates:
                continue

            # Ограничение max_candidates
            df_selected = df_filtered.head(max_candidates)

            # Агрегаты по модели (по всем товарам группы)
            model_stock = int(df_g["fbo_available"].sum())
            model_orders = int(df_g["total_orders"].sum())

            # Данные из punta_google для wb_sku
            pg_row = pg_map.get(str(wb_sku), {}) if pg_exists else {}

            # Формируем результаты
            group_number += 1
            for _, row in df_selected.iterrows():
                oz_price = float(row["oz_price"]) if pd.notna(row.get("oz_price")) else None

                # Себестоимость из запроса или по external_code из matching
                cost_usd: float | None
                tmp_cost = row.get("cost_usd")
                if pd.notna(tmp_cost):
                    cost_usd = float(tmp_cost)
                else:
                    ext_code = external_code_by_oz_all.get(str(row["oz_sku"]))
                    cost_usd = cost_by_external.get(ext_code) if ext_code else None

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
                        wb_sku=str(wb_sku),
                        oz_sku=str(row["oz_sku"]) if pd.notna(row["oz_sku"]) else "",
                        oz_vendor_code=str(row["oz_vendor_code"]),
                        gender=(pg_row.get("gender") if pg_row else None),
                        season=(pg_row.get("season") if pg_row else None),
                        material_short=(pg_row.get("material_short") if pg_row else None),
                        item_type=(pg_row.get("item_type") if pg_row else None),
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
