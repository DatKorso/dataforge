from __future__ import annotations

from typing import Iterable, List, Optional, TypedDict

import pandas as pd
import duckdb

from dataforge.db import get_connection


class Match(TypedDict):
    oz_sku: Optional[str]
    wb_sku: Optional[str]
    barcode_hit: str
    matched_by: str  # 'primary↔primary' | 'primary↔any' | 'any↔primary' | 'any↔any'
    match_score: int
    confidence_note: Optional[str]


def _normalize_barcodes(barcodes: Iterable[str]) -> List[str]:
    """Strip and drop empty values; keep as strings.

    Parameters
    - barcodes: iterable of input strings

    Returns
    - list of cleaned strings
    """
    out: List[str] = []
    for b in barcodes:
        if b is None:
            continue
        s = str(b).strip()
        if s:
            out.append(s)
    return out


def _ensure_connection(
    con: Optional[duckdb.DuckDBPyConnection],
    *,
    md_token: Optional[str] = None,
    md_database: Optional[str] = None,
) -> duckdb.DuckDBPyConnection:
    return con or get_connection(md_token=md_token, md_database=md_database)


def _table_exists(con: duckdb.DuckDBPyConnection, table_name: str) -> bool:
    """Check whether a table exists in the current DuckDB connection."""
    try:
        q = "SELECT 1 FROM information_schema.tables WHERE table_name = ? LIMIT 1"
        res = con.execute(q, [table_name]).fetchone()
        return res is not None
    except Exception:
        return False


