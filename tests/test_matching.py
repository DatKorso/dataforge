from __future__ import annotations

import duckdb

from dataforge.matching import find_oz_by_wb, find_wb_by_oz, find_by_barcodes, search_matches


def _prepare_conn() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    # Minimal schemas used by queries
    con.execute(
        """
        CREATE TABLE oz_products (
            oz_vendor_code VARCHAR,
            oz_sku BIGINT,
            "barcode-primary" VARCHAR
        );
        CREATE TABLE oz_products_full (
            oz_vendor_code VARCHAR,
            barcodes TEXT,
            primary_barcode VARCHAR,
            russian_size VARCHAR,
            product_name VARCHAR,
            brand VARCHAR,
            color VARCHAR
        );
        CREATE TABLE wb_products (
            wb_sku BIGINT,
            wb_article VARCHAR,
            barcodes TEXT,
            primary_barcode VARCHAR,
            size VARCHAR,
            brand VARCHAR,
            color VARCHAR
        );
        """
    )

    # Data
    con.execute(
        """
        INSERT INTO oz_products VALUES
            ('A1', 111, 'PB1'),
            ('A2', 112, 'PB2');

        INSERT INTO oz_products_full VALUES
            ('A1', '["B1","PB1"]', 'PB1', '40', 'Prod A1', 'BrandOZ', 'black'),
            ('A2', '["X","PB2"]', 'PB2', '41', 'Prod A2', 'BrandOZ', 'white');

        INSERT INTO wb_products VALUES
            (1001, 'WBA-1', '["PB1","WBA"]', 'PB1', '40', 'BrandWB', 'black'),
            (1002, 'WBB-2', '["X","Y"]', 'X', '41', 'BrandWB', 'white');
        """
    )
    return con


def test_find_wb_by_oz_primary_primary():
    con = _prepare_conn()
    res = find_wb_by_oz('111', limit=5, con=con)
    assert res, "Expected at least one match"
    top = res[0]
    assert top["wb_sku"] == '1001'
    assert top["matched_by"] == 'primary↔primary'
    assert top["match_score"] == 100


def test_find_oz_by_wb_any_primary():
    con = _prepare_conn()
    res = find_oz_by_wb('1002', limit=5, con=con)
    assert res, "Expected at least one match"
    top = res[0]
    assert top["oz_sku"] == '112'
    assert top["matched_by"] == 'any↔primary'
    assert top["match_score"] == 80


def test_find_by_barcodes_pairing():
    con = _prepare_conn()
    res = find_by_barcodes(['PB1'], limit=10, con=con)
    assert any(r["oz_sku"] == '111' and r["wb_sku"] == '1001' for r in res)


def test_search_matches_batch_oz_sku():
    con = _prepare_conn()
    df = search_matches(['111','112'], input_type='oz_sku', limit_per_input=3, con=con)
    assert not df.empty
    # Both inputs should have rows
    assert set(df["oz_sku"].astype(str)) == {'111', '112'}


def _conn_primary_vs_secondary_wb_case() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE oz_products (
            oz_vendor_code VARCHAR,
            oz_sku BIGINT,
            "barcode-primary" VARCHAR
        );
        CREATE TABLE oz_products_full (
            oz_vendor_code VARCHAR,
            barcodes TEXT,
            primary_barcode VARCHAR,
            russian_size VARCHAR,
            product_name VARCHAR,
            brand VARCHAR,
            color VARCHAR
        );
        CREATE TABLE wb_products (
            wb_sku BIGINT,
            wb_article VARCHAR,
            barcodes TEXT,
            primary_barcode VARCHAR,
            size VARCHAR,
            brand VARCHAR,
            color VARCHAR
        );
        """
    )
    # OZ: primary PB1, present in barcodes
    con.execute(
        """
        INSERT INTO oz_products VALUES ('A1', 111, 'PB1');
        INSERT INTO oz_products_full VALUES ('A1', '["ALT","PB1"]', 'PB1', '40', 'Prod OZ', 'BrandOZ', 'black');
        """
    )
    # WB: two SKUs share barcode PB1, but only one has PB1 as primary
    con.execute(
        """
        INSERT INTO wb_products VALUES
            (2001, 'WB-ACT', '["PB1","X"]', 'PB1', '40', 'BrandWB', 'black'), -- primary↔primary
            (2002, 'WB-OLD', '["PB1","Y"]', 'Y',   '40', 'BrandWB', 'black'); -- primary↔any
        """
    )
    return con


def test_multiple_wb_matches_primary_and_nonprimary_for_oz_sku():
    con = _conn_primary_vs_secondary_wb_case()
    df = search_matches(['111'], input_type='oz_sku', limit_per_input=5, con=con)
    # Expect two WB candidates for one OZ SKU
    cand = df[df["oz_sku"] == 111]
    assert len(cand) == 2
    # One should be primary↔primary, the other primary↔any
    tags = set(cand["matched_by"].astype(str))
    assert tags == {"primary↔primary", "primary↔any"}
    # Check flags per wb_sku
    row_act = cand[cand["wb_sku"] == 2001].iloc[0]
    row_old = cand[cand["wb_sku"] == 2002].iloc[0]
    assert bool(row_act["wb_is_primary_hit"]) is True
    assert bool(row_old["wb_is_primary_hit"]) is False
    assert bool(row_act["oz_is_primary_hit"]) is True
    assert bool(row_old["oz_is_primary_hit"]) is True
