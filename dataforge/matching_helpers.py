from __future__ import annotations

import hashlib
import logging

import pandas as pd

logger = logging.getLogger(__name__)


def generate_merge_code(wb_sku: str) -> tuple[str, str, bool]:
    """Generate merge code and hex for a given wb_sku.

    Returns (merge_code, wb_hex, fallback_used).

    - merge_code: 'B' + hex (lowercase, without 0x)
    - wb_hex: hex portion (without 'B')
    - fallback_used: True if a non-decimal fallback was used
    """
    if wb_sku is None:
        raise ValueError("wb_sku is required")
    s = str(wb_sku).strip()
    if not s:
        raise ValueError("wb_sku is empty")

    try:
        # wb_sku is expected to be decimal numeric (UBIGINT in DB)
        n = int(s)
        wb_hex = format(n, "X")
        merge_code = "B-" + wb_hex
        return merge_code, wb_hex, False
    except ValueError:
        # Fallback: produce deterministic hex from md5 of the string
        # Use first 12 hex chars to keep code compact but unique enough
        h = hashlib.md5(s.encode("utf-8")).hexdigest()[:12].upper()
        merge_code = "B-" + h
        logger.debug("generate_merge_code: fallback used for wb_sku=%s -> %s", s, merge_code)
        return merge_code, h, True


def parse_color_from_oz_vendor_code(oz_vendor_code: str) -> tuple[str | None, bool]:
    """Parse color from `oz_vendor_code` using the convention "*-color-*".

    Returns (color_or_none, ok_flag). ok_flag==True when a color was found.
    """
    if oz_vendor_code is None:
        return None, False
    s = str(oz_vendor_code).strip()
    if not s:
        return None, False

    parts = s.split("-")
    # Expect at least three segments: prefix-color-suffix
    if len(parts) >= 3:
        color = parts[1].strip()
        if color:
            return color, True
    return None, False


def add_merge_fields(
    df, wb_sku_col: str = "wb_sku", oz_vendor_col: str = "oz_vendor_code"
):
    """Add merge helper fields to a DataFrame in-place and return it.

    Adds columns:
    - group_number (int) - sequential group number starting from 1
    - merge_code
    - merge_wb_hex
    - merge_color
    - merge_parse_ok (bool)
    - merge_fallback_hex (bool)
    """
    if df is None or df.empty:
        return df

    df = df.copy()
    merge_codes = []
    merge_hexs = []
    colors = []
    parse_ok = []
    fallback_flags = []

    for _, r in df.iterrows():
        wb = r.get(wb_sku_col)
        ozvc = r.get(oz_vendor_col)
        try:
            code, hx, fallback = generate_merge_code(wb)
        except Exception:
            code, hx, fallback = "", "", True

        color, ok = parse_color_from_oz_vendor_code(ozvc)
        # Compose visible color name: color + '; ' + hex OR hex only if color missing
        if ok and color:
            # keep color as-is, but show HEX in uppercase
            color_name = f"{color}; {hx}"
            ok_flag = True
        else:
            color_name = hx
            ok_flag = bool(ok)

        merge_codes.append(code)
        merge_hexs.append(hx)
        colors.append(color_name)
        parse_ok.append(ok_flag)
        fallback_flags.append(bool(fallback))

    df["merge_code"] = merge_codes
    df["merge_wb_hex"] = merge_hexs
    df["merge_color"] = colors
    df["merge_parse_ok"] = parse_ok
    df["merge_fallback_hex"] = fallback_flags
    
    # Add group_number based on unique merge_code
    # Sort merge_codes to ensure consistent numbering
    unique_merge_codes = sorted(df["merge_code"].unique())
    merge_code_to_group = {code: idx + 1 for idx, code in enumerate(unique_merge_codes)}
    df["group_number"] = df["merge_code"].map(merge_code_to_group)
    
    return df


