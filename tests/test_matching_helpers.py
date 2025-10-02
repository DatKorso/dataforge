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



def test_mark_duplicate_sizes_basic():
    """Test marking duplicates with C/D prefixes."""
    df = pd.DataFrame([
        {"group_number": 1, "oz_manufacturer_size": "30", "merge_code": "C-ABC123", "match_score": 100},
        {"group_number": 1, "oz_manufacturer_size": "30", "merge_code": "C-ABC123", "match_score": 80},
        {"group_number": 1, "oz_manufacturer_size": "32", "merge_code": "C-ABC123", "match_score": 90},
    ])
    from dataforge.matching_helpers import mark_duplicate_sizes
    
    out = mark_duplicate_sizes(df, primary_prefix="C", duplicate_prefix="D")
    
    # First size 30 should keep C prefix
    first_30 = out[out["match_score"] == 100].iloc[0]
    assert first_30["merge_code"].startswith("C-")
    assert first_30["group_number"] == 1
    
    # Second size 30 should get D prefix (no _2 suffix for only 2 duplicates)
    second_30 = out[out["match_score"] == 80].iloc[0]
    assert second_30["merge_code"].startswith("D-")
    assert "_2" not in second_30["merge_code"]  # Only two items, no suffix
    assert second_30["group_number"] != 1  # Different group
    
    # Size 32 should keep C prefix (no duplicates)
    size_32 = out[out["match_score"] == 90].iloc[0]
    assert size_32["merge_code"].startswith("C-")
    assert size_32["group_number"] == 1


def test_mark_duplicate_sizes_multiple_duplicates():
    """Test marking multiple duplicates with _N suffix."""
    df = pd.DataFrame([
        {"group_number": 1, "oz_manufacturer_size": "30", "merge_code": "C-XYZ789", "match_score": 100},
        {"group_number": 1, "oz_manufacturer_size": "30", "merge_code": "C-XYZ789", "match_score": 80},
        {"group_number": 1, "oz_manufacturer_size": "30", "merge_code": "C-XYZ789", "match_score": 60},
    ])
    from dataforge.matching_helpers import mark_duplicate_sizes
    
    out = mark_duplicate_sizes(df, primary_prefix="C", duplicate_prefix="D")
    
    # Sort by match_score to check order
    out_sorted = out.sort_values("match_score", ascending=False)
    
    # First (best) should keep C prefix
    assert out_sorted.iloc[0]["merge_code"].startswith("C-")
    assert out_sorted.iloc[0]["group_number"] == 1
    
    # Second should get D with _2
    assert out_sorted.iloc[1]["merge_code"].startswith("D-")
    assert "_2" in out_sorted.iloc[1]["merge_code"]
    
    # Third should get D with _3
    assert out_sorted.iloc[2]["merge_code"].startswith("D-")
    assert "_3" in out_sorted.iloc[2]["merge_code"]


def test_mark_duplicate_sizes_multiple_groups():
    """Test that duplicates are only marked within the same group."""
    df = pd.DataFrame([
        {"group_number": 1, "oz_manufacturer_size": "30", "merge_code": "C-AAA", "match_score": 100},
        {"group_number": 1, "oz_manufacturer_size": "30", "merge_code": "C-AAA", "match_score": 80},
        {"group_number": 2, "oz_manufacturer_size": "30", "merge_code": "C-BBB", "match_score": 90},
    ])
    from dataforge.matching_helpers import mark_duplicate_sizes
    
    out = mark_duplicate_sizes(df, primary_prefix="C", duplicate_prefix="D")
    
    # Group 1: first size 30 keeps C, second gets D
    group1 = out[out["merge_code"].str.contains("AAA")].sort_values("match_score", ascending=False)
    assert group1.iloc[0]["merge_code"].startswith("C-")
    assert group1.iloc[1]["merge_code"].startswith("D-")
    
    # Group 2: only one size 30, keeps C
    group2 = out[out["merge_code"].str.contains("BBB")]
    assert group2.iloc[0]["merge_code"].startswith("C-")
