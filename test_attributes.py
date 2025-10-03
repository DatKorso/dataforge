"""
Test script for attributes mapping functionality.
"""

from dataforge.schema import init_schema
from dataforge.attributes import (
    get_attributes_by_category,
    save_category_mappings,
    export_attributes_to_excel,
)
import pandas as pd
import toml
import os


def _load_secrets():
    # Prefer environment variables, fallback to .streamlit/secrets.toml
    md_token = os.environ.get("MOTHERDUCK_TOKEN")
    md_database = os.environ.get("MD_DATABASE")
    if md_token and md_database:
        return md_token, md_database
    try:
        s = toml.load(".streamlit/secrets.toml")
        return s.get("md_token"), s.get("md_database")
    except Exception:
        return md_token, md_database


md_token, md_database = _load_secrets()

print("1. Initializing schema...")
messages = init_schema(md_token=md_token, md_database=md_database)
for msg in messages:
    print(f"   - {msg}")

print("\n2. Testing category: upper_material")
# Create sample data
sample_data = pd.DataFrame({
    "id": [1, 2, 3],
    "punta_value": ["Натуральная кожа", "Текстиль", "Замша"],
    "wb_value": ["натуральная кожа", "текстиль", "замша"],
    "oz_value": ["Кожа", "Ткань", "Замша"],
    "lamoda_value": ["Leather", "Textile", "Suede"],
    "description": ["Для описания: кожаная обувь", None, None],
    "additional_field": ["Материал: кожа", "Материал: ткань", "Материал: замша"],
})

print("   Saving sample data...")
save_category_mappings("upper_material", sample_data, md_token=md_token, md_database=md_database)
print("   ✓ Saved")

print("\n3. Reading back data...")
df = get_attributes_by_category("upper_material", md_token=md_token, md_database=md_database)
print(f"   Found {len(df)} records:")
print(df[["id", "punta_value", "wb_value", "oz_value", "lamoda_value"]].to_string(index=False))

print("\n4. Testing export to Excel...")
excel_file = export_attributes_to_excel(md_token=md_token, md_database=md_database)
print(f"   ✓ Generated Excel file ({len(excel_file.getvalue())} bytes)")

print("\n✅ All tests passed!")
