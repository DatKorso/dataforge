"""
Test import of unique values from punta_products.
"""

from dataforge.attributes import import_unique_values_from_punta

print("Testing import of unique values from punta_products...")

categories = ["upper_material", "lining_material", "insole_material", "outsole_material"]

for category in categories:
    print(f"\n{'='*60}")
    print(f"Category: {category}")
    print('='*60)
    
    try:
        df = import_unique_values_from_punta(category)
        print(f"Found {len(df)} unique values:")
        if not df.empty:
            print(df[["id", "punta_value"]].head(10).to_string(index=False))
            if len(df) > 10:
                print(f"... and {len(df) - 10} more")
    except Exception as exc:
        print(f"Error: {exc}")

print("\n✅ Test completed!")
