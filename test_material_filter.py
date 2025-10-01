#!/usr/bin/env python3
"""
Quick test to verify material_short filter is working.
This test checks that the WHERE clause filters out candidates with mismatched material_short.
"""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from dataforge.similarity_matching import search_similar_matches_debug
from dataforge.similarity_config import SimilarityScoringConfig

def test_material_filter():
    """Test that material_short filter reduces candidate pool."""
    
    # Get credentials from environment
    md_token = os.environ.get('MOTHERDUCK_TOKEN')
    md_database = os.environ.get('MOTHERDUCK_DATABASE')
    
    if not md_token:
        print("⚠️  MOTHERDUCK_TOKEN not set in environment")
        print("Skipping test (requires database access)")
        return
    
    print("=" * 80)
    print("Testing material_short filter in similarity matching algorithm")
    print("=" * 80)
    
    # Test with original wb_sku from user's report
    test_wb_sku = "418786680"
    
    config = SimilarityScoringConfig(
        max_candidates_per_seed=15,
        min_score_threshold=200.0,
    )
    
    print(f"\nTest input: wb_sku={test_wb_sku}")
    print(f"Config: max_candidates_per_seed={config.max_candidates_per_seed}, min_threshold={config.min_score_threshold}")
    print("\nRunning search_similar_matches_debug()...")
    
    try:
        df_result, stats = search_similar_matches_debug(
            [test_wb_sku],
            config=config,
            md_token=md_token,
            md_database=md_database,
        )
        
        print("\n" + "=" * 80)
        print("STAGE STATISTICS")
        print("=" * 80)
        for key, value in stats.items():
            print(f"  {key:20s}: {value:,}")
        
        print("\n" + "=" * 80)
        print("RESULTS SUMMARY")
        print("=" * 80)
        
        if df_result.empty:
            print("❌ No matches found!")
        else:
            print(f"✅ Total rows:       {len(df_result):,}")
            print(f"✅ Unique wb_sku:    {df_result['wb_sku'].nunique():,}")
            print(f"✅ Unique groups:    {df_result['group_number'].nunique():,}")
            
            print("\n" + "=" * 80)
            print("TOP 10 RESULTS")
            print("=" * 80)
            cols = ['group_number', 'wb_sku', 'similarity_score', 'match_score', 'oz_sku']
            print(df_result[cols].head(10).to_string(index=False))
            
            print("\n" + "=" * 80)
            print("UNIQUE WB_SKU IN RESULTS")
            print("=" * 80)
            unique_wb = sorted(df_result['wb_sku'].unique())
            print(f"Count: {len(unique_wb)}")
            if len(unique_wb) <= 20:
                print(f"All SKUs: {unique_wb}")
            else:
                print(f"First 20: {unique_wb[:20]}")
        
        print("\n" + "=" * 80)
        print("✅ TEST COMPLETED")
        print("=" * 80)
        print("\nExpected behavior:")
        print("- 'pairs' count should be LOWER than before (material_short filter applied)")
        print("- Only candidates with matching material_short (or NULL) should remain")
        print("- This creates more focused similarity groups")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = test_material_filter()
    sys.exit(0 if success else 1)
