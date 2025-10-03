"""
Attributes mapping module for managing product characteristics across marketplaces.

This module provides functions for managing attribute mappings between Punta products
and various marketplaces (Wildberries, Ozon, Lamoda).
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Literal

import pandas as pd

from dataforge.db import get_connection

# Category display names for UI
CATEGORY_NAMES = {
    "upper_material": "Материал верха",
    "lining_material": "Материал подкладки",
    "insole_material": "Материал стельки",
    "outsole_material": "Материал подошвы",
    "season": "Сезон",
    "gender": "Пол",
    "product_type": "Предмет",
    "color": "Цвет",
    "fastening": "Застежка",
    "heel": "Каблук",
}

# Column display names for each category
CATEGORY_COLUMNS = {
    "upper_material": {
        "punta_value": "Материал верха Punta",
        "wb_value": "Состав ВБ",
        "oz_value": "Материал верха Oz",
        "lamoda_value": "Материал верха Lamoda",
        "additional_field": "Материал Oz",
        "description": "Для описания",
    },
    "lining_material": {
        "punta_value": "Материал подкладки Punta",
        "wb_value": "Материал подкладки ВБ",
        "oz_value": "Материал подкладки Oz",
        "lamoda_value": "Материал подкладки Lamoda",
        "additional_field": "Температурный диапазон",
        "description": None,
    },
    "insole_material": {
        "punta_value": "Материал стельки Punta",
        "wb_value": "Материал стельки ВБ",
        "oz_value": "Материал стельки Oz",
        "lamoda_value": "Материал стельки Lamoda",
        "additional_field": None,
        "description": None,
    },
    "outsole_material": {
        "punta_value": "Материал подошвы Punta",
        "wb_value": "Материал подошвы ВБ",
        "oz_value": "Материал подошвы Oz",
        "lamoda_value": "Материал подошвы Lamoda",
        "additional_field": None,
        "description": None,
    },
    "season": {
        "punta_value": "Сезон Punta",
        "wb_value": "Сезон ВБ",
        "oz_value": "Сезон Oz",
        "lamoda_value": "Сезон Lamoda",
        "additional_field": None,
        "description": None,
    },
    "gender": {
        "punta_value": "Пол Punta",
        "wb_value": "Пол ВБ",
        "oz_value": "Пол Oz",
        "lamoda_value": "Пол Lamoda",
        "additional_field": None,
        "description": None,
    },
    "product_type": {
        "punta_value": "Предмет Punta",
        "wb_value": "Предмет ВБ",
        "oz_value": "Предмет Oz",
        "lamoda_value": "Предмет Lamoda",
        "additional_field": "Название Lamoda",
        "description": None,
    },
    "color": {
        "punta_value": "Цвет Punta",
        "wb_value": "Цвет ВБ",
        "oz_value": "Цвет Oz",
        "lamoda_value": "Цвет Lamoda",
        "additional_field": "Доп цвет",
        "description": None,
    },
    "fastening": {
        "punta_value": "Застежка",
        "wb_value": "Застежка ВБ",
        "oz_value": "Застежка Oz",
        "lamoda_value": "Застежка Lamoda",
        "additional_field": None,
        "description": None,
    },
    "heel": {
        "punta_value": "Каблук",
        "wb_value": "Каблук ВБ",
        "oz_value": "Каблук Oz",
        "lamoda_value": "Каблук Lamoda",
        "additional_field": None,
        "description": None,
    },
}


def get_all_attributes(
    md_token: str | None = None,
    md_database: str | None = None,
) -> pd.DataFrame:
    """
    Get all attribute mappings from the database.

    Args:
        md_token: MotherDuck auth token
        md_database: MotherDuck database name

    Returns:
        DataFrame with all attribute mappings
    """
    con = get_connection(md_token=md_token, md_database=md_database)
    query = """
        SELECT 
            id,
            category,
            punta_value,
            wb_value,
            oz_value,
            lamoda_value,
            description,
            additional_field,
            created_at,
            updated_at
        FROM attributes_mapping
        ORDER BY category, id
    """
    df = con.execute(query).df()
    con.close()
    return df


def get_attributes_by_category(
    category: str,
    md_token: str | None = None,
    md_database: str | None = None,
) -> pd.DataFrame:
    """
    Get attribute mappings for a specific category.

    Args:
        category: Category name (e.g., 'upper_material', 'season')
        md_token: MotherDuck auth token
        md_database: MotherDuck database name

    Returns:
        DataFrame with attribute mappings for the category
    """
    con = get_connection(md_token=md_token, md_database=md_database)
    query = """
        SELECT 
            id,
            category,
            punta_value,
            wb_value,
            oz_value,
            lamoda_value,
            description,
            additional_field,
            created_at,
            updated_at
        FROM attributes_mapping
        WHERE category = ?
        ORDER BY id
    """
    df = con.execute(query, [category]).df()
    con.close()
    return df


def save_category_mappings(
    category: str,
    df: pd.DataFrame,
    md_token: str | None = None,
    md_database: str | None = None,
) -> None:
    """
    Save attribute mappings for a specific category.
    
    This function performs a full replace: deletes existing records for the category
    and inserts all records from the provided DataFrame.

    Args:
        category: Category name
        df: DataFrame with columns: id, punta_value, wb_value, oz_value, lamoda_value, 
            description, additional_field
        md_token: MotherDuck auth token
        md_database: MotherDuck database name
    """
    con = get_connection(md_token=md_token, md_database=md_database)
    
    try:
        # Start transaction
        con.execute("BEGIN TRANSACTION")
        
        # Delete existing records for this category
        con.execute("DELETE FROM attributes_mapping WHERE category = ?", [category])
        
        # Prepare data for insert
        if not df.empty:
            # Add category and timestamp columns
            df = df.copy()
            df["category"] = category
            df["updated_at"] = datetime.now()
            
            # If created_at is missing, set it
            if "created_at" not in df.columns:
                df["created_at"] = datetime.now()
            
            # Ensure correct column order and types
            columns_order = [
                "id",
                "category",
                "punta_value",
                "wb_value",
                "oz_value",
                "lamoda_value",
                "description",
                "additional_field",
                "created_at",
                "updated_at",
            ]
            
            # Fill missing columns with None
            for col in columns_order:
                if col not in df.columns:
                    df[col] = None
            
            df = df[columns_order]
            
            # Insert new records
            con.execute(
                """
                INSERT INTO attributes_mapping 
                (id, category, punta_value, wb_value, oz_value, lamoda_value, 
                 description, additional_field, created_at, updated_at)
                SELECT * FROM df
                """
            )
        
        # Commit transaction
        con.execute("COMMIT")
    except Exception as e:
        con.execute("ROLLBACK")
        raise e
    finally:
        con.close()


def delete_category_mapping(
    category: str,
    mapping_id: int,
    md_token: str | None = None,
    md_database: str | None = None,
) -> None:
    """
    Delete a specific attribute mapping.

    Args:
        category: Category name
        mapping_id: ID of the mapping to delete
        md_token: MotherDuck auth token
        md_database: MotherDuck database name
    """
    con = get_connection(md_token=md_token, md_database=md_database)
    con.execute(
        "DELETE FROM attributes_mapping WHERE category = ? AND id = ?",
        [category, mapping_id],
    )
    con.close()


def export_attributes_to_excel(
    md_token: str | None = None,
    md_database: str | None = None,
) -> BytesIO:
    """
    Export all attribute mappings to Excel file with separate sheets for each category.

    Args:
        md_token: MotherDuck auth token
        md_database: MotherDuck database name

    Returns:
        BytesIO object containing the Excel file
    """
    output = BytesIO()
    
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for category_key, category_name in CATEGORY_NAMES.items():
            df = get_attributes_by_category(
                category_key,
                md_token=md_token,
                md_database=md_database,
            )
            
            if not df.empty:
                # Prepare display columns
                column_config = CATEGORY_COLUMNS.get(category_key, {})
                display_df = df[["id", "punta_value", "wb_value", "oz_value", "lamoda_value"]].copy()
                
                # Add optional columns if configured
                if column_config.get("additional_field"):
                    display_df["additional_field"] = df["additional_field"]
                if column_config.get("description"):
                    display_df["description"] = df["description"]
                
                # Rename columns for display
                rename_map = {
                    "id": "ID",
                    "punta_value": column_config.get("punta_value", "Punta"),
                    "wb_value": column_config.get("wb_value", "ВБ"),
                    "oz_value": column_config.get("oz_value", "Ozon"),
                    "lamoda_value": column_config.get("lamoda_value", "Lamoda"),
                }
                
                if column_config.get("additional_field"):
                    rename_map["additional_field"] = column_config.get("additional_field", "Доп. поле")
                if column_config.get("description"):
                    rename_map["description"] = column_config.get("description", "Описание")
                
                display_df = display_df.rename(columns=rename_map)
                
                # Write to sheet
                display_df.to_excel(writer, sheet_name=category_name, index=False)
    
    output.seek(0)
    return output


def get_next_id_for_category(
    category: str,
    md_token: str | None = None,
    md_database: str | None = None,
) -> int:
    """
    Get the next available ID for a category.

    Args:
        category: Category name
        md_token: MotherDuck auth token
        md_database: MotherDuck database name

    Returns:
        Next available ID (max ID + 1, or 1 if no records exist)
    """
    con = get_connection(md_token=md_token, md_database=md_database)
    result = con.execute(
        "SELECT COALESCE(MAX(id), 0) + 1 as next_id FROM attributes_mapping WHERE category = ?",
        [category],
    ).fetchone()
    con.close()
    return result[0] if result else 1


def import_unique_values_from_punta(
    category: str,
    md_token: str | None = None,
    md_database: str | None = None,
) -> pd.DataFrame:
    """
    Import unique values from punta_products table for a specific category.
    
    Maps category to corresponding punta_products column:
    - upper_material -> upper_material
    - lining_material -> lining_material
    - insole_material -> insole_material
    - outsole_material -> outsole_material
    
    Args:
        category: Category name (e.g., 'upper_material')
        md_token: MotherDuck auth token
        md_database: MotherDuck database name
    
    Returns:
        DataFrame with unique values ready for import (with auto-generated IDs)
    """
    # Map category to punta_products column
    column_mapping = {
        "upper_material": "upper_material",
        "lining_material": "lining_material",
        "insole_material": "insole_material",
        "outsole_material": "outsole_material",
    }
    
    if category not in column_mapping:
        raise ValueError(f"Category '{category}' does not support auto-import from punta_products")
    
    punta_column = column_mapping[category]
    
    con = get_connection(md_token=md_token, md_database=md_database)
    
    # Get unique non-null values from punta_products
    query = f"""
        SELECT DISTINCT {punta_column} as punta_value
        FROM punta_products
        WHERE {punta_column} IS NOT NULL 
          AND TRIM({punta_column}) != ''
        ORDER BY {punta_column}
    """
    
    df = con.execute(query).df()
    con.close()
    
    if df.empty:
        return pd.DataFrame(columns=["id", "punta_value", "wb_value", "oz_value", "lamoda_value", "description", "additional_field"])
    
    # Generate IDs starting from 1
    df["id"] = range(1, len(df) + 1)
    
    # Add empty columns for other marketplaces
    df["wb_value"] = None
    df["oz_value"] = None
    df["lamoda_value"] = None
    df["description"] = None
    df["additional_field"] = None
    
    # Reorder columns
    df = df[["id", "punta_value", "wb_value", "oz_value", "lamoda_value", "description", "additional_field"]]
    
    return df


def merge_with_existing_mappings(
    category: str,
    new_df: pd.DataFrame,
    md_token: str | None = None,
    md_database: str | None = None,
) -> pd.DataFrame:
    """
    Merge new values with existing mappings, preserving existing records.
    
    Args:
        category: Category name
        new_df: DataFrame with new values to add
        md_token: MotherDuck auth token
        md_database: MotherDuck database name
    
    Returns:
        Merged DataFrame with both existing and new values
    """
    existing_df = get_attributes_by_category(category, md_token=md_token, md_database=md_database)

    # If there are no existing records, ensure new_df IDs will be re-assigned
    if existing_df.empty:
        # Normalize punta_value strings in new_df
        new_df = new_df.copy()
        new_df["punta_value"] = new_df["punta_value"].fillna("").astype(str).str.strip()
        # Assign IDs starting from 1
        new_df["id"] = range(1, len(new_df) + 1)
        return new_df

    # Normalize punta_value for comparison (trim + lower)
    existing_df = existing_df.copy()
    existing_df["_punta_norm"] = (
        existing_df["punta_value"].fillna("").astype(str).str.strip().str.lower()
    )

    new_df = new_df.copy()
    new_df["punta_value"] = new_df["punta_value"].fillna("").astype(str).str.strip()
    new_df["_punta_norm"] = new_df["punta_value"].str.lower()

    # Determine values that are truly new (normalized comparison)
    existing_norm_set = set(x for x in existing_df["_punta_norm"].tolist() if x)
    new_values_df = new_df[~new_df["_punta_norm"].isin(existing_norm_set)].copy()

    if new_values_df.empty:
        # Nothing to add, return existing as-is (drop helper column)
        existing_df = existing_df.drop(columns=["_punta_norm"])
        return existing_df

    # Get next available ID within the category
    max_id = int(existing_df["id"].max() or 0)
    new_values_df["id"] = range(max_id + 1, max_id + 1 + len(new_values_df))

    # Prepare new rows: ensure expected columns exist and don't overwrite marketplace columns
    for col in ["wb_value", "oz_value", "lamoda_value", "description", "additional_field"]:
        if col not in new_values_df.columns:
            new_values_df[col] = None

    new_values_df = new_values_df[["id", "punta_value", "wb_value", "oz_value", "lamoda_value", "description", "additional_field"]]

    # Combine existing and new; drop helper norm column on existing
    existing_df = existing_df.drop(columns=["_punta_norm"])
    result_df = pd.concat([existing_df, new_values_df], ignore_index=True)

    return result_df
