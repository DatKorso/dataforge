from contextlib import contextmanager

import duckdb
import pytest


@pytest.fixture()
def mem_con():
    con = duckdb.connect()
    try:
        yield con
    finally:
        try:
            con.close()
        except Exception:
            pass


@pytest.fixture(autouse=True)
def patch_db(monkeypatch, mem_con):
    from dataforge import collections, schema

    @contextmanager
    def fake_get_connection(md_token=None, md_database=None):
        # Provide a context manager yielding the same in-memory connection
        yield mem_con

    # Patch both modules that import get_connection as a symbol
    monkeypatch.setattr(schema, "get_connection", fake_get_connection)
    monkeypatch.setattr(collections, "get_connection", fake_get_connection)


def test_list_empty_and_next_priority(mem_con):
    from dataforge.collections import get_next_punta_priority, list_punta_collections
    from dataforge.schema import init_schema

    # Ensure schema initializes punta_collections
    init_schema()

    df = list_punta_collections()
    assert df is not None
    assert df.empty

    nxt = get_next_punta_priority()
    assert nxt == 1


def test_ensure_and_get_priority(mem_con):
    from dataforge.collections import ensure_punta_collection, get_punta_priority, list_punta_collections

    name, pr = ensure_punta_collection("C1")
    assert name == "C1"
    assert pr == 1
    # Re-ensuring does not duplicate and preserves priority
    name2, pr2 = ensure_punta_collection("C1")
    assert name2 == "C1"
    assert pr2 == 1

    # Next created gets priority 2
    name3, pr3 = ensure_punta_collection("C2")
    assert (name3, pr3) == ("C2", 2)

    df = list_punta_collections()
    assert list(df["collection"]) == ["C1", "C2"]
    assert list(df["priority"])[:2] == [1, 2]

    assert get_punta_priority("C1") == 1
    assert get_punta_priority("C2") == 2


def test_upsert_and_reorder(mem_con):
    from dataforge.collections import (
        ensure_punta_collection,
        get_punta_priority,
        list_punta_collections,
        reorder_punta_collections,
        upsert_punta_priority,
    )

    ensure_punta_collection("C1")
    ensure_punta_collection("C2")

    # Update priority directly
    upsert_punta_priority("C1", 5)
    assert get_punta_priority("C1") == 5

    # Reorder to [C2, C1] -> priorities 1,2
    reorder_punta_collections(["C2", "C1"])
    df = list_punta_collections()
    assert list(df["collection"])[:2] == ["C2", "C1"]
    assert list(df["priority"])[:2] == [1, 2]

