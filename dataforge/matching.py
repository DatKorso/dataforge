from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import duckdb
import pandas as pd
from dataforge.db import get_connection
from dataforge.matching_query import MatchesQuery


@dataclass
class Match:
    oz_sku: str | None
    wb_sku: str | None
    barcode_hit: str
    matched_by: str  # 'primary↔primary' | 'primary↔any' | 'any↔primary' | 'any↔any'
    match_score: int
    confidence_note: str | None = None
    punta_external_code_oz: str | None = None

    @staticmethod
    def from_row(r: pd.Series) -> Match:
        return Match(
            oz_sku=str(r.get("oz_sku")) if pd.notna(r.get("oz_sku")) else None,
            wb_sku=str(r.get("wb_sku")) if pd.notna(r.get("wb_sku")) else None,
            barcode_hit=str(r.get("barcode_hit")),
            matched_by=str(r.get("matched_by")),
            match_score=int(r.get("match_score") or 0),
            confidence_note=None,
            punta_external_code_oz=(
                str(r.get("punta_external_code_oz"))
                if pd.notna(r.get("punta_external_code_oz"))
                else None
            ),
        )

    def __getitem__(self, key: str):
        """Allow dict-style access like the previous TypedDict (e.g. m['wb_sku']).

        Raises KeyError for unknown keys to mimic mapping behavior.
        """
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key: str, default=None):
        return getattr(self, key, default)


def _normalize_barcodes(barcodes: Iterable[str]) -> list[str]:
    """Strip and drop empty values; keep as strings.

    Parameters
    - barcodes: iterable of input strings

    Returns
    - list of cleaned strings
    """
    out: list[str] = []
    for b in barcodes:
        if b is None:
            continue
        s = str(b).strip()
        if s:
            out.append(s)
    return out


