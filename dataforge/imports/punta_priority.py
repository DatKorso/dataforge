"""Priority-based primary_barcode selection using Punta collections.

This module provides logic for selecting the most relevant barcode from a list
based on Punta collection priorities. Higher priority (lower numeric value) 
collections are preferred.
"""
from __future__ import annotations

import json
from typing import Any

import pandas as pd

from dataforge.db import get_connection


def _parse_barcodes(raw: Any) -> list[str]:
    """Parse barcodes from JSON string, list, or semicolon-separated string.
    
    Returns a list of non-empty barcode strings.
    """
    if raw in (None, ""):
        return []

    candidates: list[Any] = []
    
    if isinstance(raw, list | tuple):
        candidates = list(raw)
    else:
        # Try JSON parse
        parsed: Any = None
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                parsed = None
        
        if isinstance(parsed, list):
            candidates = parsed
        elif parsed not in (None, ""):
            candidates = [parsed]
        elif isinstance(raw, str):
            # Fallback: semicolon-separated
            candidates = [part.strip() for part in raw.split(";")]
        else:
            return []

    # Clean and filter
    cleaned = [str(item).strip() for item in candidates if str(item).strip()]
    return cleaned


def enrich_primary_barcode_by_punta(
    df: pd.DataFrame,
    *,
    md_token: str | None = None,
    md_database: str | None = None,
) -> pd.DataFrame:
    """Enrich DataFrame with primary_barcode selected by Punta collection priority.
    
    For each row with a "barcodes" column, selects the barcode with the highest
    Punta priority (MAXIMUM numeric priority value = most recent/preferred).
    If no Punta mapping exists, falls back to the first barcode in the list.
    
    Priority Logic:
    - HIGHER priority number = MORE RECENT collection (e.g., ОЗ-25 priority=14 > ОЗ-23 priority=10)
    - Uses MAX(priority) to select the most preferred barcode
    
    Algorithm:
    1. Collect all unique barcodes from df["barcodes"]
    2. Query DB once: barcode → external_code → collection → priority
    3. For each row, select barcode with MAX(priority)
    4. Fallback: if no Punta match, use first barcode
    
    Args:
        df: DataFrame with "barcodes" column (JSON or semicolon-separated)
        md_token: MotherDuck auth token
        md_database: MotherDuck database name
        
    Returns:
        DataFrame with updated "primary_barcode" column
    """
    if df.empty or "barcodes" not in df.columns:
        return df
    
    # Step 1: Collect all unique barcodes from the batch
    all_barcodes: set[str] = set()
    for raw_barcodes in df["barcodes"]:
        parsed = _parse_barcodes(raw_barcodes)
        all_barcodes.update(parsed)
    
    if not all_barcodes:
        # No barcodes to process; ensure primary_barcode is set to None or first
        df = df.copy()
        if "primary_barcode" not in df.columns:
            df["primary_barcode"] = None
        return df
    
    # Step 2: Query DB once to get barcode → priority mapping
    barcode_to_priority = _get_barcode_priorities(
        list(all_barcodes),
        md_token=md_token,
        md_database=md_database,
    )
    
    # Step 3: For each row, select barcode with highest priority (MAX value)
    # NOTE: In this system, HIGHER priority number = MORE RECENT/PREFERRED collection
    df = df.copy()
    primary_barcodes: list[str | None] = []
    
    for raw_barcodes in df["barcodes"]:
        candidates = _parse_barcodes(raw_barcodes)
        if not candidates:
            primary_barcodes.append(None)
            continue
        
        # Find barcode with maximum priority (highest actual priority)
        best_barcode: str | None = None
        best_priority: int | None = None
        
        for bc in candidates:
            prio = barcode_to_priority.get(bc)
            if prio is not None:
                if best_priority is None or prio > best_priority:
                    best_priority = prio
                    best_barcode = bc
        
        # Fallback: if no Punta mapping found, use first barcode
        if best_barcode is None:
            best_barcode = candidates[0]
        
        primary_barcodes.append(best_barcode)
    
    df["primary_barcode"] = primary_barcodes
    return df


def _get_barcode_priorities(
    barcodes: list[str],
    *,
    md_token: str | None = None,
    md_database: str | None = None,
) -> dict[str, int]:
    """Query DB to get barcode → priority mapping in a single batch query.
    
    Returns:
        Dict mapping barcode to priority (higher number = higher priority/more recent).
        Barcodes not found in Punta will not be in the dict.
    """
    if not barcodes:
        return {}
    
    with get_connection(md_token=md_token, md_database=md_database) as con:
        # Check if Punta tables exist
        tables_exist = _check_punta_tables(con)
        if not tables_exist:
            return {}
        
        # Register barcodes as temp table
        df_barcodes = pd.DataFrame({"barcode": barcodes})
        con.register("input_barcodes_temp", df_barcodes)
        
        # Single JOIN query to get barcode → priority
        sql = """
        SELECT DISTINCT
            ib.barcode,
            pc.priority
        FROM input_barcodes_temp ib
        JOIN punta_barcodes pb ON pb.barcode = ib.barcode
        JOIN punta_products_codes ppc ON ppc.external_code = pb.external_code
        JOIN punta_collections pc ON pc.collection = ppc.collection
        WHERE pc.priority IS NOT NULL
        """
        
        try:
            df_result = con.execute(sql).fetch_df()
        except Exception:
            # Punta tables may not be fully populated; return empty mapping
            return {}
        
        if df_result.empty:
            return {}
        
        # If multiple priorities per barcode (rare), take MAX (highest priority)
        df_grouped = df_result.groupby("barcode")["priority"].max().reset_index()
        
        # Convert to dict
        mapping = dict(zip(df_grouped["barcode"], df_grouped["priority"]))
        return mapping


def _check_punta_tables(con) -> bool:
    """Check if all required Punta tables exist."""
    required_tables = ["punta_barcodes", "punta_products_codes", "punta_collections"]
    try:
        existing = con.execute("SHOW TABLES").fetch_df()
        existing_names = set(existing["name"].astype(str).tolist())
        return all(t in existing_names for t in required_tables)
    except Exception:
        return False
