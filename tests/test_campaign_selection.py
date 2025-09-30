from __future__ import annotations

from datetime import datetime, timedelta

import duckdb
import pytest
from dataforge.campaign_selection import select_campaign_candidates


@pytest.fixture
def mock_db():
    """Создать in-memory DuckDB с тестовыми данными."""
    con = duckdb.connect(":memory:")

    # Создать таблицы
    con.execute("""
        CREATE TABLE oz_products (
            oz_sku BIGINT,
            oz_vendor_code VARCHAR,
            fbo_available INTEGER
        )
    """)

    con.execute("""
        CREATE TABLE oz_orders (
            oz_vendor_code VARCHAR,
            processing_date TIMESTAMP,
            quantity INTEGER
        )
    """)

    # Вставить тестовые данные oz_products
    con.execute("""
        INSERT INTO oz_products VALUES
        (1001, 'OZ-SIZE-1', 10),
        (1002, 'OZ-SIZE-2', 20),
        (1003, 'OZ-SIZE-3', 5),
        (1004, 'OZ-SIZE-4', 2),
        (2001, 'OZ-SIZE-5', 15),
        (2002, 'OZ-SIZE-6', 8)
    """)

    # Вставить тестовые данные oz_orders (за последние 14 дней)
    today = datetime.now()
    con.execute(
        """
        INSERT INTO oz_orders VALUES
        (?, ?, ?),
        (?, ?, ?),
        (?, ?, ?),
        (?, ?, ?),
        (?, ?, ?),
        (?, ?, ?)
    """,
        [
            "OZ-SIZE-1", today - timedelta(days=1), 5,
            "OZ-SIZE-2", today - timedelta(days=3), 10,
            "OZ-SIZE-2", today - timedelta(days=5), 5,
            "OZ-SIZE-3", today - timedelta(days=7), 3,
            "OZ-SIZE-5", today - timedelta(days=2), 20,
            "OZ-SIZE-6", today - timedelta(days=4), 10,
        ],
    )

    yield con
    con.close()


def test_select_campaign_candidates_basic(mock_db, monkeypatch):
    """Базовый сценарий: 1 wb_sku с достаточным количеством кандидатов."""

    def mock_find_oz_by_wb(wb_sku, limit=None, con=None):
        if wb_sku == "WB-123":
            return [
                {"oz_sku": "1001", "wb_sku": "WB-123"},
                {"oz_sku": "1002", "wb_sku": "WB-123"},
                {"oz_sku": "1003", "wb_sku": "WB-123"},
            ]
        return []

    monkeypatch.setattr("dataforge.campaign_selection.find_oz_by_wb", mock_find_oz_by_wb)

    results = select_campaign_candidates(
        wb_skus=["WB-123"],
        min_stock=5,
        min_candidates=2,
        max_candidates=5,
        con=mock_db,
    )

    assert len(results) == 3
    assert results[0]["group_number"] == 1
    assert results[0]["wb_sku"] == "WB-123"
    assert results[0]["oz_vendor_code"] == "OZ-SIZE-2"  # Первый по заказам (15 total)
    assert results[0]["size_orders"] == 15
    assert results[1]["oz_vendor_code"] == "OZ-SIZE-1"  # Второй по заказам (5)
    assert results[2]["oz_vendor_code"] == "OZ-SIZE-3"  # Третий (3 заказа, остаток 5)


def test_select_campaign_candidates_insufficient(mock_db, monkeypatch):
    """Группа с недостаточным количеством кандидатов не попадает в результат."""

    def mock_find_oz_by_wb(wb_sku, limit=None, con=None):
        if wb_sku == "WB-456":
            return [
                {"oz_sku": "1001", "wb_sku": "WB-456"},
            ]
        return []

    monkeypatch.setattr("dataforge.campaign_selection.find_oz_by_wb", mock_find_oz_by_wb)

    results = select_campaign_candidates(
        wb_skus=["WB-456"],
        min_stock=5,
        min_candidates=3,  # Требуется минимум 3, но есть только 1
        max_candidates=5,
        con=mock_db,
    )

    assert len(results) == 0


def test_select_campaign_candidates_stock_filter(mock_db, monkeypatch):
    """Фильтрация по минимальному остатку работает корректно."""

    def mock_find_oz_by_wb(wb_sku, limit=None, con=None):
        if wb_sku == "WB-789":
            return [
                {"oz_sku": "1001", "wb_sku": "WB-789"},  # stock=10
                {"oz_sku": "1003", "wb_sku": "WB-789"},  # stock=5
                {"oz_sku": "1004", "wb_sku": "WB-789"},  # stock=2 (отфильтруется)
            ]
        return []

    monkeypatch.setattr("dataforge.campaign_selection.find_oz_by_wb", mock_find_oz_by_wb)

    results = select_campaign_candidates(
        wb_skus=["WB-789"],
        min_stock=5,  # Минимальный остаток 5
        min_candidates=1,
        max_candidates=5,
        con=mock_db,
    )

    assert len(results) == 2
    assert all(r["size_stock"] >= 5 for r in results)


