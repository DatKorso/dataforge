from __future__ import annotations

import json

import pandas as pd
from dataforge.imports.registry import get_registry
from dataforge.imports.validator import normalize_and_validate


def _normalize_single_row(spec_id: str, payload: dict[str, list[object]]):
    spec = get_registry()[spec_id]
    df = pd.DataFrame(payload)
    result = normalize_and_validate(df, spec)
    assert result.errors == []
    assert result.rows_valid == 1
    return result.df_normalized.iloc[0]


def test_wb_products_primary_barcode_uses_last_entry():
    row = _normalize_single_row(
        "wb_products",
        {
            "Артикул продавца": ["WB-001"],
            "Артикул WB": ["1001"],
            "Баркод": ["111;222;333"],
        },
    )
    assert row["primary_barcode"] == "333"
    assert json.loads(row["barcodes"]) == ["111", "222", "333"]


def test_oz_products_full_primary_barcode_uses_last_entry():
    row = _normalize_single_row(
        "ozon_products_full",
        {
            "Артикул*": ["OZ-001"],
            "Штрихкод (Серийный номер / EAN)": ["444;555;666"],
        },
    )
    assert row["primary_barcode"] == "666"
    assert json.loads(row["barcodes"]) == ["444", "555", "666"]
