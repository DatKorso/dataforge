import pandas as pd

from dataforge.schema import init_schema
from dataforge.attributes import (
    get_attributes_by_category,
    save_category_mappings,
    export_attributes_to_excel,
)


def test_attributes_roundtrip(md_token_md_database):
    md_token, md_database = md_token_md_database

    # Initialize schema (idempotent)
    messages = init_schema(md_token=md_token, md_database=md_database)
    assert isinstance(messages, list)

    # Prepare sample data
    sample_data = pd.DataFrame({
        "id": [1, 2, 3],
        "punta_value": ["Тест1", "Тест2", "Тест3"],
        "wb_value": ["wb1", "wb2", "wb3"],
        "oz_value": ["oz1", "oz2", "oz3"],
        "lamoda_value": ["l1", "l2", "l3"],
        "description": [None, None, None],
        "additional_field": [None, None, None],
    })

    # Save and read back
    save_category_mappings("test_material", sample_data, md_token=md_token, md_database=md_database)
    df = get_attributes_by_category("test_material", md_token=md_token, md_database=md_database)
    assert len(df) == 3

    # Export to excel
    excel = export_attributes_to_excel(md_token=md_token, md_database=md_database)
    assert excel.getbuffer().nbytes > 0

    # Cleanup: clear category
    save_category_mappings("test_material", pd.DataFrame(columns=sample_data.columns), md_token=md_token, md_database=md_database)