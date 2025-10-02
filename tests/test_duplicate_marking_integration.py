"""Integration test for duplicate size marking in both algorithms."""
from __future__ import annotations

import pandas as pd
from dataforge.matching_helpers import add_merge_fields, mark_duplicate_sizes


def test_basic_algorithm_duplicate_marking():
    """Test that basic algorithm (B prefix) correctly marks duplicates with D."""
    # Simulate data from search_matches (basic algorithm)
    df = pd.DataFrame([
        {"wb_sku": "123", "oz_sku": "1001", "oz_vendor_code": "1-Red-3", "oz_manufacturer_size": "M", "match_score": 95},
        {"wb_sku": "123", "oz_sku": "1002", "oz_vendor_code": "2-Red-4", "oz_manufacturer_size": "M", "match_score": 85},
        {"wb_sku": "123", "oz_sku": "1003", "oz_vendor_code": "3-Red-5", "oz_manufacturer_size": "L", "match_score": 90},
    ])
    
    # Step 1: Add merge fields (simulates the processing in the page)
    df = add_merge_fields(df, wb_sku_col="wb_sku", oz_vendor_col="oz_vendor_code")
    
    # Check all have B prefix initially
    assert all(df["merge_code"].str.startswith("B-"))
    
    # Step 2: Mark duplicates (when checkbox is OFF) - use wb_sku for grouping
    df_marked = mark_duplicate_sizes(df, primary_prefix="B", duplicate_prefix="D", grouping_column="wb_sku")
    
    # Check results
    # Size M: first should keep B, second should get D
    size_m_items = df_marked[df_marked["oz_manufacturer_size"] == "M"].sort_values("match_score", ascending=False)
    assert len(size_m_items) == 2
    assert size_m_items.iloc[0]["merge_code"].startswith("B-"), "First M should have B prefix"
    assert size_m_items.iloc[0]["match_score"] == 95
    assert size_m_items.iloc[1]["merge_code"].startswith("D-"), "Second M should have D prefix"
    assert size_m_items.iloc[1]["match_score"] == 85
    
    # Size L: should keep B (no duplicates)
    size_l_items = df_marked[df_marked["oz_manufacturer_size"] == "L"]
    assert len(size_l_items) == 1
    assert size_l_items.iloc[0]["merge_code"].startswith("B-")
    
    # Check group numbers are different for duplicate
    assert size_m_items.iloc[0]["group_number"] != size_m_items.iloc[1]["group_number"]


def test_similarity_algorithm_duplicate_marking():
    """Test that similarity algorithm (C prefix) correctly marks duplicates with D."""
    # Simulate data from search_similar_matches (already has C prefix and group_number)
    df = pd.DataFrame([
        {"wb_sku": "123", "oz_sku": "1001", "oz_vendor_code": "1-Blue-3", 
         "oz_manufacturer_size": "30", "match_score": 100, "merge_code": "C-ABC123", "group_number": 1},
        {"wb_sku": "123", "oz_sku": "1002", "oz_vendor_code": "2-Blue-4", 
         "oz_manufacturer_size": "30", "match_score": 85, "merge_code": "C-ABC123", "group_number": 1},
        {"wb_sku": "456", "oz_sku": "1003", "oz_vendor_code": "3-Blue-5", 
         "oz_manufacturer_size": "32", "match_score": 90, "merge_code": "C-DEF456", "group_number": 1},
    ])
    
    # Mark duplicates (when checkbox is OFF)
    df_marked = mark_duplicate_sizes(df, primary_prefix="C", duplicate_prefix="D")
    
    # Check results
    # Size 30: first should keep C, second should get D
    size_30_items = df_marked[df_marked["oz_manufacturer_size"] == "30"].sort_values("match_score", ascending=False)
    assert len(size_30_items) == 2
    assert size_30_items.iloc[0]["merge_code"].startswith("C-"), "First 30 should have C prefix"
    assert size_30_items.iloc[0]["match_score"] == 100
    assert size_30_items.iloc[1]["merge_code"].startswith("D-"), "Second 30 should have D prefix"
    assert size_30_items.iloc[1]["match_score"] == 85
    
    # Size 32: should keep C (no duplicates)
    size_32_items = df_marked[df_marked["oz_manufacturer_size"] == "32"]
    assert len(size_32_items) == 1
    assert size_32_items.iloc[0]["merge_code"].startswith("C-")


