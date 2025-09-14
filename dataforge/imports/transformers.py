from __future__ import annotations

import math
import re
import pandas as pd
from typing import Any, Optional
import json


def _to_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v)
    s = s.strip()
    return s if s != "" else None


def string_clean(v: Any) -> Optional[str]:
    """Trim whitespace; return None for empty strings; drop leading apostrophes.
    Also remove zero-width characters and normalize spaces.
    """
    s = _to_str(v)
    if s is None:
        return None
    s = s.replace("\u200b", "").replace("\xa0", " ").strip()
    if s.startswith("'"):
        s = s.lstrip("'")
    return s if s else None


def brand_title(v: Any) -> Optional[str]:
    """Normalize brand names to Title Case if present."""
    s = string_clean(v)
    if s is None:
        return None
    return s.title()


def title_clean(v: Any) -> Optional[str]:
    s = string_clean(v)
    if s is None:
        return None
    return s.title()


def upper3(v: Any) -> Optional[str]:
    """Return uppercased string (trimmed), up to 3 chars if longer."""
    s = string_clean(v)
    if s is None:
        return None
    return s.upper()[:3]


def int_strict(v: Any) -> Optional[int]:
    s = string_clean(v)
    if s is None:
        return None
    if not re.fullmatch(r"[0-9]+", s):
        raise ValueError(f"not an integer: {s}")
    try:
        return int(s)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"invalid int: {s}") from exc


def int_relaxed(v: Any) -> Optional[int]:
    s = string_clean(v)
    if s is None:
        return None
    s = s.replace(" ", "").replace("'", "")
    s = re.sub(r"[^0-9-]", "", s)
    if s in ("", "-"):
        return None
    try:
        return int(s)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"invalid int: {s}") from exc


def price(v: Any) -> Optional[float]:
    """Clean currency strings, return rounded float to 2 decimals, allow None.
    Removes currency symbols and spaces.
    """
    s = string_clean(v)
    if s is None:
        return None
    s = s.replace(" ", "")
    s = s.replace("₽", "").replace("р", "").replace("RUB", "")
    # Handle comma decimals
    s = s.replace("\u00A0", "").replace("\u202F", "")
    s = s.replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    if s in ("", ".", "-"):
        return None
    val = float(s)
    # Round to 2 decimals, but requirements say round prices to integers
    return round(val)


def money2(v: Any) -> Optional[float]:
    """Parse money with decimals; keep 2 decimal places."""
    s = string_clean(v)
    if s is None:
        return None
    s = s.replace(" ", "").replace("₽", "").replace("р", "").replace("RUB", "")
    s = s.replace("\u00A0", "").replace("\u202F", "").replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    if s in ("", ".", "-"):
        return None
    val = float(s)
    return round(val, 2)


def decimal2(v: Any) -> Optional[float]:
    s = string_clean(v)
    if s is None:
        return None
    s = s.replace(" ", "").replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    if s in ("", ".", "-"):
        return None
    return round(float(s), 2)


def decimal3(v: Any) -> Optional[float]:
    s = string_clean(v)
    if s is None:
        return None
    s = s.replace(" ", "").replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    if s in ("", ".", "-"):
        return None
    return round(float(s), 3)


def percent_str(v: Any) -> Optional[float]:
    s = string_clean(v)
    if s is None:
        return None
    s = s.replace("%", "").replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    if s in ("", ".", "-"):
        return None
    val = float(s)
    # clamp to 0..100
    return max(0.0, min(100.0, val))


def percent_text(v: Any) -> Optional[str]:
    """Normalize percent to string 0..100 with up to 2 decimals (no % sign)."""
    p = percent_str(v)
    if p is None:
        return None
    # Keep compact representation: drop trailing zeros
    s = ("{:.2f}".format(p)).rstrip("0").rstrip(".")
    return s


def percent_int(v: Any) -> Optional[int]:
    """Normalize percent to integer 0..100."""
    p = percent_str(v)
    if p is None:
        return None
    return int(round(p))


def rating(v: Any) -> Optional[float]:
    s = string_clean(v)
    if s is None:
        return None
    s = s.replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    if s in ("", ".", "-"):
        return None
    val = float(s)
    return max(0.0, min(5.0, round(val, 2)))


