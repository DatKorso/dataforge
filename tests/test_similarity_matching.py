from __future__ import annotations

import pandas as pd
import duckdb
from dataforge.similarity_matching import search_similar_matches
from dataforge.similarity_config import SimilarityScoringConfig

# Вспомогательные фикстуры внутри файла (изолированные) — используем in-memory DuckDB

def _prep_conn():
    con = duckdb.connect()
    # Минимальные таблицы wb_products и punta_google и oz_products/oz_products_full
    con.execute("""
        CREATE TABLE wb_products (
            wb_sku UBIGINT,
            seller_category VARCHAR,
            gender VARCHAR,
            barcodes JSON,
            primary_barcode VARCHAR,
            size VARCHAR,
            wb_article VARCHAR,
            brand VARCHAR,
            color VARCHAR
        );
    """)
    con.execute("""
        CREATE TABLE punta_google (
            wb_sku UBIGINT,
            season VARCHAR,
            color VARCHAR,
            lacing_type VARCHAR,
            material_short VARCHAR,
            mega_last VARCHAR,
            best_last VARCHAR,
            new_last VARCHAR,
            model_name VARCHAR
        );
    """)
    con.execute("""
        CREATE TABLE oz_products (
            oz_sku UBIGINT,
            oz_vendor_code VARCHAR,
            "barcode-primary" VARCHAR
        );
    """)
    con.execute("""
        CREATE TABLE oz_products_full (
            oz_vendor_code VARCHAR,
            barcodes JSON,
            primary_barcode VARCHAR,
            russian_size VARCHAR,
            product_name VARCHAR,
            brand VARCHAR,
            color VARCHAR
        );
    """)
    return con


def _json_array(*vals: str) -> str:
    import json
    return json.dumps(list(vals))


def test_similarity_basic_season_match():
    con = _prep_conn()
    # seed wb_sku = 100, candidate = 101 (same category/gender)
    con.execute("INSERT INTO wb_products VALUES (100, 'Shoes', 'M', ?, 'PB100', '42', 'ART100', 'BR', 'RED')", [_json_array('PB100')])
    con.execute("INSERT INTO wb_products VALUES (101, 'Shoes', 'M', ?, 'PB101', '43', 'ART101', 'BR', 'BLUE')", [_json_array('PB101')])
    # punta_google attributes
    con.execute("INSERT INTO punta_google VALUES (100,'WINTER','RED','LACE','LEATHER','M1',NULL,NULL,'MODELX')")
    con.execute("INSERT INTO punta_google VALUES (101,'WINTER','BLUE','LACE','LEATHER','M1',NULL,NULL,'MODELX')")
    # OZ side: map both wb barcodes to distinct oz products
    con.execute("INSERT INTO oz_products VALUES (500,'OZ-A-500','OZPB500')")
    con.execute("INSERT INTO oz_products_full VALUES ('OZ-A-500', ?, 'OZPB500', '42', 'Prod A', 'OBR', 'AQUA')", [_json_array('PB100')])
    con.execute("INSERT INTO oz_products VALUES (501,'OZ-B-501','OZPB501')")
    con.execute("INSERT INTO oz_products_full VALUES ('OZ-B-501', ?, 'OZPB501', '43', 'Prod B', 'OBR', 'NAVY')", [_json_array('PB101')])

    cfg = SimilarityScoringConfig()
    df = search_similar_matches([100], config=cfg, con=con)
    # candidate 101 should appear
    assert not df.empty
    assert set(df['wb_sku'].astype(int)) == {100,101}


