"""Test script to verify duplicate handling in similarity algorithm."""
import pandas as pd
from dataforge.matching_helpers import add_merge_fields_for_similarity

# Create test data simulating similarity results with duplicates
# Scenario: 
# - Group 1: wb_sku 100, 200, 300 (min=100)
# - wb_sku 200 has THREE oz items with size 30 (scores: 95, 85, 80)
# - wb_sku 300 has TWO oz items with size 42 (scores: 90, 70)

test_data = [
    # Group 1, wb_sku=100, unique sizes
    {"group_number": 1, "wb_sku": 100, "oz_sku": 1001, "oz_vendor_code": "X-Синий-A", "oz_manufacturer_size": "28", "match_score": 98},
    {"group_number": 1, "wb_sku": 100, "oz_sku": 1002, "oz_vendor_code": "X-Синий-B", "oz_manufacturer_size": "29", "match_score": 97},
    
    # Group 1, wb_sku=200, THREE items with size 30 (duplicates)
    {"group_number": 1, "wb_sku": 200, "oz_sku": 2001, "oz_vendor_code": "Y-Красный-A", "oz_manufacturer_size": "30", "match_score": 95},
    {"group_number": 1, "wb_sku": 200, "oz_sku": 2002, "oz_vendor_code": "Y-Красный-B", "oz_manufacturer_size": "30", "match_score": 85},
    {"group_number": 1, "wb_sku": 200, "oz_sku": 2003, "oz_vendor_code": "Y-Красный-C", "oz_manufacturer_size": "30", "match_score": 80},
    {"group_number": 1, "wb_sku": 200, "oz_sku": 2004, "oz_vendor_code": "Y-Красный-D", "oz_manufacturer_size": "31", "match_score": 94},
    
    # Group 1, wb_sku=300, TWO items with size 42 (one duplicate)
    {"group_number": 1, "wb_sku": 300, "oz_sku": 3001, "oz_vendor_code": "Z-Зеленый-A", "oz_manufacturer_size": "42", "match_score": 90},
    {"group_number": 1, "wb_sku": 300, "oz_sku": 3002, "oz_vendor_code": "Z-Зеленый-B", "oz_manufacturer_size": "42", "match_score": 70},
    {"group_number": 1, "wb_sku": 300, "oz_sku": 3003, "oz_vendor_code": "Z-Зеленый-C", "oz_manufacturer_size": "43", "match_score": 88},
]

df = pd.DataFrame(test_data)
print("=" * 80)
print("INPUT DATA:")
print("=" * 80)
print(df[["group_number", "wb_sku", "oz_sku", "oz_vendor_code", "oz_manufacturer_size", "match_score"]])
print()

# Apply the new function
result = add_merge_fields_for_similarity(df)

print("=" * 80)
print("OUTPUT DATA:")
print("=" * 80)
print(result[["group_number", "wb_sku", "oz_sku", "oz_manufacturer_size", "merge_code", "merge_color", "match_score"]])
print()

# Verify expectations
print("=" * 80)
print("VERIFICATION:")
print("=" * 80)

# Check: wb_sku=200, size=30 should have one C- and two D- codes
size_30_items = result[(result["wb_sku"] == 200) & (result["oz_manufacturer_size"] == "30")]
print(f"\nwb_sku=200, size=30 items:")
print(f"Expected merge_code: 1 primary 'C-64' (min group wb=100), 2 duplicates 'D-C8' (own wb=200)")
print(f"Expected merge_color: all should have 'Красный; C8' (own wb_sku hex)")
for _, row in size_30_items.iterrows():
    print(f"  oz_sku={row['oz_sku']}, match_score={row['match_score']}, merge_code={row['merge_code']}, merge_color={row['merge_color']}, group_number={row['group_number']}")

# Check: wb_sku=300, size=42 should have one C- and one D- code
size_42_items = result[(result["wb_sku"] == 300) & (result["oz_manufacturer_size"] == "42")]
print(f"\nwb_sku=300, size=42 items:")
print(f"Expected merge_code: 1 primary 'C-64' (min group wb=100), 1 duplicate 'D-12C' (own wb=300)")
print(f"Expected merge_color: all should have 'Зеленый; 12C' (own wb_sku hex)")
for _, row in size_42_items.iterrows():
    print(f"  oz_sku={row['oz_sku']}, match_score={row['match_score']}, merge_code={row['merge_code']}, merge_color={row['merge_color']}, group_number={row['group_number']}")

# Check: All unique size items should have C- prefix with min group wb_sku (64 = hex(100))
# But merge_color should use OWN wb_sku hex
unique_size_items = result[result["oz_sku"].isin([1001, 1002, 2004, 3003])]
print(f"\nUnique size items:")
print(f"Expected: merge_code uses min group wb (C-64), merge_color uses own wb hex")
for _, row in unique_size_items.iterrows():
    own_hex = format(int(row['wb_sku']), 'X')
    print(f"  oz_sku={row['oz_sku']}, wb_sku={row['wb_sku']} (hex={own_hex}), size={row['oz_manufacturer_size']}, merge_code={row['merge_code']}, merge_color={row['merge_color']}")

# Check: Duplicates should have different group_numbers
dup_groups = result[result["merge_code"].str.startswith("D-", na=False)]["group_number"].unique()
primary_groups = result[result["merge_code"].str.startswith("C-", na=False)]["group_number"].unique()
print(f"\nPrimary group_numbers: {sorted(primary_groups)}")
print(f"Duplicate group_numbers: {sorted(dup_groups)}")
print(f"No overlap: {len(set(primary_groups) & set(dup_groups)) == 0}")

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
