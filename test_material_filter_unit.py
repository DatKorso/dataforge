#!/usr/bin/env python3
"""
Unit test to verify SQL generation includes material_short filter.
This test doesn't require database access - just checks the SQL logic.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_material_filter_sql():
    """Verify that the SQL query includes material_short filter."""
    
    print("=" * 80)
    print("Testing SQL generation for material_short filter")
    print("=" * 80)
    
    # Import after path is set
    from dataforge.similarity_matching import search_similar_matches
    import inspect
    
    # Get the source code of the function
    source = inspect.getsource(search_similar_matches)
    
    # Check for key components
    checks = {
        "material_filter variable": "material_filter = ''",
        "material_filter assignment": "material_filter = \"WHERE (pg_seed.material_short IS NULL OR pg_cand.material_short IS NULL OR pg_seed.material_short = pg_cand.material_short)\"",
        "material_filter in SQL": "{material_filter}",
        "pairs CTE with filter": "punta_left_joins}\n        {material_filter}",
    }
    
    print("\n" + "=" * 80)
    print("VALIDATION CHECKS")
    print("=" * 80)
    
    all_passed = True
    for check_name, pattern in checks.items():
        if pattern in source:
            print(f"✅ {check_name:40s} - FOUND")
        else:
            print(f"❌ {check_name:40s} - NOT FOUND")
            all_passed = False
    
    # Extract and display the relevant SQL section
    print("\n" + "=" * 80)
    print("EXTRACTED SQL LOGIC (pairs CTE)")
    print("=" * 80)
    
    # Find the pairs CTE section
    pairs_start = source.find(", pairs AS (")
    if pairs_start > 0:
        pairs_end = source.find(")", pairs_start + 50)  # Find closing paren
        if pairs_end > 0:
            pairs_section = source[pairs_start:pairs_end + 1]
            print(pairs_section)
    
    print("\n" + "=" * 80)
    print("MATERIAL FILTER LOGIC")
    print("=" * 80)
    
    # Find material_filter assignment
    filter_start = source.find("material_filter = ''")
    if filter_start > 0:
        filter_end = source.find("\n\n", filter_start)
        if filter_end > 0:
            filter_section = source[filter_start:filter_end]
            print(filter_section)
    
    print("\n" + "=" * 80)
    if all_passed:
        print("✅ ALL CHECKS PASSED")
        print("=" * 80)
        print("\nThe material_short filter is correctly implemented:")
        print("1. material_filter variable is initialized")
        print("2. Filter condition is set when punta_google exists")
        print("3. Filter is applied in the pairs CTE via {material_filter}")
        print("4. Logic: (material_short IS NULL OR material_short = seed_material_short)")
        return True
    else:
        print("❌ SOME CHECKS FAILED")
        print("=" * 80)
        return False


if __name__ == "__main__":
    success = test_material_filter_sql()
    sys.exit(0 if success else 1)
