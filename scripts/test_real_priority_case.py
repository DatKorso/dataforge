"""Integration test with real DB data for wb_sku=168568189.

This test validates the fix:
- Old barcode: 4815550505853 → ОЗ-23 (priority=10, older)
- New barcode: 4815694741544 → ОЗ-25 (priority=14, newer)
- Expected: primary_barcode should be 4815694741544
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from dataforge.imports.punta_priority import enrich_primary_barcode_by_punta


def test_real_case_wb_sku_168568189():
    """Test the actual case that revealed the bug."""
    print("=" * 80)
    print("🧪 INTEGRATION TEST: wb_sku=168568189")
    print("=" * 80)
    
    # Load credentials
    try:
        import streamlit as st
        md_token = st.secrets.get("md_token")
        md_database = st.secrets.get("md_database")
    except Exception:
        import os
        md_token = os.environ.get("MOTHERDUCK_TOKEN")
        md_database = os.environ.get("MOTHERDUCK_DATABASE", "dataforge")
    
    import pytest

    if not md_token:
        pytest.skip("No MotherDuck token found in streamlit.secrets or MOTHERDUCK_TOKEN env")
    
    # Test data: wb_sku with two barcodes from different collections
    df_test = pd.DataFrame({
        "wb_sku": [168568189],
        "barcodes": [json.dumps(["4815550505853", "4815694741544"])],
    })
    
    print("\n📋 INPUT DATA:")
    print(f"  wb_sku: {df_test['wb_sku'].values[0]}")
    print(f"  barcodes: {df_test['barcodes'].values[0]}")
    print(f"    - 4815550505853 (ОЗ-23, priority=10, older)")
    print(f"    - 4815694741544 (ОЗ-25, priority=14, newer)")
    
    # Run the enrichment
    print("\n🔄 RUNNING ENRICHMENT...")
    result = enrich_primary_barcode_by_punta(
        df_test,
        md_token=md_token,
        md_database=md_database,
    )
    
    selected = result["primary_barcode"].values[0]
    print(f"\n✅ SELECTED primary_barcode: {selected}")
    
    # Validate
    expected = "4815694741544"
    assert selected == expected, (
        f"Expected primary_barcode {expected} but got {selected}; should pick the barcode from the collection with MAX(priority)"
    )


if __name__ == "__main__":
    try:
        test_real_case_wb_sku_168568189()
        sys.exit(0)
    except Exception:
        sys.exit(1)
