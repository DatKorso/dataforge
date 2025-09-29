from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from dataforge.db import get_connection


@dataclass(frozen=True)
class TableSchema:
    name: str
    create_sql: str
    index_sql: List[Tuple[str, str]]  # (index_name, create_sql)


def _oz_products_schema() -> TableSchema:
    name = "oz_products"
    # Hardcoded schema for readability and stability
    create = f"""
    CREATE TABLE IF NOT EXISTS "{name}" (
        oz_vendor_code VARCHAR,
        oz_product_id BIGINT,
        oz_sku BIGINT,
        "barcode-primary" VARCHAR,
        product_name TEXT,
        brand VARCHAR,
        product_status VARCHAR,
        tags TEXT,
        reviews_count INTEGER,
        rating DECIMAL(3,2),
        visibility_status VARCHAR,
        hide_reasons TEXT,
        fbo_available INTEGER,
        reserved_qty INTEGER,
        current_price DECIMAL(10,2),
        original_price DECIMAL(10,2),
        premium_price DECIMAL(10,2),
        market_price DECIMAL(10,2),
        vat_rate VARCHAR(10),
        discount_percent DECIMAL(5,2)
    )
    """

    # Indexes (non-unique). Rebuilt after loads as the table is replaced.
    idx_defs = [
        (f"idx_{name}_oz_product_id", f'CREATE INDEX {{}} ON "{name}" (oz_product_id)'),
        (f"idx_{name}_oz_sku", f'CREATE INDEX {{}} ON "{name}" (oz_sku)'),
        (f"idx_{name}_oz_vendor_code", f'CREATE INDEX {{}} ON "{name}" (oz_vendor_code)'),
        (f"idx_{name}_barcode_primary", f'CREATE INDEX {{}} ON "{name}" ("barcode-primary")'),
    ]

    # Fill in index name placeholders
    index_sql: List[Tuple[str, str]] = []
    for idx_name, tmpl in idx_defs:
        index_sql.append((idx_name, tmpl.format(idx_name)))

    return TableSchema(name=name, create_sql=create, index_sql=index_sql)


