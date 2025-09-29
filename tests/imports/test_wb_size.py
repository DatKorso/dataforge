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


def test_wb_products_size_truncated_to_first_two_chars():
    row = _normalize_single_row(
        "wb_products",
        {
            "Артикул продавца": ["WB-001"],
            "Артикул WB": ["1001"],
            "Размер": ["37→37.5ru"],
        },
    )
    assert row["size"] == "37"


def test_wb_products_size_truncated_simple():
    row = _normalize_single_row(
        "wb_products",
        {
            "Артикул продавца": ["WB-002"],
            "Артикул WB": ["1002"],
            "Размер": ["39ru"],
        },
    )
    assert row["size"] == "39"

