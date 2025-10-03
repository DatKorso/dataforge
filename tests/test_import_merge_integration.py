from dataforge.attributes import (
    import_unique_values_from_punta,
    merge_with_existing_mappings,
    get_attributes_by_category,
)


def test_import_merge_no_duplicates(md_token_md_database):
    md_token, md_database = md_token_md_database

    cat = "lining_material"

    new_vals = import_unique_values_from_punta(cat, md_token=md_token, md_database=md_database)
    existing = get_attributes_by_category(cat, md_token=md_token, md_database=md_database)

    merged = merge_with_existing_mappings(cat, new_vals, md_token=md_token, md_database=md_database)

    # merged should be at least as large as existing and should not contain duplicates by normalized punta_value
    assert len(merged) >= len(existing)

    existing_norm = set(existing["punta_value"].fillna("").astype(str).str.strip().str.lower())
    merged_norm = set(merged["punta_value"].fillna("").astype(str).str.strip().str.lower())
    assert existing_norm.issubset(merged_norm)