def _matches_for_oz_skus(
    oz_skus: List[str],
    limit_per_input: Optional[int] = None,
    *,
    con: Optional[duckdb.DuckDBPyConnection] = None,
    md_token: Optional[str] = None,
    md_database: Optional[str] = None,
) -> pd.DataFrame:
    """Найти WB соответствия для набора OZ SKU. Возвращает детализированный DataFrame.

    Колонки результата включают ключевые поля обеих сторон и атрибуты совпадения.
    """
    if not oz_skus:
        return pd.DataFrame()

    local_con = _ensure_connection(con, md_token=md_token, md_database=md_database)

    # Регистрируем входные значения как таблицу inputs(oz_sku)
    df_inp = pd.DataFrame({"oz_sku": oz_skus})
    local_con.register("inputs", df_inp)

    punta_enabled = _table_exists(local_con, "punta_barcodes") and _table_exists(local_con, "punta_products_codes")

    punta_cte = r"""
    punta_map AS (
        SELECT pb.barcode,
               pb.external_code,
               ppc.collection
        FROM punta_barcodes pb
        LEFT JOIN punta_products_codes ppc ON ppc.external_code = pb.external_code
    )
    """ if punta_enabled else ""

    punta_select = r"""
               , pm_oz.collection AS punta_collection_oz
               , pm_oz.external_code AS punta_external_code_oz
               , pm_wb.collection AS punta_collection_wb
               , pm_wb.external_code AS punta_external_code_wb
               , (pm_oz.external_code = pm_wb.external_code) AS punta_external_equal
    """ if punta_enabled else ""

    punta_joins = r"""
        LEFT JOIN punta_map pm_oz ON pm_oz.barcode = o.oz_primary_barcode
        LEFT JOIN punta_map pm_wb ON pm_wb.barcode = w.wb_primary_barcode
    """ if punta_enabled else ""

    sql_head = r"""
    WITH inp AS (
        SELECT CAST(oz_sku AS UBIGINT) AS oz_sku FROM inputs
    ),
    -- Ozon: сопоставляем oz_sku → oz_vendor_code и разворачиваем barcodes из oz_products_full
    oz_base AS (
        SELECT p.oz_sku,
               p.oz_vendor_code,
               CAST(p."barcode-primary" AS VARCHAR) AS oz_barcode_primary
        FROM oz_products AS p
        JOIN inp ON inp.oz_sku = p.oz_sku
    ),
    oz_full_barcodes AS (
        SELECT b.oz_sku,
               b.oz_vendor_code,
               json_extract_string(j.value, '$') AS barcode,
               CASE WHEN json_extract_string(j.value, '$') = f.primary_barcode THEN TRUE ELSE FALSE END AS is_primary,
               f.primary_barcode AS oz_primary_barcode,
               f.russian_size AS oz_russian_size,
               f.product_name AS oz_product_name,
               f.brand AS oz_brand,
               f.color AS oz_color
        FROM oz_base b
        LEFT JOIN oz_products_full f ON f.oz_vendor_code = b.oz_vendor_code
        , json_each(COALESCE(f.barcodes, '[]')) AS j
    ),
    oz_primary_extra AS (
        -- Добавляем первичный штрихкод из oz_products, если он отсутствует в списке oz_products_full.barcodes
        SELECT b.oz_sku,
               b.oz_vendor_code,
               b.oz_barcode_primary AS barcode,
               TRUE AS is_primary,
               b.oz_barcode_primary AS oz_primary_barcode,
               NULL::VARCHAR AS oz_russian_size,
               NULL::VARCHAR AS oz_product_name,
               NULL::VARCHAR AS oz_brand,
               NULL::VARCHAR AS oz_color
        FROM oz_base b
        LEFT JOIN oz_products_full f ON f.oz_vendor_code = b.oz_vendor_code
        WHERE b.oz_barcode_primary IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM json_each(COALESCE(f.barcodes, '[]')) AS j
              WHERE json_extract_string(j.value, '$') = b.oz_barcode_primary
          )
    ),
    oz_barcodes AS (
        SELECT DISTINCT oz_sku, oz_vendor_code, barcode, is_primary,
                        oz_primary_barcode, oz_russian_size, oz_product_name, oz_brand, oz_color
        FROM (
            SELECT * FROM oz_full_barcodes
            UNION ALL
            SELECT * FROM oz_primary_extra
        )
        WHERE barcode IS NOT NULL
    ),
    -- WB: разворачиваем все штрихкоды
    wb_barcodes AS (
        SELECT wp.wb_sku,
               json_extract_string(j.value, '$') AS barcode,
               CASE WHEN json_extract_string(j.value, '$') = wp.primary_barcode THEN TRUE ELSE FALSE END AS is_primary,
               wp.size AS wb_size,
               wp.wb_article AS wb_article,
               wp.brand AS wb_brand,
               wp.color AS wb_color,
               wp.primary_barcode AS wb_primary_barcode
        FROM wb_products AS wp,
             json_each(COALESCE(wp.barcodes, '[]')) AS j
    )
    """

    joined_sql = r"""
    ,
    joined AS (
        SELECT o.oz_sku,
               o.oz_vendor_code,
               w.wb_sku,
               o.barcode AS barcode_hit,
               o.is_primary AS oz_is_primary_hit,
               w.is_primary AS wb_is_primary_hit,
               o.oz_primary_barcode,
               o.oz_russian_size,
               o.oz_product_name,
               o.oz_brand,
               o.oz_color,
               w.wb_primary_barcode,
               w.wb_size,
               w.wb_article,
               w.wb_brand,
               w.wb_color,
               CASE
                   WHEN o.is_primary AND w.is_primary THEN 'primary↔primary'
                   WHEN o.is_primary AND NOT w.is_primary THEN 'primary↔any'
                   WHEN NOT o.is_primary AND w.is_primary THEN 'any↔primary'
                   ELSE 'any↔any'
               END AS matched_by,
               CASE
                   WHEN o.is_primary AND w.is_primary THEN 100
                   WHEN o.is_primary OR  w.is_primary THEN 80
                   ELSE 60
               END AS match_score
        FROM oz_barcodes AS o
        JOIN wb_barcodes AS w
          ON w.barcode = o.barcode
    ),
    ranked AS (
        SELECT j.*, ROW_NUMBER() OVER (PARTITION BY j.oz_sku ORDER BY j.match_score DESC, j.wb_sku) AS rn
        FROM joined j
    )
    SELECT r.*
    FROM ranked r
    WHERE (? IS NULL OR r.rn <= ?)
    ORDER BY r.oz_sku, r.match_score DESC, r.wb_sku
    """

    if punta_enabled:
        sql_mid = ",\n    " + punta_cte + "\n"
        joined_enrich = r"""
               , pm_oz.collection AS punta_collection_oz
               , pm_oz.external_code AS punta_external_code_oz
               , pm_wb.collection AS punta_collection_wb
               , pm_wb.external_code AS punta_external_code_wb
               , (pm_oz.external_code = pm_wb.external_code) AS punta_external_equal
        """
        joined_sql = joined_sql.replace(
            "FROM oz_barcodes AS o",
            joined_enrich + "        FROM oz_barcodes AS o",
        )
        joined_sql = joined_sql.replace(
            "ON w.barcode = o.barcode",
            "ON w.barcode = o.barcode\n          " + punta_joins,
        )
        sql = sql_head + sql_mid + joined_sql
    else:
        sql = sql_head + joined_sql

    if limit_per_input is None or int(limit_per_input) <= 0:
        params = [None, 0]
    else:
        params = [int(limit_per_input), int(limit_per_input)]
    df = local_con.execute(sql, params).fetch_df()
    return df


