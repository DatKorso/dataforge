"""Debug script to check Punta priority logic with real data.

This script checks:
1. Priority order in punta_collections (ascending or descending?)
2. Barcode mapping for wb_sku=168568189
3. Expected vs actual primary_barcode selection
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dataforge.db import get_connection


def check_priority_system():
    """Check how priorities are structured in the database."""
    print("=" * 80)
    print("🔍 CHECKING PUNTA PRIORITY SYSTEM")
    print("=" * 80)
    
    try:
        # Load credentials from secrets
        import streamlit as st
        md_token = st.secrets.get("md_token")
        md_database = st.secrets.get("md_database")
    except Exception:
        print("⚠️  Could not load secrets. Using environment variables.")
        import os
        md_token = os.environ.get("MOTHERDUCK_TOKEN")
        md_database = os.environ.get("MOTHERDUCK_DATABASE", "dataforge")
    
    if not md_token:
        print("❌ No MotherDuck token found. Set MOTHERDUCK_TOKEN or configure secrets.toml")
        return
    
    with get_connection(md_token=md_token, md_database=md_database) as con:
        # 1. Check collection priorities
        print("\n📊 COLLECTION PRIORITIES (from punta_collections):")
        print("-" * 80)
        
        df_collections = con.execute("""
            SELECT collection, priority, active
            FROM punta_collections
            WHERE collection IN ('ОЗ-23', 'ОЗ-25')
            ORDER BY collection
        """).fetch_df()
        
        if df_collections.empty:
            print("❌ No collections found for ОЗ-23 or ОЗ-25")
        else:
            for _, row in df_collections.iterrows():
                print(f"  {row['collection']:<15} priority={row['priority']:<5} active={row['active']}")
        
        # Determine priority order
        oz23_prio = df_collections[df_collections['collection'] == 'ОЗ-23']['priority'].values[0] if not df_collections[df_collections['collection'] == 'ОЗ-23'].empty else None
        oz25_prio = df_collections[df_collections['collection'] == 'ОЗ-25']['priority'].values[0] if not df_collections[df_collections['collection'] == 'ОЗ-25'].empty else None
        
        if oz23_prio and oz25_prio:
            print(f"\n💡 PRIORITY ORDER:")
            if oz25_prio > oz23_prio:
                print(f"   ОЗ-25 ({oz25_prio}) > ОЗ-23 ({oz23_prio}) → HIGHER number = NEWER collection")
                print(f"   ✅ Should use MAX(priority) to select most recent")
            else:
                print(f"   ОЗ-23 ({oz23_prio}) > ОЗ-25 ({oz25_prio}) → LOWER number = NEWER collection")
                print(f"   ✅ Should use MIN(priority) to select most recent")
        
        # 2. Check specific barcodes for wb_sku=168568189
        print("\n🔍 BARCODE MAPPING FOR wb_sku=168568189:")
        print("-" * 80)
        
        # Get barcodes from wb_products
        df_wb = con.execute("""
            SELECT wb_sku, barcodes, primary_barcode
            FROM wb_products
            WHERE wb_sku = 168568189
            LIMIT 1
        """).fetch_df()
        
        if df_wb.empty:
            print("❌ wb_sku=168568189 not found in wb_products")
        else:
            print(f"  Current primary_barcode in DB: {df_wb['primary_barcode'].values[0]}")
            print(f"  All barcodes: {df_wb['barcodes'].values[0]}")
        
        # Check each barcode's collection
        test_barcodes = ['4815550505853', '4815694741544']
        print(f"\n  Checking barcodes: {test_barcodes}")
        print("-" * 80)
        
        for bc in test_barcodes:
            result = con.execute("""
                SELECT 
                    pb.barcode,
                    pb.external_code,
                    ppc.collection,
                    pc.priority
                FROM punta_barcodes pb
                LEFT JOIN punta_products_codes ppc ON ppc.external_code = pb.external_code
                LEFT JOIN punta_collections pc ON pc.collection = ppc.collection
                WHERE pb.barcode = ?
            """, [bc]).fetch_df()
            
            if result.empty:
                print(f"  ❌ {bc}: NOT FOUND in Punta")
            else:
                row = result.iloc[0]
                print(f"  ✅ {bc}:")
                print(f"     └─ external_code: {row['external_code']}")
                print(f"     └─ collection:    {row['collection']}")
                print(f"     └─ priority:      {row['priority']}")
        
        # 3. Simulate priority selection
        print("\n🧪 SIMULATING PRIORITY SELECTION:")
        print("-" * 80)
        
        df_barcode_prio = con.execute("""
            SELECT 
                pb.barcode,
                ppc.collection,
                pc.priority
            FROM punta_barcodes pb
            JOIN punta_products_codes ppc ON ppc.external_code = pb.external_code
            JOIN punta_collections pc ON pc.collection = ppc.collection
            WHERE pb.barcode IN ('4815550505853', '4815694741544')
            ORDER BY pc.priority
        """).fetch_df()
        
        if not df_barcode_prio.empty:
            print("  Order by priority ASC (MIN first):")
            for _, row in df_barcode_prio.iterrows():
                print(f"    {row['barcode']} → {row['collection']} (priority={row['priority']})")
            
            min_barcode = df_barcode_prio.iloc[0]['barcode']
            max_barcode = df_barcode_prio.iloc[-1]['barcode']
            
            print(f"\n  ❓ Current logic uses MIN(priority):")
            print(f"     → Would select: {min_barcode}")
            
            print(f"\n  ❓ If we use MAX(priority):")
            print(f"     → Would select: {max_barcode}")
            
            print(f"\n  ✅ Expected (based on user): 4815694741544 (ОЗ-25)")


if __name__ == "__main__":
    check_priority_system()