def rating10(v: Any) -> Optional[float]:
    s = string_clean(v)
    if s is None:
        return None
    s = s.replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    if s in ("", ".", "-"):
        return None
    val = float(s)
    return max(0.0, min(10.0, round(val, 1)))


def lower_clean(v: Any) -> Optional[str]:
    s = string_clean(v)
    if s is None:
        return None
    return s.lower()


def digits_only(v: Any) -> Optional[str]:
    """Keep only digits, handling numeric inputs without appending bogus trailing zeros.

    - If value is int -> stringify
    - If value is float and is integer (e.g., 12345.0) -> int -> str
    - Otherwise, normalize to string and strip non-digits
    """
    if v is None:
        return None
    if isinstance(v, int):
        s = str(v)
    elif isinstance(v, float):
        s = str(int(v)) if v.is_integer() else string_clean(v) or ""
    else:
        s = string_clean(v) or ""
    s = re.sub(r"[^0-9]", "", s)
    return s if s else None


def code_text(v: Any) -> Optional[str]:
    """Convert values that may be read as numbers into stable text codes.

    Behaviors:
    - None/empty -> None
    - float that is an integer (e.g., 12345.0) -> "12345"
    - float with trailing zeros -> strip trailing .0/.00 (keeps integer part)
    - other values -> string_clean result
    Does not strip leading zeros or non-digit characters; preserves text form.
    """
    # Preserve None/empty first
    if v is None:
        return None
    # If it's already a string, normalize and trim trailing .0 patterns
    if isinstance(v, str):
        s = string_clean(v)
        if s is None:
            return None
        # If the value looks like a number with .0 or .00, strip decimals
        if re.fullmatch(r"-?[0-9]+\.(?:0+)", s):
            return s.split(".")[0]
        return s
    # Numeric handling
    try:
        # pandas may give numpy types; handle floats specially
        if isinstance(v, float):
            if v.is_integer():
                return str(int(v))
            # Fallback: drop trailing zeros if any when stringified
            s = ("{:.8f}".format(v)).rstrip("0").rstrip(".")
            return s
        if isinstance(v, int):
            return str(v)
    except Exception:
        pass
    # Fallback to generic string cleaning
    return string_clean(v)


def timestamp(v: Any) -> Optional[pd.Timestamp]:
    """Parse typical Ozon datetime formats (dd.mm.yyyy[ HH:MM[:SS]])."""
    s = string_clean(v)
    if s is None:
        return None
    try:
        # Pandas robust parsing with dayfirst
        return pd.to_datetime(s, dayfirst=True, errors="raise")
    except Exception:
        return None


def barcodes_json(v: Any) -> Optional[str]:
    """Split barcodes by ';' and serialize as JSON array (strings)."""
    s = string_clean(v)
    if s is None:
        return None
    parts = [p.strip() for p in s.split(";")]
    parts = [p for p in parts if p]
    if not parts:
        return None
    # keep order; return JSON string
    return json.dumps(parts, ensure_ascii=False)


def urls_json(v: Any) -> Optional[str]:
    """Split URLs by ';' and serialize as JSON array (strings)."""
    s = string_clean(v)
    if s is None:
        return None
    parts = [p.strip() for p in s.split(";")]
    parts = [p for p in parts if p]
    if not parts:
        return None
    return json.dumps(parts, ensure_ascii=False)


# Registry of transformer functions
TRANSFORMERS = {
    "string_clean": string_clean,
    "brand_title": brand_title,
    "title_clean": title_clean,
    "upper3": upper3,
    "int_strict": int_strict,
    "int_relaxed": int_relaxed,
    "price": price,
    "money2": money2,
    "decimal2": decimal2,
    "decimal3": decimal3,
    "percent_str": percent_str,
    "percent_text": percent_text,
    "percent_int": percent_int,
    "rating": rating,
    "rating10": rating10,
    "timestamp": timestamp,
    "barcodes_json": barcodes_json,
    "urls_json": urls_json,
    "lower_clean": lower_clean,
    "digits_only": digits_only,
    "code_text": code_text,
}