def _matches_for_wb_skus(
    wb_skus: List[str],
    limit_per_input: Optional[int] = None,
    *,
    con: Optional[duckdb.DuckDBPyConnection] = None,
    md_token: Optional[str] = None,
    md_database: Optional[str] = None,
) -> pd.DataFrame:
    if not wb_skus:
        return pd.DataFrame()
    local_con = _ensure_connection(con, md_token=md_token, md_database=md_database)
    df_inp = pd.DataFrame({"wb_sku": wb_skus})
    local_con.register("inputs", df_inp)

    punta_enabled = _table_exists(local_con, "punta_barcodes") and _table_exists(local_con, "punta_products_codes")

    punta_cte = r"""
    punta_map AS (
        SELECT pb.barcode,
               pb.external_code,
               ppc.collection
        FROM punta_barcodes pb
        LEFT JOIN punta_products_codes ppc ON ppc.external_code = pb.external_code
    )
    """ if punta_enabled else ""

    punta_select = r"""
               , pm_oz.collection AS punta_collection_oz
               , pm_oz.external_code AS punta_external_code_oz
               , pm_wb.collection AS punta_collection_wb
               , pm_wb.external_code AS punta_external_code_wb
               , (pm_oz.external_code = pm_wb.external_code) AS punta_external_equal
    """ if punta_enabled else ""

    punta_joins = r"""
        LEFT JOIN punta_map pm_oz ON pm_oz.barcode = o.oz_primary_barcode
        LEFT JOIN punta_map pm_wb ON pm_wb.barcode = w.wb_primary_barcode
    """ if punta_enabled else ""

    sql_head = r"""
    WITH inp AS (
        SELECT CAST(wb_sku AS UBIGINT) AS wb_sku FROM inputs
    ),
    wb_barcodes AS (
        SELECT wp.wb_sku,
               json_extract_string(j.value, '$') AS barcode,
               CASE WHEN json_extract_string(j.value, '$') = wp.primary_barcode THEN TRUE ELSE FALSE END AS is_primary,
               wp.size AS wb_size,
               wp.wb_article AS wb_article,
               wp.brand AS wb_brand,
               wp.color AS wb_color,
               wp.primary_barcode AS wb_primary_barcode
        FROM wb_products AS wp
        JOIN inp ON inp.wb_sku = wp.wb_sku
        , json_each(COALESCE(wp.barcodes, '[]')) AS j
    ),
    oz_full AS (
        SELECT p.oz_sku,
               p.oz_vendor_code,
               CAST(p."barcode-primary" AS VARCHAR) AS oz_barcode_primary
        FROM oz_products AS p
    ),
    oz_barcodes AS (
        SELECT f.oz_vendor_code,
               o.oz_sku,
               json_extract_string(j.value, '$') AS barcode,
               CASE WHEN json_extract_string(j.value, '$') = f.primary_barcode THEN TRUE ELSE FALSE END AS is_primary,
               f.primary_barcode AS oz_primary_barcode,
               f.russian_size AS oz_russian_size,
               f.product_name AS oz_product_name,
               f.brand AS oz_brand,
               f.color AS oz_color
        FROM oz_products_full AS f
        JOIN oz_full o ON o.oz_vendor_code = f.oz_vendor_code
        , json_each(COALESCE(f.barcodes, '[]')) AS j
        UNION ALL
        SELECT o.oz_vendor_code,
               o.oz_sku,
               o.oz_barcode_primary AS barcode,
               TRUE AS is_primary,
               o.oz_barcode_primary AS oz_primary_barcode,
               NULL::VARCHAR AS oz_russian_size,
               NULL::VARCHAR AS oz_product_name,
               NULL::VARCHAR AS oz_brand,
               NULL::VARCHAR AS oz_color
        FROM oz_full o
        LEFT JOIN oz_products_full f ON f.oz_vendor_code = o.oz_vendor_code
        WHERE o.oz_barcode_primary IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM json_each(COALESCE(f.barcodes, '[]')) AS j
              WHERE json_extract_string(j.value, '$') = o.oz_barcode_primary
          )
    )
    """

    joined_sql = r"""
    ,
    joined AS (
        SELECT w.wb_sku,
               o.oz_sku,
               o.oz_vendor_code,
               w.barcode AS barcode_hit,
               o.is_primary AS oz_is_primary_hit,
               w.is_primary AS wb_is_primary_hit,
               o.oz_primary_barcode,
               o.oz_russian_size,
               o.oz_product_name,
               o.oz_brand,
               o.oz_color,
               w.wb_primary_barcode,
               w.wb_size,
               w.wb_article,
               w.wb_brand,
               w.wb_color,
               CASE
                   WHEN o.is_primary AND w.is_primary THEN 'primary↔primary'
                   WHEN o.is_primary AND NOT w.is_primary THEN 'primary↔any'
                   WHEN NOT o.is_primary AND w.is_primary THEN 'any↔primary'
                   ELSE 'any↔any'
               END AS matched_by,
               CASE
                   WHEN o.is_primary AND w.is_primary THEN 100
                   WHEN o.is_primary OR  w.is_primary THEN 80
                   ELSE 60
               END AS match_score
        FROM wb_barcodes AS w
        JOIN oz_barcodes AS o ON o.barcode = w.barcode
    ),
    ranked AS (
        SELECT j.*, ROW_NUMBER() OVER (PARTITION BY j.wb_sku ORDER BY j.match_score DESC, j.oz_sku) AS rn
        FROM joined j
    )
    SELECT r.*
    FROM ranked r
    WHERE (? IS NULL OR r.rn <= ?)
    ORDER BY r.wb_sku, r.match_score DESC, r.oz_sku
    """

    if punta_enabled:
        sql_mid = ",\n    " + punta_cte + "\n"
        joined_enrich = r"""
               , pm_oz.collection AS punta_collection_oz
               , pm_oz.external_code AS punta_external_code_oz
               , pm_wb.collection AS punta_collection_wb
               , pm_wb.external_code AS punta_external_code_wb
               , (pm_oz.external_code = pm_wb.external_code) AS punta_external_equal
        """
        joined_sql = joined_sql.replace(
            "FROM wb_barcodes AS w",
            joined_enrich + "        FROM wb_barcodes AS w",
        )
        joined_sql = joined_sql.replace(
            "JOIN oz_barcodes AS o ON o.barcode = w.barcode",
            "JOIN oz_barcodes AS o ON o.barcode = w.barcode\n          " + punta_joins,
        )
        sql = sql_head + sql_mid + joined_sql
    else:
        sql = sql_head + joined_sql

    if limit_per_input is None or int(limit_per_input) <= 0:
        params = [None, 0]
    else:
        params = [int(limit_per_input), int(limit_per_input)]
    df = local_con.execute(sql, params).fetch_df()
    return df


