from __future__ import annotations

import pandas as pd

from dataforge.imports.google_sheets import to_export_csv_url, dedup_by_wb_sku_first


def test_to_export_csv_url_basic():
    url = "https://docs.google.com/spreadsheets/d/14A_-tWHcBQBzgh6gY6yml3OyLXVjgSXFIUfQfYV3Soo/edit?usp=sharing"
    out = to_export_csv_url(url)
    assert out == (
        "https://docs.google.com/spreadsheets/d/14A_-tWHcBQBzgh6gY6yml3OyLXVjgSXFIUfQfYV3Soo/export?format=csv"
    )


def test_dedup_by_wb_sku_first_keeps_first():
    df = pd.DataFrame(
        {
            "wb_sku": ["1", "2", "1", "3", "2"],
            "value": ["a", "b", "c", "d", "e"],
        }
    )
    out = dedup_by_wb_sku_first(df)
    # Expect first occurrences for 1->a, 2->b, 3->d
    assert out.reset_index(drop=True).to_dict(orient="list") == {
        "wb_sku": ["1", "2", "3"],
        "value": ["a", "b", "d"],
    }