def add_merge_fields_with_duplicates(
    df,
    wb_sku_col: str = "wb_sku",
    oz_vendor_col: str = "oz_vendor_code",
    algorithm_prefix: str = "C",
):
    """Add merge fields with duplicate size tracking.
    
    Similar to add_merge_fields, but marks duplicate sizes within same group:
    - First (best score) gets prefix from algorithm_prefix (e.g., 'C')
    - Duplicates get prefix 'D' with optional suffix '_N' for multiple duplicates
    
    Args:
        df: DataFrame with matching results
        wb_sku_col: Column name for WB SKU
        oz_vendor_col: Column name for OZ vendor code
        algorithm_prefix: Prefix for primary (non-duplicate) items (default: 'C')
    
    Returns:
        DataFrame with merge fields including duplicate markers
    """
    if df is None or df.empty:
        return df

    df = df.copy()
    
    # First, generate base merge codes as usual
    merge_codes = []
    merge_hexs = []
    colors = []
    parse_ok = []
    fallback_flags = []

    for _, r in df.iterrows():
        wb = r.get(wb_sku_col)
        ozvc = r.get(oz_vendor_col)
        try:
            _, hx, fallback = generate_merge_code(wb)
        except Exception:
            hx, fallback = "", True

        color, ok = parse_color_from_oz_vendor_code(ozvc)
        if ok and color:
            color_name = f"{color}; {hx}"
            ok_flag = True
        else:
            color_name = hx
            ok_flag = bool(ok)

        merge_hexs.append(hx)
        colors.append(color_name)
        parse_ok.append(ok_flag)
        fallback_flags.append(bool(fallback))

    df["merge_wb_hex"] = merge_hexs
    df["merge_color"] = colors
    df["merge_parse_ok"] = parse_ok
    df["merge_fallback_hex"] = fallback_flags

    # Now handle duplicates: group by group_number and oz_manufacturer_size
    # Sort by match_score descending to ensure best item comes first
    if "group_number" in df.columns and "oz_manufacturer_size" in df.columns and "match_score" in df.columns:
        df = df.sort_values(["group_number", "oz_manufacturer_size", "match_score"], 
                           ascending=[True, True, False])
        
        # Track duplicates
        final_merge_codes = []
        for idx, row in df.iterrows():
            group_num = row.get("group_number")
            size = row.get("oz_manufacturer_size")
            hx = row["merge_wb_hex"]
            color = row["merge_color"]
            
            # Count how many items with same group_number and size appear before this one
            if pd.notna(size) and str(size).strip():
                mask = (df["group_number"] == group_num) & (df["oz_manufacturer_size"] == size)
                same_size_items = df.loc[mask]
                position = list(same_size_items.index).index(idx) + 1
                total_duplicates = len(same_size_items)
                
                if position == 1:
                    # First (best) item - use algorithm prefix
                    code = f"{algorithm_prefix}-{color}-{hx}"
                else:
                    # Duplicate item - use 'D' prefix
                    if total_duplicates > 2:
                        # Multiple duplicates: add _N suffix
                        code = f"D-{color}-{hx}_{position}"
                    else:
                        # Only one duplicate: no suffix needed
                        code = f"D-{color}-{hx}"
            else:
                # No size info - use primary prefix
                code = f"{algorithm_prefix}-{color}-{hx}"
            
            final_merge_codes.append(code)
        
        df["merge_code"] = final_merge_codes
    else:
        # Fallback if required columns missing - use simple algorithm_prefix
        df["merge_code"] = df.apply(
            lambda r: f"{algorithm_prefix}-{r['merge_color']}-{r['merge_wb_hex']}", axis=1
        )
    
    # Add group_number based on unique merge_code (recalculate in case it wasn't present)
    unique_merge_codes = sorted(df["merge_code"].unique())
    merge_code_to_group = {code: idx + 1 for idx, code in enumerate(unique_merge_codes)}
    df["group_number"] = df["merge_code"].map(merge_code_to_group)
    
    return df


