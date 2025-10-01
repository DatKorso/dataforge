from __future__ import annotations

import pandas as pd
from dataforge.matching_helpers import (
    add_merge_fields,
    generate_merge_code,
    parse_color_from_oz_vendor_code,
)


def test_generate_merge_code_numeric():
    code, hx, fallback = generate_merge_code("1234")
    assert hx == "4D2"
    assert code == "B-4D2"
    assert fallback is False


def test_generate_merge_code_non_numeric():
    code, hx, fallback = generate_merge_code("ABC-XYZ")
    assert code.startswith("B-")
    assert len(hx) > 0
    assert fallback is True


def test_parse_color_from_oz_vendor_code_ok():
    color, ok = parse_color_from_oz_vendor_code("123-Blue-456")
    assert ok is True
    assert color == "Blue"


def test_parse_color_from_oz_vendor_code_missing():
    color, ok = parse_color_from_oz_vendor_code("no-dash")
    assert ok is False
    assert color is None


def test_add_merge_fields_integration():
    df = pd.DataFrame({"wb_sku": ["123", "ABC-1"], "oz_vendor_code": ["1-Red-3", "badformat"]})
    out = add_merge_fields(df)
    assert "merge_code" in out.columns
    assert "merge_color" in out.columns
    assert out.loc[0, "merge_code"] == "B-7B"
    # second row: color missing -> merge_color equals hex
    assert out.loc[1, "merge_parse_ok"] in (False,)


def test_dedupe_sizes_keep_highest_score():
    # rows with same wb_sku and wb_size -> keep one with highest match_score
    df = pd.DataFrame(
        [
            {"wb_sku": "1", "wb_size": "M", "match_score": 50},
            {"wb_sku": "1", "wb_size": "M", "match_score": 80},
            {"wb_sku": "1", "wb_size": "L", "match_score": 60},
        ]
    )
    from dataforge.matching_helpers import dedupe_sizes

    out = dedupe_sizes(df, input_type="wb_sku")
    # should contain 2 rows: M (score 80) and L (60)
    assert len(out) == 2
    assert 80 in out["match_score"].values
    assert 60 in out["match_score"].values
