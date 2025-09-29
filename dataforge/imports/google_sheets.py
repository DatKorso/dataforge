from __future__ import annotations

import re

import pandas as pd

_RE_SPREADSHEET_ID = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")


def to_export_csv_url(url: str) -> str:
    """Convert a Google Sheets share URL to a CSV export URL (first sheet).

    Examples:
    - https://docs.google.com/spreadsheets/d/<id>/edit?usp=sharing ->
      https://docs.google.com/spreadsheets/d/<id>/export?format=csv
    - If the url is already an export link, return as-is.
    """
    if "export?format=csv" in url:
        return url
    m = _RE_SPREADSHEET_ID.search(url)
    if not m:
        raise ValueError("Не удалось извлечь идентификатор Google Sheets из ссылки")
    sheet_id = m.group(1)
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"


def read_csv_first_sheet(url: str, *, nrows: int | None = None) -> pd.DataFrame:
    """Read first sheet of a Google Sheet as CSV into a DataFrame of strings.

    - Skips the 2nd row (decorators) via skiprows=[1]
    - Uses the 1st row as headers (header=0)
    - All values are read as strings
    - Optionally limit to `nrows` for quick checks
    """
    csv_url = to_export_csv_url(url)
    df = pd.read_csv(csv_url, dtype=str, header=0, skiprows=[1], nrows=nrows)
    # Normalize dtypes: ensure all cells are strings, NaN -> None
    try:
        return df.map(lambda x: None if pd.isna(x) else str(x))  # pandas >= 2.2
    except AttributeError:  # pragma: no cover - compat for older pandas
        return df.applymap(lambda x: None if pd.isna(x) else str(x))


def check_access(url: str) -> tuple[bool, str, pd.DataFrame | None]:
    """Try reading a few rows to validate access and format.

    Returns (ok, message, df_preview)
    """
    try:
        df = read_csv_first_sheet(url, nrows=10)
        if df is None or df.empty:
            return True, "Доступ есть, но документ пуст или не содержит данных.", df
        return True, f"Доступ подтверждён. Найдено колонок: {len(df.columns)}.", df
    except Exception as exc:  # noqa: BLE001
        return False, f"Ошибка доступа или чтения: {exc}", None


def dedup_by_wb_sku_first(df: pd.DataFrame) -> pd.DataFrame:
    """Drop duplicate rows by wb_sku, keeping the first occurrence.

    If wb_sku column is missing, returns the DataFrame unchanged.
    """
    if df is None or df.empty:
        return df
    cols = [str(c) for c in df.columns]
    if "wb_sku" not in cols:
        return df
    return df.drop_duplicates(subset=["wb_sku"], keep="first")