def get_all_schemas() -> Dict[str, TableSchema]:
    prod = _oz_products_schema()

    # Ozon orders schema (from docs/TZ_oz_orders_import.md)
    def _oz_orders_schema() -> TableSchema:
        name = "oz_orders"
        create = f"""
        CREATE TABLE IF NOT EXISTS "{name}" (
            order_number VARCHAR(50),
            shipment_number VARCHAR(50),
            processing_date TIMESTAMP,
            shipment_date TIMESTAMP,
            status VARCHAR(100),
            delivery_date TIMESTAMP,
            actual_delivery_transfer_date TIMESTAMP,
            shipment_amount DECIMAL(10,2),
            shipment_currency_code VARCHAR(3),
            product_name TEXT,
            oz_product_id BIGINT,
            oz_vendor_code VARCHAR(100),
            your_product_cost DECIMAL(10,2),
            product_currency_code VARCHAR(3),
            customer_product_cost DECIMAL(10,2),
            customer_currency_code VARCHAR(3),
            quantity INTEGER,
            delivery_cost DECIMAL(10,2),
            related_shipments TEXT,
            product_buyout VARCHAR(50),
            price_before_discount DECIMAL(10,2),
            discount_percent DECIMAL(5,2),
            discount_amount DECIMAL(10,2),
            promotions TEXT
        )
        """

        idx_defs = [
            (f"idx_{name}_oz_product_id", f'CREATE INDEX {{}} ON "{name}" (oz_product_id)'),
            (f"idx_{name}_oz_vendor_code", f'CREATE INDEX {{}} ON "{name}" (oz_vendor_code)'),
        ]
        index_sql: List[Tuple[str, str]] = []
        for idx_name, tmpl in idx_defs:
            index_sql.append((idx_name, tmpl.format(idx_name)))
        return TableSchema(name=name, create_sql=create, index_sql=index_sql)

    orders = _oz_orders_schema()

    # Ozon products full schema
    def _oz_products_full_schema() -> TableSchema:
        name = "oz_products_full"
        create = f"""
        CREATE TABLE IF NOT EXISTS "{name}" (
            oz_vendor_code VARCHAR(100),
            product_name VARCHAR(500),
            price DECIMAL(10,2),
            price_before_discount DECIMAL(10,2),
            vat_percent INTEGER,
            barcodes TEXT,
            primary_barcode VARCHAR(50),
            weight_grams INTEGER,
            package_width_mm INTEGER,
            package_height_mm INTEGER,
            package_length_mm INTEGER,
            main_photo_url TEXT,
            additional_photos_urls TEXT,
            photo_article VARCHAR(100),
            brand VARCHAR(100),
            group_on_card VARCHAR(100),
            color VARCHAR(100),
            russian_size VARCHAR(20),
            color_name VARCHAR(100),
            manufacturer_size VARCHAR(20),
            product_type VARCHAR(100),
            gender VARCHAR(20),
            season VARCHAR(50),
            group_name VARCHAR(200),
            error_message TEXT,
            warning_message TEXT,
            video_name VARCHAR(500),
            video_url TEXT,
            video_products TEXT,
            video_cover_url TEXT,
            import_date TIMESTAMP,
            source_file VARCHAR(255)
        )
        """

        idx_defs = [
            (f"idx_{name}_oz_vendor_code", f'CREATE INDEX {{}} ON "{name}" (oz_vendor_code)'),
            (f"idx_{name}_primary_barcode", f'CREATE INDEX {{}} ON "{name}" (primary_barcode)'),
        ]
        index_sql: List[Tuple[str, str]] = []
        for idx_name, tmpl in idx_defs:
            index_sql.append((idx_name, tmpl.format(idx_name)))
        return TableSchema(name=name, create_sql=create, index_sql=index_sql)

    prod_full = _oz_products_full_schema()
    
    # WB products schema
    def _wb_products_schema() -> TableSchema:
        name = "wb_products"
        create = f"""
        CREATE TABLE IF NOT EXISTS "{name}" (
            group_id INTEGER,
            wb_article VARCHAR(100),
            wb_sku BIGINT,
            product_name VARCHAR(500),
            seller_category VARCHAR(200),
            brand VARCHAR(100),
            description TEXT,
            photos TEXT,
            video_url VARCHAR(500),
            gender VARCHAR(50),
            color VARCHAR(100),
            barcodes TEXT,
            primary_barcode VARCHAR(50),
            size VARCHAR(20),
            russian_size VARCHAR(20),
            weight_kg DECIMAL(8,3),
            package_height_cm DECIMAL(8,2),
            package_length_cm DECIMAL(8,2),
            package_width_cm DECIMAL(8,2),
            package_volume_cm3 DECIMAL(12,2),
            tnved_code VARCHAR(20),
            card_rating DECIMAL(3,1),
            labels TEXT,
            vat_rate VARCHAR(20),
            source_file VARCHAR(255)
        )
        """
        idx_defs = [
            (f"idx_{name}_wb_sku", f'CREATE INDEX {{}} ON "{name}" (wb_sku)'),
            (f"idx_{name}_primary_barcode", f'CREATE INDEX {{}} ON "{name}" (primary_barcode)'),
        ]
        index_sql: List[Tuple[str, str]] = []
        for idx_name, tmpl in idx_defs:
            index_sql.append((idx_name, tmpl.format(idx_name)))
        return TableSchema(name=name, create_sql=create, index_sql=index_sql)

    # WB prices schema
    def _wb_prices_schema() -> TableSchema:
        name = "wb_prices"
        create = f"""
        CREATE TABLE IF NOT EXISTS "{name}" (
            brand VARCHAR(100),
            category VARCHAR(150),
            wb_sku VARCHAR(50),
            wb_vendor_code VARCHAR(100),
            barcode_primary VARCHAR(50),
            wb_stock INTEGER,
            current_price DECIMAL(10,2),
            current_discount DECIMAL(5,2)
        )
        """
        idx_defs = [
            (f"idx_{name}_wb_sku", f'CREATE INDEX {{}} ON "{name}" (wb_sku)'),
            (f"idx_{name}_barcode_primary", f'CREATE INDEX {{}} ON "{name}" (barcode_primary)'),
        ]
        index_sql: List[Tuple[str, str]] = []
        for idx_name, tmpl in idx_defs:
            index_sql.append((idx_name, tmpl.format(idx_name)))
        return TableSchema(name=name, create_sql=create, index_sql=index_sql)

    wb_prod = _wb_products_schema()
    wb_prices_tbl = _wb_prices_schema()
    
    # Punta barcodes schema
    def _punta_barcodes_schema() -> TableSchema:
        name = "punta_barcodes"
        create = f"""
        CREATE TABLE IF NOT EXISTS "{name}" (
            collection VARCHAR(100),
            pn_article VARCHAR(100),
            product_type VARCHAR(50),
            external_code VARCHAR(50),
            size VARCHAR(100),
            barcode VARCHAR(50),
            tn_ved VARCHAR(50)
        )
        """
        idx_defs = [
            (f"idx_{name}_pn_article", f'CREATE INDEX {{}} ON "{name}" (pn_article)'),
            (f"idx_{name}_size", f'CREATE INDEX {{}} ON "{name}" (size)'),
            (f"idx_{name}_external_code", f'CREATE INDEX {{}} ON "{name}" (external_code)'),
            (f"idx_{name}_barcode", f'CREATE INDEX {{}} ON "{name}" (barcode)'),
        ]
        index_sql: List[Tuple[str, str]] = []
        for idx_name, tmpl in idx_defs:
            index_sql.append((idx_name, tmpl.format(idx_name)))
        return TableSchema(name=name, create_sql=create, index_sql=index_sql)

    punta_bc = _punta_barcodes_schema()

    # Punta products schema
    def _punta_products_schema() -> TableSchema:
        name = "punta_products"
        create = f"""
        CREATE TABLE IF NOT EXISTS "{name}" (
            collection VARCHAR(100),
            "un-id" VARCHAR(100),
            status VARCHAR(100),
            buyer VARCHAR(150),
            pn_article VARCHAR(100),
            group_code VARCHAR(100),
            original_code VARCHAR(100),
            external_code_list TEXT,
            cost_usd DECIMAL(10,2)
        )
        """
        idx_defs = [
            (f"idx_{name}_collection", f'CREATE INDEX {{}} ON "{name}" (collection)'),
            (f"idx_{name}_un_id", f'CREATE INDEX {{}} ON "{name}" ("un-id")'),
            (f"idx_{name}_pn_article", f'CREATE INDEX {{}} ON "{name}" (pn_article)'),
        ]
        index_sql: List[Tuple[str, str]] = []
        for idx_name, tmpl in idx_defs:
            index_sql.append((idx_name, tmpl.format(idx_name)))
        return TableSchema(name=name, create_sql=create, index_sql=index_sql)

    punta_prod = _punta_products_schema()

    # Punta products codes (normalized external_code → product row)
    def _punta_products_codes_schema() -> TableSchema:
        name = "punta_products_codes"
        # Minimal placeholder schema; real shape is created via CTAS in rebuild helper
        create = f"""
        CREATE TABLE IF NOT EXISTS "{name}" (
            external_code VARCHAR(50)
        )
        """

        idx_defs = [
            (f"idx_{name}_external_code", f'CREATE INDEX {{}} ON "{name}" (external_code)'),
        ]
        index_sql: List[Tuple[str, str]] = []
        for idx_name, tmpl in idx_defs:
            index_sql.append((idx_name, tmpl.format(idx_name)))
        return TableSchema(name=name, create_sql=create, index_sql=index_sql)

    punta_prod_codes = _punta_products_codes_schema()

    # Punta collections metadata (name, priority, active flag)
    def _punta_collections_schema() -> TableSchema:
        name = "punta_collections"
        create = f"""
        CREATE TABLE IF NOT EXISTS "{name}" (
            collection TEXT PRIMARY KEY,
            priority INTEGER NOT NULL,
            active BOOLEAN DEFAULT TRUE
        )
        """

        idx_defs = [
            (f"idx_{name}_priority", f'CREATE INDEX {{}} ON "{name}" (priority)'),
        ]
        index_sql: List[Tuple[str, str]] = []
        for idx_name, tmpl in idx_defs:
            index_sql.append((idx_name, tmpl.format(idx_name)))
        return TableSchema(name=name, create_sql=create, index_sql=index_sql)

    punta_colls = _punta_collections_schema()

    return {
        prod.name: prod,
        orders.name: orders,
        prod_full.name: prod_full,
        wb_prod.name: wb_prod,
        wb_prices_tbl.name: wb_prices_tbl,
        punta_bc.name: punta_bc,
        punta_prod.name: punta_prod,
        punta_prod_codes.name: punta_prod_codes,
        punta_colls.name: punta_colls,
    }


