from __future__ import annotations

import pandas as pd

from .db import get_connection
from .schema import init_schema


def list_punta_collections(
    *, md_token: str | None = None, md_database: str | None = None
) -> pd.DataFrame:
    """Return all Punta collections sorted by priority.

    Columns: collection (str), priority (int), active (bool)
    """
    with get_connection(md_token=md_token, md_database=md_database) as con:
        init_schema(md_token=md_token, md_database=md_database)
        try:
            df = con.execute(
                'SELECT collection, priority, active FROM "punta_collections" ORDER BY priority ASC, collection ASC'
            ).fetch_df()
        except Exception:
            # Table may not exist yet in some environments; ensure schema and retry empty
            df = pd.DataFrame(columns=["collection", "priority", "active"])  # empty
    return df


def get_punta_priority(
    collection: str, *, md_token: str | None = None, md_database: str | None = None
) -> int | None:
    """Get priority for a given collection, or None if missing."""
    with get_connection(md_token=md_token, md_database=md_database) as con:
        init_schema(md_token=md_token, md_database=md_database)
        res = con.execute(
            'SELECT priority FROM "punta_collections" WHERE collection = ?', [collection]
        ).fetchone()
    return int(res[0]) if res is not None else None


def get_next_punta_priority(
    *, md_token: str | None = None, md_database: str | None = None
) -> int:
    """Return COALESCE(MAX(priority), 0) + 1."""
    with get_connection(md_token=md_token, md_database=md_database) as con:
        init_schema(md_token=md_token, md_database=md_database)
        row = con.execute('SELECT COALESCE(MAX(priority), 0) + 1 FROM "punta_collections"').fetchone()
    return int(row[0]) if row and row[0] is not None else 1


def ensure_punta_collection(
    collection: str, *, md_token: str | None = None, md_database: str | None = None
) -> tuple[str, int]:
    """Ensure a collection exists; create with next priority if missing.

    Returns (collection, priority).
    """
    collection = str(collection).strip()
    if not collection:
        raise ValueError("collection name is empty")

    with get_connection(md_token=md_token, md_database=md_database) as con:
        init_schema(md_token=md_token, md_database=md_database)
        con.execute("BEGIN TRANSACTION")
        try:
            existing = con.execute(
                'SELECT priority FROM "punta_collections" WHERE collection = ?', [collection]
            ).fetchone()
            if existing is not None:
                prio = int(existing[0])
            else:
                prio = get_next_punta_priority(md_token=md_token, md_database=md_database)
                con.execute(
                    'INSERT INTO "punta_collections" (collection, priority, active) VALUES (?, ?, TRUE)',
                    [collection, prio],
                )
            con.execute("COMMIT")
        except Exception:  # noqa: BLE001
            con.execute("ROLLBACK")
            raise
    return collection, prio


def upsert_punta_priority(
    collection: str, priority: int, *, md_token: str | None = None, md_database: str | None = None
) -> None:
    """Insert or update priority for a collection.

    If the collection doesn't exist, it will be created with the given priority.
    """
    collection = str(collection).strip()
    if not collection:
        raise ValueError("collection name is empty")

    if priority is None:
        raise ValueError("priority is required")

    with get_connection(md_token=md_token, md_database=md_database) as con:
        init_schema(md_token=md_token, md_database=md_database)
        con.execute("BEGIN TRANSACTION")
        try:
            existing = con.execute(
                'SELECT 1 FROM "punta_collections" WHERE collection = ?', [collection]
            ).fetchone()
            if existing is None:
                con.execute(
                    'INSERT INTO "punta_collections" (collection, priority, active) VALUES (?, ?, TRUE)',
                    [collection, int(priority)],
                )
            else:
                con.execute(
                    'UPDATE "punta_collections" SET priority = ? WHERE collection = ?',
                    [int(priority), collection],
                )
            con.execute("COMMIT")
        except Exception:  # noqa: BLE001
            con.execute("ROLLBACK")
            raise


def reorder_punta_collections(
    order: list[str], *, md_token: str | None = None, md_database: str | None = None
) -> None:
    """Persist a new order: assign priorities 1..n in the given sequence.

    The provided list is expected to contain all collections. Any collections
    missing from the list will be appended in the current order.
    """
    with get_connection(md_token=md_token, md_database=md_database) as con:
        init_schema(md_token=md_token, md_database=md_database)
        # Fetch current items
        df = con.execute('SELECT collection FROM "punta_collections" ORDER BY priority, collection').fetch_df()
        current = [str(x) for x in (df["collection"].tolist() if not df.empty else [])]

        # Compose full order
        seen = set()
        full: list[str] = []
        for c in order:
            c = str(c)
            if c and c not in seen:
                full.append(c)
                seen.add(c)
        for c in current:
            if c not in seen:
                full.append(c)
                seen.add(c)

        con.execute("BEGIN TRANSACTION")
        try:
            for idx, coll in enumerate(full, start=1):
                con.execute(
                    'UPDATE "punta_collections" SET priority = ? WHERE collection = ?', [idx, coll]
                )
            con.execute("COMMIT")
        except Exception:  # noqa: BLE001
            con.execute("ROLLBACK")
            raise

