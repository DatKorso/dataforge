from __future__ import annotations

import duckdb
from dataforge.matching import search_matches


def _prepare_conn_with_punta() -> duckdb.DuckDBPyConnection:
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
        CREATE TABLE punta_barcodes (
            collection VARCHAR,
            pn_article VARCHAR,
            product_type VARCHAR,
            external_code VARCHAR,
            size VARCHAR,
            barcode VARCHAR,
            tn_ved VARCHAR
        );
        CREATE TABLE punta_products (
            collection VARCHAR,
            "un-id" VARCHAR,
            status VARCHAR,
            buyer VARCHAR,
            pn_article VARCHAR,
            group_code VARCHAR,
            original_code VARCHAR,
            external_code_list TEXT,
            cost_usd DECIMAL(10,2)
        );
        """
    )

    # Seed MP data
    con.execute(
        """
        INSERT INTO oz_products VALUES ('A1', 111, 'PB1');
        INSERT INTO oz_products_full VALUES ('A1', '["PB1"]', 'PB1', '40', 'Prod A1', 'BrandOZ', 'black');
        INSERT INTO wb_products VALUES (1001, 'WBA', '["PB1"]', 'PB1', '40', 'BrandWB', 'black');
        """
    )
    # Seed Punta data: PB1 -> EXT1, product has collection C1
    con.execute(
        """
        INSERT INTO punta_barcodes VALUES ('C1', 'ART-1', 'type', 'EXT1', '40', 'PB1', 'TN');
        INSERT INTO punta_products VALUES ('C1', 'U1', 'st', 'buyer', 'ART-1', 'G', 'OC1', '["EXT1","EXT1-ALT"]', 10.0);
        CREATE OR REPLACE TABLE punta_products_codes AS
        SELECT json_extract_string(e.value, '$') AS external_code, p.*
        FROM punta_products p, json_each(COALESCE(p.external_code_list, '[]')) e;
        """
    )
    return con


def test_punta_enrichment_primary_only():
    con = _prepare_conn_with_punta()
    df = search_matches(['111'], input_type='oz_sku', limit_per_input=5, con=con)
    assert not df.empty
    row = df.iloc[0]
    # Should expose Punta external_code/collection via primary barcode
    assert row.get("punta_external_code_oz") == "EXT1"
    assert row.get("punta_collection_oz") == "C1"
    assert row.get("punta_external_code_wb") == "EXT1"
    assert row.get("punta_collection_wb") == "C1"
    # And equality flag is true
    assert bool(row.get("punta_external_equal")) is True