def mark_duplicate_sizes(
    df,
    primary_prefix: str = "C",
    duplicate_prefix: str = "D",
    grouping_column: str | None = None,
):
    """Mark duplicate sizes within groups by modifying merge_code.
    
    For each group_number + oz_manufacturer_size combination:
    - Keep the first (best match_score) with primary_prefix
    - Mark others as duplicates with duplicate_prefix
    - Add _N suffix for multiple duplicates (when > 2 items with same size)
    
    Args:
        df: DataFrame with group_number, oz_manufacturer_size, merge_code, match_score
        primary_prefix: Prefix for primary (best) items (default: 'C')
        duplicate_prefix: Prefix for duplicate items (default: 'D')
        grouping_column: Additional column to group by (e.g., 'wb_sku' for basic algorithm).
                        If provided, duplicates are found within grouping_column + oz_manufacturer_size
                        instead of group_number + oz_manufacturer_size.
    
    Returns:
        DataFrame with modified merge_code and group_number for duplicates
    """
    if df is None or df.empty:
        return df
    
    required_cols = ["oz_manufacturer_size", "merge_code", "match_score"]
    if grouping_column:
        required_cols.append(grouping_column)
    else:
        required_cols.append("group_number")
    
    if not all(col in df.columns for col in required_cols):
        missing = [c for c in required_cols if c not in df.columns]
        logger.warning(f"mark_duplicate_sizes: Missing required columns: {missing}")
        return df
    
    df = df.copy()
    
    # Determine which column to use for grouping
    group_col = grouping_column if grouping_column else "group_number"
    
    # Sort by group, size, and match_score (descending) to ensure best items come first
    df = df.sort_values(
        [group_col, "oz_manufacturer_size", "match_score"],
        ascending=[True, True, False]
    )
    
    new_merge_codes = []
    new_group_numbers = []
    next_group_number = df.get("group_number", pd.Series([0])).max() + 1 if "group_number" in df.columns and not df.empty else 1
    
    for idx, row in df.iterrows():
        group_val = row[group_col]
        size = row["oz_manufacturer_size"]
        original_merge_code = row["merge_code"]
        original_group_num = row.get("group_number", 1)
        
        # Only process rows with known size
        if pd.notna(size) and str(size).strip():
            # Count items with same grouping value and size
            mask = (df[group_col] == group_val) & (df["oz_manufacturer_size"] == size)
            same_size_items = df.loc[mask]
            
            # Find position of current item in the sorted group
            position = list(same_size_items.index).index(idx) + 1
            total_duplicates = len(same_size_items)
            
            if position == 1:
                # First (best) item - keep original with primary prefix
                if original_merge_code.startswith(primary_prefix + "-"):
                    new_code = original_merge_code
                else:
                    # Replace prefix if needed
                    parts = original_merge_code.split("-", 1)
                    new_code = f"{primary_prefix}-{parts[1]}" if len(parts) > 1 else original_merge_code
                new_group_num = original_group_num
            else:
                # Duplicate item - use duplicate prefix and new group number
                parts = original_merge_code.split("-", 1)
                base_code = parts[1] if len(parts) > 1 else original_merge_code
                
                if total_duplicates > 2:
                    # Multiple duplicates: add _N suffix
                    new_code = f"{duplicate_prefix}-{base_code}_{position}"
                else:
                    # Only one duplicate: no suffix needed
                    new_code = f"{duplicate_prefix}-{base_code}"
                
                # Assign new group number for duplicates
                new_group_num = next_group_number
                next_group_number += 1
        else:
            # No size info - keep original
            new_code = original_merge_code
            new_group_num = original_group_num
        
        new_merge_codes.append(new_code)
        new_group_numbers.append(new_group_num)
    
    df["merge_code"] = new_merge_codes
    df["group_number"] = new_group_numbers
    
    return df


def dedupe_sizes(df, input_type: str) -> pd.DataFrame:
    """Remove duplicate sizes keeping the highest match_score per size group.

    Mirrors the logic used on the matching page. Accepts DataFrame and input_type
    ('wb_sku' or 'oz_sku' or others).
    """
    import pandas as _pd

    if df is None or df.empty:
        return df

    if input_type == "wb_sku":
        size_col = "wb_size"
        group_cols = ["wb_sku", size_col]
    elif input_type in ("oz_sku", "oz_vendor_code"):
        size_col = "oz_manufacturer_size"
        group_cols = ["oz_sku", size_col]
    else:
        return df

    if "match_score" not in df.columns or any(col not in df.columns for col in group_cols):
        return df

    mask_known_size = df[size_col].notna() & (df[size_col].astype(str).str.strip() != "")
    df_known = df.loc[mask_known_size].copy()
    df_unknown = df.loc[~mask_known_size].copy()

    if df_known.empty:
        return df

    df_known = df_known.sort_values(["match_score"], ascending=[False])
    df_known = df_known.drop_duplicates(subset=group_cols, keep="first")

    return _pd.concat([df_known, df_unknown], axis=0, ignore_index=True)
