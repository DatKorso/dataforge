"""
Migration script to recreate attributes_mapping table with composite primary key.
"""

from dataforge.db import get_connection
from dataforge.schema import get_all_schemas

print("Starting migration: recreating attributes_mapping with composite primary key...")

con = get_connection()

try:
    # Check if table exists and has data
    print("\n1. Checking existing table...")
    has_data = False
    try:
        result = con.execute("SELECT COUNT(*) as cnt FROM attributes_mapping").fetchone()
        count = result[0] if result else 0
        has_data = count > 0
        print(f"   Found {count} existing records")
        
        if has_data:
            # Backup existing data
            print("\n2. Backing up existing data...")
            backup_df = con.execute("SELECT * FROM attributes_mapping").df()
            print(f"   Backed up {len(backup_df)} records")
    except Exception:
        print("   Table does not exist yet")
    
    # Drop the old table
    print("\n3. Dropping old table...")
    con.execute("DROP TABLE IF EXISTS attributes_mapping")
    print("   ✓ Dropped")
    
    # Create new table with composite primary key
    print("\n4. Creating new table with composite primary key (category, id)...")
    schema = get_all_schemas()["attributes_mapping"]
    con.execute(schema.create_sql)
    print("   ✓ Created")
    
    # Restore data if we had any
    if has_data:
        print("\n5. Restoring data...")
        con.execute("INSERT INTO attributes_mapping SELECT * FROM backup_df")
        restored_count = con.execute("SELECT COUNT(*) FROM attributes_mapping").fetchone()[0]
        print(f"   ✓ Restored {restored_count} records")
    
    # Create indexes
    print("\n6. Creating indexes...")
    for idx_name, idx_sql in schema.index_sql:
        try:
            con.execute(idx_sql)
            print(f"   ✓ Created index {idx_name}")
        except Exception as e:
            print(f"   ⚠ Index {idx_name} already exists or error: {e}")
    
    print("\n✅ Migration completed successfully!")
    print("\nNew schema allows ID duplication across categories (composite key: category + id)")
    
except Exception as e:
    print(f"\n❌ Migration failed: {e}")
    raise
finally:
    con.close()
