from __future__ import annotations

import csv
from io import BytesIO, StringIO
from typing import Any, Optional, Tuple

import pandas as pd


def sniff_delimiter(sample: str) -> Optional[str]:
    """Try to detect CSV delimiter from a text sample.

    Returns one of ",", ";", "\t" or None if unknown.
    """
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
        return dialect.delimiter  # type: ignore[no-any-return]
    except Exception:
        return None


def ensure_text(buffer: bytes, encoding: str | None) -> Tuple[str, str]:
    """Decode bytes to text using the provided encoding or fallbacks.

    Returns the decoded text and the encoding used.
    """
    encodings = [encoding] if encoding else []
    encodings += ["utf-8", "utf-8-sig", "cp1251"]
    for enc in encodings:
        try:
            return buffer.decode(enc), enc  # type: ignore[return-value]
        except Exception:
            continue
    # As last resort, decode with errors replaced
    return buffer.decode("utf-8", errors="replace"), "utf-8"


def read_any(
    uploaded_file: Any,
    ext: str,
    *,
    delimiter: Optional[str] = None,
    encoding: Optional[str] = None,
    header_row: int = 0,
) -> pd.DataFrame:
    """Read an uploaded CSV/XLSX file into a DataFrame.

    - For CSV: auto-detect delimiter if not provided.
    - For XLSX: uses openpyxl engine per project guideline.
    """
    # Streamlit's UploadedFile supports .read() and .getvalue(); ensure bytes
    if hasattr(uploaded_file, "getvalue"):
        raw = uploaded_file.getvalue()
    else:
        raw = uploaded_file.read()

    if ext.lower() == "csv":
        text, used_enc = ensure_text(raw, encoding)
        if delimiter is None:
            # pandas can infer if sep=None with python engine, but sniff first
            sniffed = sniff_delimiter(text[:50_000])
            delimiter = sniffed
        if delimiter is None:
            # fallback to pandas inference; force text to preserve leading zeros
            df = pd.read_csv(StringIO(text), sep=None, engine="python", header=header_row, dtype=str)
        else:
            df = pd.read_csv(StringIO(text), sep=delimiter, header=header_row, dtype=str)
        return df

    if ext.lower() in {"xlsx", "xlsm", "xls"}:
        bio = BytesIO(raw)
        # openpyxl ensures better compatibility
        df = pd.read_excel(bio, engine="openpyxl", header=header_row, dtype=str)
        return df

    raise ValueError(f"Unsupported extension: {ext}")