def _matches_for_barcodes(
    barcodes: List[str],
    limit_per_barcode: Optional[int] = None,
    *,
    con: Optional[duckdb.DuckDBPyConnection] = None,
    md_token: Optional[str] = None,
    md_database: Optional[str] = None,
) -> pd.DataFrame:
    if not barcodes:
        return pd.DataFrame()
    local_con = _ensure_connection(con, md_token=md_token, md_database=md_database)

    df_inp = pd.DataFrame({"barcode": barcodes})
    local_con.register("inputs", df_inp)

    punta_enabled = _table_exists(local_con, "punta_barcodes") and _table_exists(local_con, "punta_products_codes")

    punta_cte = r"""
    punta_map AS (
        SELECT pb.barcode,
               pb.external_code,
               ppc.collection
        FROM punta_barcodes pb
        LEFT JOIN punta_products_codes ppc ON ppc.external_code = pb.external_code
    )
    """ if punta_enabled else ""

    punta_select = r"""
               , pm_oz.collection AS punta_collection_oz
               , pm_oz.external_code AS punta_external_code_oz
               , pm_wb.collection AS punta_collection_wb
               , pm_wb.external_code AS punta_external_code_wb
               , (pm_oz.external_code = pm_wb.external_code) AS punta_external_equal
    """ if punta_enabled else ""

    punta_joins = r"""
        LEFT JOIN punta_map pm_oz ON pm_oz.barcode = o.oz_primary_barcode
        LEFT JOIN punta_map pm_wb ON pm_wb.barcode = w.wb_primary_barcode
    """ if punta_enabled else ""

    sql_head = r"""
    WITH inp AS (
        SELECT TRIM(barcode) AS barcode FROM inputs WHERE TRIM(barcode) <> ''
    ),
    oz_full AS (
        SELECT p.oz_sku,
               p.oz_vendor_code,
               CAST(p."barcode-primary" AS VARCHAR) AS oz_barcode_primary
        FROM oz_products AS p
    ),
    oz_barcodes AS (
        SELECT f.oz_vendor_code,
               o.oz_sku,
               json_extract_string(j.value, '$') AS barcode,
               CASE WHEN json_extract_string(j.value, '$') = f.primary_barcode THEN TRUE ELSE FALSE END AS is_primary,
               f.primary_barcode AS oz_primary_barcode,
               f.russian_size AS oz_russian_size,
               f.product_name AS oz_product_name,
               f.brand AS oz_brand,
               f.color AS oz_color
        FROM oz_products_full AS f
        JOIN oz_full o ON o.oz_vendor_code = f.oz_vendor_code
        , json_each(COALESCE(f.barcodes, '[]')) AS j
        UNION ALL
        SELECT o.oz_vendor_code, o.oz_sku, o.oz_barcode_primary AS barcode, TRUE AS is_primary,
               o.oz_barcode_primary AS oz_primary_barcode,
               NULL::VARCHAR AS oz_russian_size,
               NULL::VARCHAR AS oz_product_name,
               NULL::VARCHAR AS oz_brand,
               NULL::VARCHAR AS oz_color
        FROM oz_full o
        LEFT JOIN oz_products_full f ON f.oz_vendor_code = o.oz_vendor_code
        WHERE o.oz_barcode_primary IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM json_each(COALESCE(f.barcodes, '[]')) AS j
              WHERE json_extract_string(j.value, '$') = o.oz_barcode_primary
          )
    ),
    wb_barcodes AS (
        SELECT wp.wb_sku,
               json_extract_string(j.value, '$') AS barcode,
               CASE WHEN json_extract_string(j.value, '$') = wp.primary_barcode THEN TRUE ELSE FALSE END AS is_primary,
               wp.size AS wb_size,
               wp.wb_article AS wb_article,
               wp.brand AS wb_brand,
               wp.color AS wb_color,
               wp.primary_barcode AS wb_primary_barcode
        FROM wb_products AS wp,
             json_each(COALESCE(wp.barcodes, '[]')) AS j
    )
    """

    joined_sql = r"""
    ,
    joined AS (
        SELECT i.barcode AS input_barcode,
               o.oz_sku,
               o.oz_vendor_code,
               w.wb_sku,
               i.barcode AS barcode_hit,
               o.is_primary AS oz_is_primary_hit,
               w.is_primary AS wb_is_primary_hit,
               o.oz_primary_barcode,
               o.oz_russian_size,
               o.oz_product_name,
               o.oz_brand,
               o.oz_color,
               w.wb_primary_barcode,
               w.wb_size,
               w.wb_article,
               w.wb_brand,
               w.wb_color,
               CASE
                   WHEN o.is_primary AND w.is_primary THEN 100
                   WHEN o.is_primary OR  w.is_primary THEN 80
                   ELSE 60
               END AS match_score
        FROM inp i
        JOIN oz_barcodes o ON o.barcode = i.barcode
        JOIN wb_barcodes w ON w.barcode = i.barcode
    ),
    ranked AS (
        SELECT j.*, ROW_NUMBER() OVER (
            PARTITION BY j.input_barcode ORDER BY j.match_score DESC, j.oz_sku, j.wb_sku
        ) AS rn
        FROM joined j
    )
    SELECT r.*
    FROM ranked r
    WHERE (? IS NULL OR r.rn <= ?)
    ORDER BY r.input_barcode, r.match_score DESC, r.oz_sku, r.wb_sku
    """

    if punta_enabled:
        sql_mid = ",\n    " + punta_cte + "\n"
        joined_enrich = r"""
               , pm_oz.collection AS punta_collection_oz
               , pm_oz.external_code AS punta_external_code_oz
               , pm_wb.collection AS punta_collection_wb
               , pm_wb.external_code AS punta_external_code_wb
               , (pm_oz.external_code = pm_wb.external_code) AS punta_external_equal
        """
        joined_sql = joined_sql.replace(
            "FROM inp i",
            joined_enrich + "        FROM inp i",
        )
        joined_sql = joined_sql.replace(
            "JOIN wb_barcodes w ON w.barcode = i.barcode",
            "JOIN wb_barcodes w ON w.barcode = i.barcode\n          " + punta_joins,
        )
        sql = sql_head + sql_mid + joined_sql
    else:
        sql = sql_head + joined_sql

    if limit_per_barcode is None or int(limit_per_barcode) <= 0:
        params = [None, 0]
    else:
        params = [int(limit_per_barcode), int(limit_per_barcode)]
    df = local_con.execute(sql, params).fetch_df()
    return df


