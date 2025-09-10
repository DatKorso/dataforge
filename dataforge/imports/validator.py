from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import pandas as pd

from .registry import ColumnSpec, ReportSpec
from .transformers import TRANSFORMERS


@dataclass
class ValidationResult:
    rows_total: int
    rows_valid: int
    errors: List[Dict[str, Any]]
    df_normalized: pd.DataFrame


def normalize_and_validate(df_raw: pd.DataFrame, spec: ReportSpec) -> ValidationResult:
    """Normalize source DataFrame into target schema and validate.

    - Applies transformers
    - Enforces required fields
    - Checks batch-level uniqueness
    - Computes derived fields
    - Collects per-row errors and skips invalid rows
    """
    # Map source headers (strip spaces)
    df = df_raw.copy()
    df.columns = [str(c).strip() for c in df.columns]

    # Build normalized rows
    errors: List[Dict[str, Any]] = []
    out_rows: List[Dict[str, Any]] = []

    # Prepare source -> ColumnSpec map for quick lookup
    src_map: Dict[str, ColumnSpec] = {c.source: c for c in spec.columns}

    for idx, row in df.iterrows():
        record: Dict[str, Any] = {}
        row_errors: List[str] = []

        # Field mapping & transforms
        for col in spec.columns:
            value = row.get(col.source, None)
            try:
                if col.transform:
                    func = TRANSFORMERS[col.transform]
                    value = func(value)
                # else: keep as-is
            except Exception as exc:  # noqa: BLE001
                row_errors.append(f"{col.target}: transform failed ({exc})")
                value = None
            record[col.target] = value

        # Required checks
        for col in spec.columns:
            if col.required and (record.get(col.target) is None or record.get(col.target) == ""):
                row_errors.append(f"{col.target}: missing required value")

        # Compute derived fields
        for k, fn in spec.computed_fields.items():
            try:
                record[k] = fn(record)
            except Exception as exc:  # noqa: BLE001
                row_errors.append(f"{k}: compute failed ({exc})")
                record[k] = None

        if row_errors:
            errors.append({"row": int(idx) + 1, "errors": "; ".join(row_errors)})
        else:
            out_rows.append(record)

    df_norm = pd.DataFrame(out_rows)

    # Uniqueness checks (within the batch)
    dup_errors = _detect_duplicates(df_norm, spec.unique_fields_in_batch)
    errors.extend(dup_errors)

    # Drop duplicate rows for import (keep first occurrence)
    if spec.unique_fields_in_batch:
        df_norm = df_norm.drop_duplicates(subset=spec.unique_fields_in_batch, keep="first")

    return ValidationResult(
        rows_total=len(df_raw),
        rows_valid=len(df_norm),
        errors=errors,
        df_normalized=df_norm,
    )


def _detect_duplicates(df: pd.DataFrame, keys: List[str]) -> List[Dict[str, Any]]:
    if not keys or df.empty:
        return []
    dups = df[df.duplicated(subset=keys, keep=False)]
    if dups.empty:
        return []
    # Group duplicates to produce concise messages
    msgs: List[Dict[str, Any]] = []
    for _, grp in dups.groupby(keys):
        key_vals = {k: grp.iloc[0][k] for k in keys}
        msgs.append({"row": None, "errors": f"duplicate batch keys: {key_vals}"})
    return msgs

