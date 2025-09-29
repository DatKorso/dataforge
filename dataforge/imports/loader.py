from __future__ import annotations

import pandas as pd
from dataforge.db import get_connection
from dataforge.schema import get_all_schemas, init_schema, rebuild_indexes


def quote_ident(ident: str) -> str:
    """Quote an identifier for DuckDB (handles special characters like dashes)."""
    # Double-quote and escape internal quotes
    return '"' + ident.replace('"', '""') + '"'


def load_dataframe(
    df: pd.DataFrame,
    table: str,
    *,
    md_token: str | None = None,
    md_database: str | None = None,
    replace: bool = True,
) -> str:
    """Load a DataFrame into MotherDuck via DuckDB.

    - When `replace` is True, uses CREATE OR REPLACE TABLE as SELECT ...
    - Otherwise, creates table if missing and inserts rows
    Returns a short status message.
    """
    if df.empty:
        return "DataFrame is empty; nothing to load"

    with get_connection(md_token=md_token, md_database=md_database) as con:
        con.register("df_to_load", df)

        # If we have a known schema, prefer preserving it (delete + insert)
        schemas = get_all_schemas()
        if table in schemas and replace:
            # Ensure table exists; detect schema drift (new columns in DF vs table)
            init_schema(md_token=md_token, md_database=md_database)
            try:
                info = con.execute(f"PRAGMA table_info({quote_ident(table)})").fetch_df()
            except Exception:
                info = None

            table_cols = set([str(x) for x in (info["name"].tolist() if info is not None else [])])
            df_cols = set(df.columns)
            needs_recreate = False
            if not table_cols:
                needs_recreate = True
            else:
                new_cols_in_df = df_cols - table_cols
                if new_cols_in_df:
                    needs_recreate = True

            if needs_recreate:
                # Drop and recreate using hardcoded schema, then insert
                con.execute(f"DROP TABLE IF EXISTS {quote_ident(table)}")
                init_schema(md_token=md_token, md_database=md_database)
                info2 = con.execute(f"PRAGMA table_info({quote_ident(table)})").fetch_df()
                target_cols = [str(x) for x in info2["name"].tolist()]
                for c in target_cols:
                    if c not in df.columns:
                        df[c] = None
                con.unregister("df_to_load")
                con.register("df_to_load", df[target_cols])
                cols = ", ".join(quote_ident(c) for c in target_cols)
                con.execute(
                    f"INSERT INTO {quote_ident(table)} ({cols}) SELECT {cols} FROM df_to_load"
                )
                rebuild_indexes(md_token=md_token, md_database=md_database, table=table)
                return (
                    f"Recreated table {table} from schema and loaded {len(df)} rows; indexes rebuilt"
                )
            # Column set matches; preserve table types
            target_cols = [str(x) for x in info["name"].tolist()]
            for c in target_cols:
                if c not in df.columns:
                    df[c] = None
            con.unregister("df_to_load")
            con.register("df_to_load", df[target_cols])
            con.execute(f"DELETE FROM {quote_ident(table)}")
            cols = ", ".join(quote_ident(c) for c in target_cols)
            con.execute(
                f"INSERT INTO {quote_ident(table)} ({cols}) SELECT {cols} FROM df_to_load"
            )
            rebuild_indexes(md_token=md_token, md_database=md_database, table=table)
            return f"Replaced table {table} with {len(df)} rows and rebuilt indexes"

        if replace:
            # Fallback: replace table via CTAS
            con.execute(f"CREATE OR REPLACE TABLE {quote_ident(table)} AS SELECT * FROM df_to_load")
            rebuild_indexes(md_token=md_token, md_database=md_database, table=table)
            return f"Replaced table {table} with {len(df)} rows and rebuilt indexes"

        # else: create if not exists then insert
        cols = ", ".join(quote_ident(c) for c in df.columns)
        con.execute(f"CREATE TABLE IF NOT EXISTS {quote_ident(table)} AS SELECT * FROM df_to_load WHERE 1=0")
        con.execute(f"INSERT INTO {quote_ident(table)} ({cols}) SELECT {cols} FROM df_to_load")
        rebuild_indexes(md_token=md_token, md_database=md_database, table=table)
        return f"Inserted {len(df)} rows into {table} and ensured indexes"


def load_dataframe_partitioned(
    df: pd.DataFrame,
    table: str,
    *,
    partition_field: str,
    partition_value: str,
    md_token: str | None = None,
    md_database: str | None = None,
) -> str:
    """Load a DataFrame by replacing a single partition identified by a field/value.

    This is used for reports where data is logically grouped by a user-provided
    key (e.g., "collection"). The function:
    - Ensures schema exists
    - Aligns columns to the target table
    - Deletes existing rows for the partition
    - Inserts new rows
    - Rebuilds indexes
    Returns a short status message.
    """
    if df.empty:
        return "DataFrame is empty; nothing to load"

    with get_connection(md_token=md_token, md_database=md_database) as con:
        con.register("df_to_load", df)

        # Ensure target schema exists
        init_schema(md_token=md_token, md_database=md_database)

        # Determine target columns from table
        try:
            info = con.execute(f"PRAGMA table_info({quote_ident(table)})").fetch_df()
            target_cols = [str(x) for x in info["name"].tolist()]
        except Exception:
            target_cols = list(df.columns)

        # Ensure DataFrame has all required columns (fill missing with None)
        for c in target_cols:
            if c not in df.columns:
                df[c] = None

        # Re-register limiting to target columns to preserve order and types
        con.unregister("df_to_load")
        con.register("df_to_load", df[target_cols])

        cols = ", ".join(quote_ident(c) for c in target_cols)

        # Transactional replace of the partition
        con.execute("BEGIN TRANSACTION")
        try:
            con.execute(
                f"DELETE FROM {quote_ident(table)} WHERE {quote_ident(partition_field)} = ?",
                [partition_value],
            )
            con.execute(
                f"INSERT INTO {quote_ident(table)} ({cols}) SELECT {cols} FROM df_to_load",
            )
            con.execute("COMMIT")
        except Exception:  # noqa: BLE001
            con.execute("ROLLBACK")
            raise

        rebuild_indexes(md_token=md_token, md_database=md_database, table=table)
        return (
            f"Replaced partition where {partition_field}={partition_value!r} in {table}; indexes rebuilt"
        )
