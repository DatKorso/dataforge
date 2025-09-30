"""Shared SQL fragments and templates used by dataforge.matching.

This module centralizes repeated CTE fragments (punta map, punta selects/joins)
so other modules can import them and avoid duplicated string literals.
"""
from __future__ import annotations

PUNTA_CTE = r"""
ext_barcodes AS (
    SELECT external_code,
           barcode
    FROM punta_barcodes
),
punta_map AS (
    SELECT pb.barcode,
           pb.external_code,
           ppc.collection
    FROM punta_barcodes pb
    LEFT JOIN punta_products_codes ppc ON ppc.external_code = pb.external_code
)
"""

PUNTA_SELECT = r"""
           , pm_oz.collection AS punta_collection_oz
           , pm_oz.external_code AS punta_external_code_oz
           , pm_wb.collection AS punta_collection_wb
           , pm_wb.external_code AS punta_external_code_wb
           , (pm_oz.external_code = pm_wb.external_code) AS punta_external_equal
"""

PUNTA_JOINS = r"""
LEFT JOIN punta_map pm_oz ON pm_oz.barcode = COALESCE(o.oz_primary_barcode, o.barcode)
LEFT JOIN punta_map pm_wb ON pm_wb.barcode = COALESCE(w.wb_primary_barcode, w.barcode)
"""

PUNTA_JOINS_BARCODES = r"""
    LEFT JOIN punta_map pm_oz ON pm_oz.barcode = COALESCE(o.oz_primary_barcode, o.barcode)
    LEFT JOIN punta_map pm_wb ON pm_wb.barcode = COALESCE(w.wb_primary_barcode, w.barcode)
"""
