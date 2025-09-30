from __future__ import annotations

from typing import Literal

from dataforge.matching_sql import PUNTA_CTE, PUNTA_JOINS, PUNTA_SELECT

Mode = Literal["oz", "wb", "barcode", "external"]


class MatchesQuery:
    """Small helper to assemble the final SQL for matches queries.

    It centralizes how `punta` fragments are injected into the base CTEs and joined
    parts. The goal is to avoid repeating the same replace/insert logic in multiple
    functions while keeping the resulting SQL identical to the previous implementation.
    """

    @staticmethod
    def assemble(sql_head: str, joined_sql: str, mode: Mode, punta_enabled: bool) -> str:
        if not punta_enabled:
            return sql_head + joined_sql

        sql_mid = ",\n    " + PUNTA_CTE + "\n"

        if mode == "oz":
            joined_enrich = PUNTA_SELECT
            joined_sql = joined_sql.replace(
                "FROM oz_barcodes AS o",
                joined_enrich + "        FROM oz_barcodes AS o",
            )
            joined_sql = joined_sql.replace(
                "JOIN wb_barcodes AS w ON w.barcode = o.barcode",
                "JOIN wb_barcodes AS w ON w.barcode = o.barcode\n          " + PUNTA_JOINS,
            )
            return sql_head + sql_mid + joined_sql

        if mode == "wb":
            joined_enrich = PUNTA_SELECT
            joined_sql = joined_sql.replace(
                "FROM wb_barcodes AS w",
                joined_enrich + "        FROM wb_barcodes AS w",
            )
            joined_sql = joined_sql.replace(
                "JOIN oz_barcodes AS o ON o.barcode = w.barcode",
                "JOIN oz_barcodes AS o ON o.barcode = w.barcode\n          " + PUNTA_JOINS,
            )
            return sql_head + sql_mid + joined_sql

        if mode == "barcode":
            joined_enrich = PUNTA_SELECT
            joined_sql = joined_sql.replace(
                "FROM inp AS i",
                joined_enrich + "        FROM inp AS i",
            )
            joined_sql = joined_sql.replace(
                "LEFT JOIN oz_barcodes AS o ON o.barcode = i.barcode",
                "LEFT JOIN oz_barcodes AS o ON o.barcode = i.barcode\n          LEFT JOIN punta_map pm_oz ON pm_oz.barcode = COALESCE(o.oz_primary_barcode, o.barcode)",
            )
            joined_sql = joined_sql.replace(
                "LEFT JOIN wb_barcodes AS w ON w.barcode = i.barcode",
                "LEFT JOIN wb_barcodes AS w ON w.barcode = i.barcode\n          LEFT JOIN punta_map pm_wb ON pm_wb.barcode = COALESCE(w.wb_primary_barcode, w.barcode)",
            )
            return sql_head + sql_mid + joined_sql

        # external
        joined_sql = joined_sql.replace(
            "FROM matched AS m",
            PUNTA_SELECT + "        FROM matched AS m",
        )
        joined_sql = joined_sql.replace(
            "LEFT JOIN oz_barcodes AS o ON o.barcode = m.barcode",
            "LEFT JOIN oz_barcodes AS o ON o.barcode = m.barcode\n          LEFT JOIN punta_map pm_oz ON pm_oz.barcode = COALESCE(o.oz_primary_barcode, o.barcode)",
        )
        joined_sql = joined_sql.replace(
            "LEFT JOIN wb_barcodes AS w ON w.barcode = m.barcode",
            "LEFT JOIN wb_barcodes AS w ON w.barcode = m.barcode\n          LEFT JOIN punta_map pm_wb ON pm_wb.barcode = COALESCE(w.wb_primary_barcode, w.barcode)",
        )
        head = sql_head.lstrip()
        if head.startswith("WITH "):
            head = head[len("WITH ") :]
        return "WITH " + PUNTA_CTE + ",\n" + head + joined_sql