def test_similarity_season_mismatch_penalty():
    con = _prep_conn()
    con.execute("INSERT INTO wb_products VALUES (200,'Shoes','F', ?, 'PB200', '38', 'ART200', 'BR', 'RED')", [_json_array('PB200')])
    con.execute("INSERT INTO wb_products VALUES (201,'Shoes','F', ?, 'PB201', '39', 'ART201', 'BR', 'RED')", [_json_array('PB201')])
    con.execute("INSERT INTO punta_google VALUES (200,'WINTER','RED','ZIP','LEATHER',NULL,'B1',NULL,'MODELZ')")
    con.execute("INSERT INTO punta_google VALUES (201,'SUMMER','RED','ZIP','LEATHER',NULL,'B1',NULL,'MODELZ')")
    con.execute("INSERT INTO oz_products VALUES (600,'OZ-COLOR-600','OZPB600')")
    con.execute("INSERT INTO oz_products_full VALUES ('OZ-COLOR-600', ?, 'OZPB600', '38', 'Prod C', 'BR', 'GREEN')", [_json_array('PB200')])
    con.execute("INSERT INTO oz_products VALUES (601,'OZ-COLOR-601','OZPB601')")
    con.execute("INSERT INTO oz_products_full VALUES ('OZ-COLOR-601', ?, 'OZPB601', '39', 'Prod D', 'BR', 'YELLOW')", [_json_array('PB201')])

    cfg = SimilarityScoringConfig()
    df = search_similar_matches([200], config=cfg, con=con)
    assert not df.empty
    # presence of both wb sku
    assert set(df['wb_sku'].astype(int)) == {200,201}


def test_similarity_no_last_penalty():
    con = _prep_conn()
    con.execute("INSERT INTO wb_products VALUES (300,'Shoes','M', ?, 'PB300', '40', 'ART300', 'BR', 'BLK')", [_json_array('PB300')])
    con.execute("INSERT INTO wb_products VALUES (301,'Shoes','M', ?, 'PB301', '41', 'ART301', 'BR', 'BLK')", [_json_array('PB301')])
    # No last fields -> expect base * multiplier path
    con.execute("INSERT INTO punta_google VALUES (300,'WINTER','BLK','VELCRO','TEXTILE',NULL,NULL,NULL,'MODA')")
    con.execute("INSERT INTO punta_google VALUES (301,'WINTER','BLK','VELCRO','TEXTILE',NULL,NULL,NULL,'MODA')")
    con.execute("INSERT INTO oz_products VALUES (700,'OZ-X-700','OZPB700')")
    con.execute("INSERT INTO oz_products_full VALUES ('OZ-X-700', ?, 'OZPB700', '40', 'Prod X', 'BR', 'RED')", [_json_array('PB300')])
    con.execute("INSERT INTO oz_products VALUES (701,'OZ-X-701','OZPB701')")
    con.execute("INSERT INTO oz_products_full VALUES ('OZ-X-701', ?, 'OZPB701', '41', 'Prod Y', 'BR', 'BLUE')", [_json_array('PB301')])

    cfg = SimilarityScoringConfig()
    df = search_similar_matches([300], config=cfg, con=con)
    assert not df.empty
    assert set(df['wb_sku'].astype(int)) == {300,301}


def test_similarity_merge_code_and_color():
    con = _prep_conn()
    con.execute("INSERT INTO wb_products VALUES (400,'Shoes','M', ?, 'PB400', '40', 'ART400', 'BR', 'BLK')", [_json_array('PB400')])
    con.execute("INSERT INTO wb_products VALUES (401,'Shoes','M', ?, 'PB401', '41', 'ART401', 'BR', 'BLK')", [_json_array('PB401')])
    con.execute("INSERT INTO punta_google VALUES (400,'WINTER','BLK','ZIP','TEXT','M1',NULL,NULL,'M1')")
    con.execute("INSERT INTO punta_google VALUES (401,'WINTER','BLK','ZIP','TEXT','M1',NULL,NULL,'M1')")
    con.execute("INSERT INTO oz_products VALUES (800,'OZ-COLOR-800','OZPB800')")
    con.execute("INSERT INTO oz_products_full VALUES ('OZ-COLOR-800', ?, 'OZPB800', '40', 'Prod A', 'BR', 'RED')", [_json_array('PB400')])
    con.execute("INSERT INTO oz_products VALUES (801,'OZ-COLOR-801','OZPB801')")
    con.execute("INSERT INTO oz_products_full VALUES ('OZ-COLOR-801', ?, 'OZPB801', '41', 'Prod B', 'BR', 'RED')", [_json_array('PB401')])

    df = search_similar_matches([400], con=con)
    assert not df.empty
    assert all(df['merge_code'].str.startswith('C-'))
    # merge_color must contain HEX(wb_sku) (e.g., 400 -> 190) present at least once
    assert any(format(400, 'X') in mc for mc in df['merge_color'])

