from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from dataforge.db import get_connection


def init_imports_metadata(md_token: str | None = None, md_database: str | None = None) -> None:
    """Ensure the imports metadata table exists."""
    with get_connection(md_token=md_token, md_database=md_database) as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS imports_last_loaded (
                table_name TEXT PRIMARY KEY,
                last_loaded_at TIMESTAMP,
                rows_loaded BIGINT,
                notes TEXT
            )
            """
        )


def set_last_import(
    table_name: str,
    rows_loaded: int | None = None,
    notes: str | None = None,
    md_token: str | None = None,
    md_database: str | None = None,
) -> None:
    """Record the last successful import for a table.

    Uses an UPSERT-like semantics: replace existing record for the table_name.
    This function swallows exceptions so callers can call it as a best-effort
    post-import action without failing the main import flow.
    """
    try:
        init_imports_metadata(md_token=md_token, md_database=md_database)
        # Use explicit UTC timestamp
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        with get_connection(md_token=md_token, md_database=md_database) as con:
            # DuckDB doesn't have a standard UPSERT so do DELETE+INSERT which is simple
            con.execute("DELETE FROM imports_last_loaded WHERE table_name = ?", [table_name])
            con.execute(
                "INSERT INTO imports_last_loaded (table_name, last_loaded_at, rows_loaded, notes) VALUES (?, ?, ?, ?)",
                [table_name, now, rows_loaded, notes],
            )
    except Exception:
        # Best-effort: don't raise to avoid interrupting the main import
        return


def get_last_import(
    table_name: str, md_token: str | None = None, md_database: str | None = None
) -> dict[str, Any] | None:
    """Return last import metadata row for a table or None."""
    try:
        init_imports_metadata(md_token=md_token, md_database=md_database)
        with get_connection(md_token=md_token, md_database=md_database) as con:
            df = con.execute(
                "SELECT table_name, last_loaded_at, rows_loaded, notes FROM imports_last_loaded WHERE table_name = ?",
                [table_name],
            ).fetch_df()
            if df.empty:
                return None
            row = df.iloc[0].to_dict()
            rows_val = row.get("rows_loaded")
            rows_loaded = int(rows_val) if rows_val is not None else None
            return {
                "table_name": str(row.get("table_name")),
                "last_loaded_at": row.get("last_loaded_at"),
                "rows_loaded": rows_loaded,
                "notes": row.get("notes"),
            }
    except Exception:
        return None


def get_all_imports(md_token: str | None = None, md_database: str | None = None) -> list[dict[str, Any]]:
    """Return all import metadata rows as a list of dicts."""
    try:
        init_imports_metadata(md_token=md_token, md_database=md_database)
        with get_connection(md_token=md_token, md_database=md_database) as con:
            df = con.execute("SELECT table_name, last_loaded_at, rows_loaded, notes FROM imports_last_loaded").fetch_df()
            if df.empty:
                return []
            out = []
            for _, r in df.iterrows():
                row = r.to_dict()
                rows_val = row.get("rows_loaded")
                rows_loaded = int(rows_val) if rows_val is not None else None
                out.append(
                    {
                        "table_name": str(row.get("table_name")),
                        "last_loaded_at": row.get("last_loaded_at"),
                        "rows_loaded": rows_loaded,
                        "notes": row.get("notes"),
                    }
                )
            return out
    except Exception:
        return []