def init_schema(md_token: Optional[str] = None, md_database: Optional[str] = None) -> List[str]:
    messages: List[str] = []
    with get_connection(md_token=md_token, md_database=md_database) as con:
        for tbl in get_all_schemas().values():
            con.execute(tbl.create_sql)
            messages.append(f"ensured table {tbl.name}")
        # Lightweight migration: rename legacy column tn_vad -> tn_ved for punta_barcodes
        try:
            info = con.execute('PRAGMA table_info("punta_barcodes")').fetch_df()
            if not info.empty and (info["name"] == "tn_vad").any():
                con.execute('ALTER TABLE "punta_barcodes" RENAME COLUMN "tn_vad" TO "tn_ved"')
                messages.append("migrated punta_barcodes: tn_vad -> tn_ved")
        except Exception:
            # Best effort; ignore if table doesn't exist yet or ALTER not supported
            pass
    return messages


def rebuild_indexes(
    *,
    md_token: Optional[str] = None,
    md_database: Optional[str] = None,
    table: Optional[str] = None,
) -> List[str]:
    """Drop and recreate indexes for given table or all.

    DuckDB may drop indexes on CREATE OR REPLACE TABLE; this restores them.
    """
    messages: List[str] = []
    schemas = get_all_schemas()
    targets: Iterable[TableSchema]
    if table:
        ts = schemas.get(table)
        if not ts:
            return [f"no schema known for table {table}"]
        targets = [ts]
    else:
        targets = schemas.values()

    with get_connection(md_token=md_token, md_database=md_database) as con:
        for ts in targets:
            for idx_name, create_sql in ts.index_sql:
                con.execute(f"DROP INDEX IF EXISTS {idx_name}")
                con.execute(create_sql)
                messages.append(f"rebuilt index {idx_name} on {ts.name}")
    return messages


def rebuild_punta_products_codes(
    *,
    md_token: Optional[str] = None,
    md_database: Optional[str] = None,
) -> List[str]:
    """(Re)build normalized table punta_products_codes from punta_products.

    - Expands JSON array external_code_list into rows and attaches the full product row.
    - Uses CREATE OR REPLACE TABLE to keep the table in sync with punta_products schema
      (new columns will automatically appear in punta_products_codes).
    - Rebuilds index on external_code for performant lookups.
    """
    messages: List[str] = []
    with get_connection(md_token=md_token, md_database=md_database) as con:
        con.execute(
            r"""
            CREATE OR REPLACE TABLE punta_products_codes AS
            SELECT
                json_extract_string(e.value, '$') AS external_code,
                p.*
            FROM punta_products AS p,
                 json_each(COALESCE(p.external_code_list, '[]')) AS e
            """
        )
        messages.append("rebuilt punta_products_codes via CTAS")

    # Ensure indexes exist (DuckDB can drop indexes on replace)
    messages.extend(rebuild_indexes(md_token=md_token, md_database=md_database, table="punta_products_codes"))
    return messages
