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
