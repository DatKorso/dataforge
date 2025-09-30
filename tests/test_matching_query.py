from dataforge.matching_query import MatchesQuery
from dataforge.matching_sql import PUNTA_CTE, PUNTA_SELECT, PUNTA_JOINS


def test_matchesquery_injects_punta_for_oz():
    sql_head = "WITH inp AS (SELECT 1 AS oz_sku)"
    joined_sql = "FROM oz_barcodes AS o\nJOIN wb_barcodes AS w ON w.barcode = o.barcode"
    out = MatchesQuery.assemble(sql_head, joined_sql, "oz", punta_enabled=True)
    assert "punta_map" in out
    assert "pm_oz" in out or "punta_collection_oz" in out
    assert "LEFT JOIN punta_map" in out


def test_matchesquery_no_punta_when_disabled():
    sql_head = "WITH inp AS (SELECT 1 AS oz_sku)"
    joined_sql = "FROM oz_barcodes AS o\nJOIN wb_barcodes AS w ON w.barcode = o.barcode"
    out = MatchesQuery.assemble(sql_head, joined_sql, "oz", punta_enabled=False)
    assert "punta_map" not in out