def test_multiple_duplicates_suffix():
    """Test that multiple duplicates get _N suffix correctly."""
    df = pd.DataFrame([
        {"wb_sku": "123", "oz_sku": "1001", "oz_vendor_code": "1-Black-3", "oz_manufacturer_size": "XL", 
         "match_score": 100, "merge_code": "B-7B", "group_number": 1},
        {"wb_sku": "123", "oz_sku": "1002", "oz_vendor_code": "2-Black-4", "oz_manufacturer_size": "XL", 
         "match_score": 90, "merge_code": "B-7B", "group_number": 1},
        {"wb_sku": "123", "oz_sku": "1003", "oz_vendor_code": "3-Black-5", "oz_manufacturer_size": "XL", 
         "match_score": 80, "merge_code": "B-7B", "group_number": 1},
    ])
    
    df_marked = mark_duplicate_sizes(df, primary_prefix="B", duplicate_prefix="D")
    
    # Sort by match_score to check order
    df_sorted = df_marked.sort_values("match_score", ascending=False)
    
    # First should keep B
    assert df_sorted.iloc[0]["merge_code"].startswith("B-")
    assert "_" not in df_sorted.iloc[0]["merge_code"]
    
    # Second should get D with _2
    assert df_sorted.iloc[1]["merge_code"].startswith("D-")
    assert "_2" in df_sorted.iloc[1]["merge_code"]
    
    # Third should get D with _3
    assert df_sorted.iloc[2]["merge_code"].startswith("D-")
    assert "_3" in df_sorted.iloc[2]["merge_code"]



def test_group_number_recalculation_before_marking():
    """Test that group_number is recalculated correctly before marking duplicates.
    
    This simulates the scenario where data from multiple chunks is concatenated,
    and group_number values may overlap between chunks.
    """
    # Simulate data from two chunks that were processed separately
    # Chunk 1: wb_sku 123
    chunk1 = pd.DataFrame([
        {"wb_sku": "123", "oz_sku": "1001", "oz_vendor_code": "1-Red-3", 
         "oz_manufacturer_size": "M", "match_score": 95, "merge_code": "B-7B", "group_number": 1},
        {"wb_sku": "123", "oz_sku": "1002", "oz_vendor_code": "2-Red-4", 
         "oz_manufacturer_size": "M", "match_score": 85, "merge_code": "B-7B", "group_number": 1},
    ])
    
    # Chunk 2: wb_sku 456 (also gets group_number 1 because it was processed separately!)
    chunk2 = pd.DataFrame([
        {"wb_sku": "456", "oz_sku": "2001", "oz_vendor_code": "1-Blue-5", 
         "oz_manufacturer_size": "L", "match_score": 90, "merge_code": "B-1C8", "group_number": 1},
        {"wb_sku": "456", "oz_sku": "2002", "oz_vendor_code": "2-Blue-6", 
         "oz_manufacturer_size": "L", "match_score": 80, "merge_code": "B-1C8", "group_number": 1},
    ])
    
    # Concatenate (simulates what happens in the page)
    df = pd.concat([chunk1, chunk2], ignore_index=True)
    
    # Problem: both groups have group_number=1!
    assert df[df["wb_sku"] == "123"]["group_number"].iloc[0] == 1
    assert df[df["wb_sku"] == "456"]["group_number"].iloc[0] == 1
    
    # Solution: Recalculate group_number based on unique merge_code
    unique_merge_codes = sorted(df["merge_code"].unique())
    merge_code_to_group = {code: idx + 1 for idx, code in enumerate(unique_merge_codes)}
    df["group_number"] = df["merge_code"].map(merge_code_to_group)
    
    # Now group numbers should be different
    group_123 = df[df["wb_sku"] == "123"]["group_number"].iloc[0]
    group_456 = df[df["wb_sku"] == "456"]["group_number"].iloc[0]
    assert group_123 != group_456, "Different merge_code should have different group_number"
    
    # Now mark duplicates
    from dataforge.matching_helpers import mark_duplicate_sizes
    df_marked = mark_duplicate_sizes(df, primary_prefix="B", duplicate_prefix="D")
    
    # Check that duplicates within each group are marked correctly
    # Group with wb_sku 123: size M duplicates
    group_123_data = df_marked[df_marked["wb_sku"] == "123"].sort_values("match_score", ascending=False)
    assert group_123_data.iloc[0]["merge_code"].startswith("B-"), "First M should keep B"
    assert group_123_data.iloc[1]["merge_code"].startswith("D-"), "Second M should get D"
    
    # Group with wb_sku 456: size L duplicates
    group_456_data = df_marked[df_marked["wb_sku"] == "456"].sort_values("match_score", ascending=False)
    assert group_456_data.iloc[0]["merge_code"].startswith("B-"), "First L should keep B"
    assert group_456_data.iloc[1]["merge_code"].startswith("D-"), "Second L should get D"