def test_select_campaign_candidates_orders_sorting(mock_db, monkeypatch):
    """Сортировка по заказам работает правильно (DESC)."""

    def mock_find_oz_by_wb(wb_sku, limit=None, con=None):
        if wb_sku == "WB-SORT":
            return [
                {"oz_sku": "1001", "wb_sku": "WB-SORT"},  # 5 заказов
                {"oz_sku": "1002", "wb_sku": "WB-SORT"},  # 15 заказов
                {"oz_sku": "1003", "wb_sku": "WB-SORT"},  # 3 заказа
            ]
        return []

    monkeypatch.setattr("dataforge.campaign_selection.find_oz_by_wb", mock_find_oz_by_wb)

    results = select_campaign_candidates(
        wb_skus=["WB-SORT"],
        min_stock=0,
        min_candidates=1,
        max_candidates=5,
        con=mock_db,
    )

    assert len(results) == 3
    # Проверяем порядок: сначала больше заказов
    assert results[0]["oz_vendor_code"] == "OZ-SIZE-2"  # 15 заказов
    assert results[1]["oz_vendor_code"] == "OZ-SIZE-1"  # 5 заказов
    assert results[2]["oz_vendor_code"] == "OZ-SIZE-3"  # 3 заказа


def test_select_campaign_candidates_model_aggregation(mock_db, monkeypatch):
    """Агрегаты на уровне модели считаются корректно."""

    def mock_find_oz_by_wb(wb_sku, limit=None, con=None):
        if wb_sku == "WB-AGG":
            return [
                {"oz_sku": "1001", "wb_sku": "WB-AGG"},  # stock=10, orders=5
                {"oz_sku": "1002", "wb_sku": "WB-AGG"},  # stock=20, orders=15
                {"oz_sku": "1003", "wb_sku": "WB-AGG"},  # stock=5, orders=3
            ]
        return []

    monkeypatch.setattr("dataforge.campaign_selection.find_oz_by_wb", mock_find_oz_by_wb)

    results = select_campaign_candidates(
        wb_skus=["WB-AGG"],
        min_stock=0,
        min_candidates=1,
        max_candidates=2,  # Ограничиваем 2 кандидатами
        con=mock_db,
    )

    assert len(results) == 2

    # model_stock и model_orders должны быть одинаковыми для всех кандидатов группы
    # и учитывать ВСЕ товары группы (даже те, что не попали в результат)
    expected_model_stock = 10 + 20 + 5  # Все 3 товара
    expected_model_orders = 5 + 15 + 3  # Все 3 товара

    assert results[0]["model_stock"] == expected_model_stock
    assert results[0]["model_orders"] == expected_model_orders
    assert results[1]["model_stock"] == expected_model_stock
    assert results[1]["model_orders"] == expected_model_orders


def test_select_campaign_candidates_multiple_groups(mock_db, monkeypatch):
    """Несколько wb_sku формируют разные группы с правильной нумерацией."""

    def mock_find_oz_by_wb(wb_sku, limit=None, con=None):
        if wb_sku == "WB-GROUP-1":
            return [
                {"oz_sku": "1001", "wb_sku": "WB-GROUP-1"},
                {"oz_sku": "1002", "wb_sku": "WB-GROUP-1"},
            ]
        if wb_sku == "WB-GROUP-2":
            return [
                {"oz_sku": "2001", "wb_sku": "WB-GROUP-2"},
                {"oz_sku": "2002", "wb_sku": "WB-GROUP-2"},
            ]
        return []

    monkeypatch.setattr("dataforge.campaign_selection.find_oz_by_wb", mock_find_oz_by_wb)

    results = select_campaign_candidates(
        wb_skus=["WB-GROUP-1", "WB-GROUP-2"],
        min_stock=5,
        min_candidates=2,
        max_candidates=5,
        con=mock_db,
    )

    assert len(results) == 4

    # Проверяем нумерацию групп
    group_1_results = [r for r in results if r["wb_sku"] == "WB-GROUP-1"]
    group_2_results = [r for r in results if r["wb_sku"] == "WB-GROUP-2"]

    assert len(group_1_results) == 2
    assert len(group_2_results) == 2
    assert all(r["group_number"] == 1 for r in group_1_results)
    assert all(r["group_number"] == 2 for r in group_2_results)


def test_select_campaign_candidates_empty_input():
    """Пустой список wb_skus возвращает пустой результат."""
    results = select_campaign_candidates(
        wb_skus=[],
        min_stock=0,
        min_candidates=1,
        max_candidates=5,
    )
    assert results == []


def test_select_campaign_candidates_invalid_params():
    """Некорректные параметры вызывают ошибку."""
    with pytest.raises(ValueError, match="min_candidates не может быть больше max_candidates"):
        select_campaign_candidates(
            wb_skus=["WB-123"],
            min_stock=0,
            min_candidates=10,
            max_candidates=5,
        )