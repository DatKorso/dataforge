"""Debug script to test duplicate marking with real-like data."""
from __future__ import annotations

import pandas as pd
from dataforge.matching_helpers import add_merge_fields, mark_duplicate_sizes

# Simulate what happens in the page for basic algorithm

# Step 1: Data comes from search_matches (no merge_code yet)
print("=" * 80)
print("STEP 1: Initial data from search_matches")
print("=" * 80)
df = pd.DataFrame([
    {"wb_sku": "168567573", "oz_sku": "1001", "oz_vendor_code": "1-Red-3", "oz_manufacturer_size": "30", "match_score": 100},
    {"wb_sku": "168567573", "oz_sku": "1002", "oz_vendor_code": "2-Red-4", "oz_manufacturer_size": "30", "match_score": 85},
    {"wb_sku": "168567573", "oz_sku": "1003", "oz_vendor_code": "3-Red-5", "oz_manufacturer_size": "32", "match_score": 90},
])
print(df[["wb_sku", "oz_sku", "oz_manufacturer_size", "match_score"]])
print()

# Step 2: Add merge fields (happens in the chunk loop)
print("=" * 80)
print("STEP 2: After add_merge_fields")
print("=" * 80)
df = add_merge_fields(df, wb_sku_col="wb_sku", oz_vendor_col="oz_vendor_code")
print(df[["wb_sku", "oz_sku", "oz_manufacturer_size", "match_score", "merge_code", "group_number"]])
print()

# Step 3: Recalculate group_number (in case of multiple chunks)
print("=" * 80)
print("STEP 3: Recalculate group_number based on merge_code")
print("=" * 80)
unique_merge_codes = sorted(df["merge_code"].unique())
merge_code_to_group = {code: idx + 1 for idx, code in enumerate(unique_merge_codes)}
df["group_number"] = df["merge_code"].map(merge_code_to_group)
print(df[["wb_sku", "oz_sku", "oz_manufacturer_size", "match_score", "merge_code", "group_number"]])
print()

# Step 4: Mark duplicates (when checkbox is OFF)
print("=" * 80)
print("STEP 4: After mark_duplicate_sizes with grouping_column='wb_sku'")
print("=" * 80)
df_marked = mark_duplicate_sizes(df, primary_prefix="B", duplicate_prefix="D", grouping_column="wb_sku")
print(df_marked[["wb_sku", "oz_sku", "oz_manufacturer_size", "match_score", "merge_code", "group_number"]])
print()

# Verify results
print("=" * 80)
print("VERIFICATION")
print("=" * 80)
size_30 = df_marked[df_marked["oz_manufacturer_size"] == "30"].sort_values("match_score", ascending=False)
print(f"Size 30 items: {len(size_30)}")
for idx, row in size_30.iterrows():
    prefix = row["merge_code"].split("-")[0]
    print(f"  oz_sku={row['oz_sku']}, score={row['match_score']}, merge_code={row['merge_code']}, prefix={prefix}, group={row['group_number']}")

size_30_prefixes = size_30["merge_code"].str.split("-").str[0].tolist()
if "B" in size_30_prefixes and "D" in size_30_prefixes:
    print("✅ SUCCESS: Found both B and D prefixes for size 30 duplicates")
else:
    print(f"❌ FAILURE: Expected B and D prefixes, got: {size_30_prefixes}")
