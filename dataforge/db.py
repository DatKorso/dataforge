from __future__ import annotations

import os
from typing import Optional, Tuple

import duckdb


def get_connection(md_token: Optional[str] = None, md_database: Optional[str] = None) -> duckdb.DuckDBPyConnection:
    """Create and return a DuckDB connection to MotherDuck.

    Authentication is provided via the `MOTHERDUCK_TOKEN` environment variable.
    If `md_token` is provided, it's used and exported into the environment for this process.

    Parameters
    - md_token: MotherDuck token (overrides env if provided)
    - md_database: MotherDuck database name (e.g., "my_db"). If None, uses default database.

    Returns
    - A `duckdb.DuckDBPyConnection` connected to MotherDuck.
    """
    if md_token:
        os.environ["MOTHERDUCK_TOKEN"] = md_token

    dsn = f"md:{md_database}" if md_database else "md:"
    return duckdb.connect(dsn)


def check_connection(md_token: Optional[str] = None, md_database: Optional[str] = None) -> Tuple[bool, str]:
    """Validate that a connection to MotherDuck can be established.

    Returns a tuple `(ok, message)` describing the result.
    """
    try:
        with get_connection(md_token=md_token, md_database=md_database) as con:
            row_db = con.execute("select current_database()").fetchone()
            if row_db is None:
                raise RuntimeError("No result returned for current_database()")
            cur_db = row_db[0]

            row_ping = con.execute("select 1").fetchone()
            if row_ping is None:
                raise RuntimeError("No result returned for ping query")
            _ = row_ping[0]
            return True, f"Connected. Current database: {cur_db!s}"
    except Exception as exc:  # noqa: BLE001
        return False, f"Connection failed: {exc}"