def find_wb_by_oz(
    oz_sku: str,
    limit: Optional[int] = None,
    *,
    con: Optional[duckdb.DuckDBPyConnection] = None,
    md_token: Optional[str] = None,
    md_database: Optional[str] = None,
) -> List[Match]:
    """Возвращает кандидатов WB для заданного OZ SKU, отсортированных по score."""
    if not oz_sku:
        raise ValueError("oz_sku is empty")
    df = _matches_for_oz_skus([str(oz_sku)], limit_per_input=limit, con=con, md_token=md_token, md_database=md_database)
    out: List[Match] = []
    for _, r in df.iterrows():
        out.append(
            Match(
                oz_sku=str(r.get("oz_sku")) if pd.notna(r.get("oz_sku")) else None,
                wb_sku=str(r.get("wb_sku")) if pd.notna(r.get("wb_sku")) else None,
                barcode_hit=str(r.get("barcode_hit")),
                matched_by=str(r.get("matched_by")),
                match_score=int(r.get("match_score") or 0),
                confidence_note=None,
            )
        )
    return out


def find_oz_by_wb(
    wb_sku: str,
    limit: Optional[int] = None,
    *,
    con: Optional[duckdb.DuckDBPyConnection] = None,
    md_token: Optional[str] = None,
    md_database: Optional[str] = None,
) -> List[Match]:
    """Возвращает кандидатов OZ для заданного WB SKU, отсортированных по score."""
    if not wb_sku:
        raise ValueError("wb_sku is empty")
    df = _matches_for_wb_skus([str(wb_sku)], limit_per_input=limit, con=con, md_token=md_token, md_database=md_database)
    out: List[Match] = []
    for _, r in df.iterrows():
        out.append(
            Match(
                oz_sku=str(r.get("oz_sku")) if pd.notna(r.get("oz_sku")) else None,
                wb_sku=str(r.get("wb_sku")) if pd.notna(r.get("wb_sku")) else None,
                barcode_hit=str(r.get("barcode_hit")),
                matched_by=str(r.get("matched_by")),
                match_score=int(r.get("match_score") or 0),
                confidence_note=None,
            )
        )
    return out


