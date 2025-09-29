from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

try:
    # Reuse existing normalization for brand strings
    from dataforge.imports.transformers import brand_title
except Exception:  # pragma: no cover - defensive import
    def brand_title(v: str | None) -> str | None:  # type: ignore[redefinition]
        if v is None:
            return None
        s = str(v).strip()
        return s.title() if s else None


def load_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


def parse_brand_list(raw: str | None) -> list[str]:
    """Parse semicolon-separated brand list into a normalized, unique list.

    - Splits on ';' (also treats newlines as separators)
    - Trims whitespace; discards empty entries
    - Normalizes each brand using `brand_title` to match imported data
    - Preserves original order while deduplicating
    """
    if not raw:
        return []
    # Support both ';' and newlines as separators
    text = raw.replace("\n", ";")
    seen: set[str] = set()
    out: list[str] = []
    for part in text.split(';'):
        b = brand_title(part)
        if not b:
            continue
        if b not in seen:
            seen.add(b)
            out.append(b)
    return out


def filter_df_by_brands(df: pd.DataFrame, brands: Sequence[str]) -> pd.DataFrame:
    """Filter a DataFrame by the `brand` column.

    - If `brands` is empty or `brand` column absent, returns the original DataFrame
    - Otherwise, keeps only rows where brand is in the provided list
    """
    if df is None or df.empty:
        return df
    if not brands or "brand" not in df.columns:
        return df
    allowed = set(brands)
    # Keep rows with brand matching allowed set (None/NaN are excluded)
    return df[df["brand"].isin(allowed)]