def _ensure_connection(
    con: duckdb.DuckDBPyConnection | None,
    *,
    md_token: str | None = None,
    md_database: str | None = None,
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


def _run_matches_query(
    con: duckdb.DuckDBPyConnection,
    sql: str,
    params: list | None = None,
) -> pd.DataFrame:
    """Central execute helper: runs given SQL with params and returns DataFrame.

    This encapsulates the single place where `execute(...).fetch_df()` is called so
    callers can be simplified and behavior is consistent.
    """
    if params is None:
        params = [None, 0]
    return con.execute(sql, params).fetch_df()


def _matches_for_oz_skus(
    oz_skus: list[str],
    limit_per_input: int | None = None,
    *,
    con: duckdb.DuckDBPyConnection | None = None,
    md_token: str | None = None,
    md_database: str | None = None,
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

    # punta fragments are injected by MatchesQuery.assemble when needed

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
               f.russian_size AS oz_manufacturer_size,
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
               NULL::VARCHAR AS oz_manufacturer_size,
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
                        oz_primary_barcode, oz_manufacturer_size, oz_product_name, oz_brand, oz_color
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
        FROM wb_products AS wp
        , json_each(COALESCE(wp.barcodes, '[]')) AS j
    )
    """

    joined_sql = r"""
    ,
    joined AS (
        SELECT o.oz_sku,
               o.oz_vendor_code,
               w.wb_sku,
               w.barcode AS barcode_hit,
               o.is_primary AS oz_is_primary_hit,
               w.is_primary AS wb_is_primary_hit,
               o.oz_primary_barcode,
               o.oz_manufacturer_size,
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
        JOIN wb_barcodes AS w ON w.barcode = o.barcode
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

    sql = MatchesQuery.assemble(sql_head, joined_sql, "oz", punta_enabled)

    params = [None, 0] if limit_per_input is None or int(limit_per_input) <= 0 else [int(limit_per_input), int(limit_per_input)]
    return _run_matches_query(local_con, sql, params)


def _matches_for_wb_skus(
    wb_skus: list[str],
    limit_per_input: int | None = None,
    *,
    con: duckdb.DuckDBPyConnection | None = None,
    md_token: str | None = None,
    md_database: str | None = None,
) -> pd.DataFrame:
    if not wb_skus:
        return pd.DataFrame()
    local_con = _ensure_connection(con, md_token=md_token, md_database=md_database)
    df_inp = pd.DataFrame({"wb_sku": wb_skus})
    local_con.register("inputs", df_inp)

    punta_enabled = _table_exists(local_con, "punta_barcodes") and _table_exists(local_con, "punta_products_codes")

    # punta fragments are injected by MatchesQuery.assemble when needed

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
               f.russian_size AS oz_manufacturer_size,
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
               NULL::VARCHAR AS oz_manufacturer_size,
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
               o.oz_manufacturer_size,
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

    sql = MatchesQuery.assemble(sql_head, joined_sql, "wb", punta_enabled)

    params = [None, 0] if limit_per_input is None or int(limit_per_input) <= 0 else [int(limit_per_input), int(limit_per_input)]
    return _run_matches_query(local_con, sql, params)


def _matches_for_barcodes(
    barcodes: list[str],
    limit_per_barcode: int | None = None,
    *,
    con: duckdb.DuckDBPyConnection | None = None,
    md_token: str | None = None,
    md_database: str | None = None,
) -> pd.DataFrame:
    if not barcodes:
        return pd.DataFrame()
    local_con = _ensure_connection(con, md_token=md_token, md_database=md_database)

    df_inp = pd.DataFrame({"barcode": barcodes})
    local_con.register("inputs", df_inp)

    punta_enabled = _table_exists(local_con, "punta_barcodes") and _table_exists(local_con, "punta_products_codes")

    # punta fragments are injected by MatchesQuery.assemble when needed

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
               f.russian_size AS oz_manufacturer_size,
               f.product_name AS oz_product_name,
               f.brand AS oz_brand,
               f.color AS oz_color
        FROM oz_products_full AS f
        JOIN oz_full o ON o.oz_vendor_code = f.oz_vendor_code
        , json_each(COALESCE(f.barcodes, '[]')) AS j
        UNION ALL
        SELECT o.oz_vendor_code, o.oz_sku, o.oz_barcode_primary AS barcode, TRUE AS is_primary,
               o.oz_barcode_primary AS oz_primary_barcode,
               NULL::VARCHAR AS oz_manufacturer_size,
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
               o.oz_manufacturer_size,
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
        FROM inp AS i
        LEFT JOIN oz_barcodes AS o ON o.barcode = i.barcode
        LEFT JOIN wb_barcodes AS w ON w.barcode = i.barcode
        WHERE o.oz_sku IS NOT NULL OR w.wb_sku IS NOT NULL
    ),
    ranked AS (
        SELECT j.*, ROW_NUMBER() OVER (PARTITION BY j.input_barcode ORDER BY j.match_score DESC, j.oz_sku, j.wb_sku) AS rn
        FROM joined j
    )
    SELECT r.*
    FROM ranked r
    WHERE (? IS NULL OR r.rn <= ?)
    ORDER BY r.input_barcode, r.match_score DESC, r.oz_sku, r.wb_sku
    """

    sql = MatchesQuery.assemble(sql_head, joined_sql, "barcode", punta_enabled)

    params = [None, 0] if limit_per_barcode is None or int(limit_per_barcode) <= 0 else [int(limit_per_barcode), int(limit_per_barcode)]
    return _run_matches_query(local_con, sql, params)


def _matches_for_external_codes(
    external_codes: list[str],
    limit_per_code: int | None = None,
    *,
    con: duckdb.DuckDBPyConnection | None = None,
    md_token: str | None = None,
    md_database: str | None = None,
) -> pd.DataFrame:
    """Найти соответствия для списка Punta external_code.

    Возвращает DataFrame, где каждая строка описывает совпадение между OZ и WB,
    и колонкой `input_external_code`, показывающей исходный код поиска.
    """
    if not external_codes:
        return pd.DataFrame()

    local_con = _ensure_connection(con, md_token=md_token, md_database=md_database)

    if not _table_exists(local_con, "punta_barcodes") or not _table_exists(local_con, "punta_products_codes"):
        raise ValueError(
            "Поиск по Punta external_code недоступен: отсутствуют таблицы punta_barcodes/punta_products_codes."
        )

    df_inp = pd.DataFrame({"external_code": external_codes})
    local_con.register("inputs", df_inp)

    # punta fragments are injected by MatchesQuery.assemble when needed

    sql_head = r"""
    WITH inp AS (
        SELECT TRIM(external_code) AS external_code
        FROM inputs
        WHERE TRIM(external_code) <> ''
    ),
    matched AS (
        SELECT i.external_code,
               eb.barcode
        FROM inp i
        JOIN ext_barcodes eb ON eb.external_code = i.external_code
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
               f.russian_size AS oz_manufacturer_size,
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
               NULL::VARCHAR AS oz_manufacturer_size,
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
        SELECT m.external_code AS input_external_code,
               o.oz_sku,
               o.oz_vendor_code,
               w.wb_sku,
               m.barcode AS barcode_hit,
               o.is_primary AS oz_is_primary_hit,
               w.is_primary AS wb_is_primary_hit,
               o.oz_primary_barcode,
               o.oz_manufacturer_size,
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
        FROM matched AS m
        LEFT JOIN oz_barcodes AS o ON o.barcode = m.barcode
        LEFT JOIN wb_barcodes AS w ON w.barcode = m.barcode
        WHERE o.oz_sku IS NOT NULL OR w.wb_sku IS NOT NULL
    ),
    ranked AS (
        SELECT j.*, ROW_NUMBER() OVER (PARTITION BY j.input_external_code ORDER BY j.match_score DESC, j.oz_sku, j.wb_sku) AS rn
        FROM joined j
    )
    SELECT r.*
    FROM ranked r
    WHERE (? IS NULL OR r.rn <= ?)
    ORDER BY r.input_external_code, r.match_score DESC, r.oz_sku, r.wb_sku
    """

    sql = MatchesQuery.assemble(sql_head, joined_sql, "external", True)

    params = [None, 0] if limit_per_code is None or int(limit_per_code) <= 0 else [int(limit_per_code), int(limit_per_code)]
    return _run_matches_query(local_con, sql, params)


def find_wb_by_oz(
    oz_sku: str,
    limit: int | None = None,
    *,
    con: duckdb.DuckDBPyConnection | None = None,
    md_token: str | None = None,
    md_database: str | None = None,
) -> list[Match]:
    """Возвращает кандидатов WB для заданного OZ SKU, отсортированных по score."""
    if not oz_sku:
        raise ValueError("oz_sku is empty")
    df = _matches_for_oz_skus(
        [str(oz_sku)],
        limit_per_input=limit,
        con=con,
        md_token=md_token,
        md_database=md_database,
    )
    out: list[Match] = []
    for _, r in df.iterrows():
        out.append(Match.from_row(r))
    return out


def find_oz_by_wb(
    wb_sku: str,
    limit: int | None = None,
    *,
    con: duckdb.DuckDBPyConnection | None = None,
    md_token: str | None = None,
    md_database: str | None = None,
) -> list[Match]:
    """Возвращает кандидатов OZ для заданного WB SKU, отсортированных по score."""
    if not wb_sku:
        raise ValueError("wb_sku is empty")
    df = _matches_for_wb_skus(
        [str(wb_sku)],
        limit_per_input=limit,
        con=con,
        md_token=md_token,
        md_database=md_database,
    )
    out: list[Match] = []
    for _, r in df.iterrows():
        out.append(Match.from_row(r))
    return out


def find_by_barcodes(
    barcodes: Iterable[str],
    limit: int | None = None,
    *,
    con: duckdb.DuckDBPyConnection | None = None,
    md_token: str | None = None,
    md_database: str | None = None,
) -> list[Match]:
    """Универсальный поиск по набору штрихкодов (любой стороны)."""
    barcodes_norm = _normalize_barcodes(barcodes)
    if not barcodes_norm:
        raise ValueError("barcodes are empty")
    df = _matches_for_barcodes(
        barcodes_norm,
        limit_per_barcode=limit,
        con=con,
        md_token=md_token,
        md_database=md_database,
    )
    out: list[Match] = []
    for _, r in df.iterrows():
        out.append(Match.from_row(r))
    return out


# Дополнительная утилита для страницы: батч-поиск с выбором типа входа
def search_matches(
    inputs: Iterable[str],
    *,
    input_type: str,  # 'oz_sku' | 'wb_sku' | 'barcode' | 'oz_vendor_code' | 'punta_external_code'
    limit_per_input: int | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
    md_token: str | None = None,
    md_database: str | None = None,
) -> pd.DataFrame:
    """Батч-поиск соответствий. Возвращает DataFrame с деталями по обеим сторонам.

    Параметры:
    - inputs: набор значений, поддерживается 10–300+ значений
    - input_type: один из 'oz_sku' | 'wb_sku' | 'barcode' | 'oz_vendor_code' | 'punta_external_code'
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
    if input_type == "punta_external_code":
        return _matches_for_external_codes(vals, limit_per_code=limit_per_input, con=con, md_token=md_token, md_database=md_database)
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
        ozs: list[str] = df_map["oz_sku"].astype(str).tolist()
        return _matches_for_oz_skus(ozs, limit_per_input=limit_per_input, con=con, md_token=md_token, md_database=md_database)

    raise ValueError(f"Unknown input_type: {input_type}")


# --- Similarity (wb_similarity) algorithm implementation ---
try:  # реэкспорт для обратной совместимости старых импортов
    from dataforge.similarity_matching import search_similar_matches  # type: ignore # noqa: E402,F401
except Exception:  # pragma: no cover
    pass


def rebuild_barcode_index() -> None:  # placeholder for future precompute
    return None


def rebuild_matches() -> None:  # placeholder for future precompute
    return None