def find_by_barcodes(
    barcodes: Iterable[str],
    limit: Optional[int] = None,
    *,
    con: Optional[duckdb.DuckDBPyConnection] = None,
    md_token: Optional[str] = None,
    md_database: Optional[str] = None,
) -> List[Match]:
    """Универсальный поиск по набору штрихкодов (любой стороны)."""
    barcodes_norm = _normalize_barcodes(barcodes)
    if not barcodes_norm:
        raise ValueError("barcodes are empty")
    df = _matches_for_barcodes(barcodes_norm, limit_per_barcode=limit, con=con, md_token=md_token, md_database=md_database)
    out: List[Match] = []
    for _, r in df.iterrows():
        out.append(
            Match(
                oz_sku=str(r.get("oz_sku")) if pd.notna(r.get("oz_sku")) else None,
                wb_sku=str(r.get("wb_sku")) if pd.notna(r.get("wb_sku")) else None,
                barcode_hit=str(r.get("barcode_hit")),
                matched_by=str(r.get("matched_by")),
                match_score=int(r.get("match_score") or 0),
                confidence_note=None,
            )
        )
    return out


# Дополнительная утилита для страницы: батч-поиск с выбором типа входа
def search_matches(
    inputs: Iterable[str],
    *,
    input_type: str,  # 'oz_sku' | 'wb_sku' | 'barcode' | 'oz_vendor_code'
    limit_per_input: Optional[int] = None,
    con: Optional[duckdb.DuckDBPyConnection] = None,
    md_token: Optional[str] = None,
    md_database: Optional[str] = None,
) -> pd.DataFrame:
    """Батч-поиск соответствий. Возвращает DataFrame с деталями по обеим сторонам.

    Параметры:
    - inputs: набор значений, поддерживается 10–300+ значений
    - input_type: один из 'oz_sku' | 'wb_sku' | 'barcode' | 'oz_vendor_code'
    - limit_per_input: ограничение числа кандидатов на одно входное значение
    """
    vals = _normalize_barcodes(inputs)  # переиспользуем нормализацию токенов
    if not vals:
        return pd.DataFrame()

    if input_type == "oz_sku":
        return _matches_for_oz_skus(vals, limit_per_input=limit_per_input, con=con, md_token=md_token, md_database=md_database)
    if input_type == "wb_sku":
        return _matches_for_wb_skus(vals, limit_per_input=limit_per_input, con=con, md_token=md_token, md_database=md_database)
    if input_type == "barcode":
        return _matches_for_barcodes(vals, limit_per_barcode=limit_per_input, con=con, md_token=md_token, md_database=md_database)
    if input_type == "oz_vendor_code":
        # Переведём oz_vendor_code → oz_sku для единообразия (берём все oz_sku данной карточки)
        local_con = _ensure_connection(con, md_token=md_token, md_database=md_database)
        df_inp = pd.DataFrame({"oz_vendor_code": vals})
        local_con.register("inputs_oid", df_inp)
        df_map = local_con.execute(
            """
            SELECT DISTINCT CAST(p.oz_sku AS VARCHAR) AS oz_sku
            FROM oz_products p
            JOIN inputs_oid i ON i.oz_vendor_code = p.oz_vendor_code
            WHERE p.oz_sku IS NOT NULL
            """
        ).fetch_df()
        ozs: List[str] = df_map["oz_sku"].astype(str).tolist()
        return _matches_for_oz_skus(ozs, limit_per_input=limit_per_input, con=con, md_token=md_token, md_database=md_database)

    raise ValueError(f"Unknown input_type: {input_type}")


def rebuild_barcode_index() -> None:  # placeholder for future precompute
    return None


def rebuild_matches() -> None:  # placeholder for future precompute
    return None
