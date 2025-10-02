"""Tests for Punta priority-based primary_barcode selection."""
from __future__ import annotations

import json
import os

import pandas as pd
import pytest

from dataforge.imports.punta_priority import (
    _parse_barcodes,
    enrich_primary_barcode_by_punta,
)


def _get_test_credentials():
    """Get MotherDuck credentials from secrets.toml or environment variables."""
    try:
        import streamlit as st
        md_token = st.secrets.get("md_token")
        md_database = st.secrets.get("md_database")
        if md_token:
            return md_token, md_database
    except Exception:
        pass
    
    # Fallback to environment variables
    return os.environ.get("MOTHERDUCK_TOKEN"), os.environ.get("MOTHERDUCK_DATABASE", "dataforge")


class TestParseBarcodes:
    """Tests for _parse_barcodes helper function."""

    def test_empty_inputs(self):
        """Test handling of empty/None inputs."""
        assert _parse_barcodes(None) == []
        assert _parse_barcodes("") == []
        assert _parse_barcodes([]) == []

    def test_list_input(self):
        """Test parsing from list."""
        assert _parse_barcodes(["123", "456", "789"]) == ["123", "456", "789"]
        assert _parse_barcodes(["123", "", "456"]) == ["123", "456"]

    def test_json_string(self):
        """Test parsing from JSON string."""
        json_str = json.dumps(["111", "222", "333"])
        assert _parse_barcodes(json_str) == ["111", "222", "333"]

    def test_semicolon_separated(self):
        """Test parsing from semicolon-separated string."""
        assert _parse_barcodes("111;222;333") == ["111", "222", "333"]
        assert _parse_barcodes("111; 222 ; 333") == ["111", "222", "333"]

    def test_single_value(self):
        """Test single value string."""
        assert _parse_barcodes("123456") == ["123456"]


class TestEnrichPrimaryBarcodeByPunta:
    """Tests for enrich_primary_barcode_by_punta main function."""

    def test_empty_dataframe(self):
        """Test with empty DataFrame."""
        df = pd.DataFrame()
        result = enrich_primary_barcode_by_punta(df)
        assert result.empty

    def test_no_barcodes_column(self):
        """Test with DataFrame missing 'barcodes' column."""
        df = pd.DataFrame({"wb_sku": [1, 2, 3]})
        result = enrich_primary_barcode_by_punta(df)
        assert list(result.columns) == ["wb_sku"]

    def test_fallback_to_first_barcode(self):
        """Test fallback when no Punta mapping exists (uses fake barcodes not in DB)."""
        md_token, md_database = _get_test_credentials()
        
        # Use fake barcodes that don't exist in Punta
        df = pd.DataFrame({
            "wb_sku": [123, 456],
            "barcodes": [
                json.dumps(["FAKE_BC001", "FAKE_BC002", "FAKE_BC003"]),
                json.dumps(["FAKE_BC100", "FAKE_BC200"]),
            ]
        })
        
        result = enrich_primary_barcode_by_punta(
            df,
            md_token=md_token,
            md_database=md_database,
        )
        
        # Should select first barcode as fallback when no Punta mapping found
        assert result["primary_barcode"].tolist() == ["FAKE_BC001", "FAKE_BC100"]

    def test_empty_barcodes_list(self):
        """Test rows with empty barcodes."""
        md_token, md_database = _get_test_credentials()
        
        df = pd.DataFrame({
            "wb_sku": [123, 456, 789],
            "barcodes": [
                json.dumps(["FAKE_BC001"]),
                json.dumps([]),  # empty
                "",  # empty string
            ]
        })
        
        result = enrich_primary_barcode_by_punta(df, md_token=md_token, md_database=md_database)
        
        assert result["primary_barcode"].tolist()[0] == "FAKE_BC001"
        assert pd.isna(result["primary_barcode"].tolist()[1])
        assert pd.isna(result["primary_barcode"].tolist()[2])

    def test_priority_selection_integration(self):
        """Integration test: select barcode by priority with real DB data.
        
        Uses real barcodes from DB:
        - 4815550505853 → ОЗ-23 (priority 10, older)
        - 4815694741544 → ОЗ-25 (priority 14, newer)
        
        Expected: 4815694741544 selected (HIGHER priority number = more recent)
        """
        md_token, md_database = _get_test_credentials()
        
        if not md_token:
            pytest.skip("No MotherDuck token available (set in secrets.toml or MOTHERDUCK_TOKEN)")
        
        df = pd.DataFrame({
            "wb_sku": [168568189],
            "barcodes": [json.dumps(["4815550505853", "4815694741544"])],
        })
        
        result = enrich_primary_barcode_by_punta(
            df,
            md_token=md_token,
            md_database=md_database,
        )
        
        # Should select barcode from collection with MAX(priority)
        assert result["primary_barcode"].tolist() == ["4815694741544"]


class TestPriorityLogic:
    """Tests for priority comparison logic."""

    def test_priority_comparison_example(self):
        """Document expected behavior: HIGHER number = HIGHER priority (more recent)."""
        priorities = {
            "OZ-25": 14,  # Highest priority (most recent)
            "OZ-24": 12,
            "OZ-23": 10,  # Lowest priority (oldest)
        }
        
        # Simulate barcode mapping
        barcode_priorities = {
            "BC_NEW": 14,  # Should be selected (higher number)
            "BC_OLD": 10,
        }
        
        # Find maximum (best) priority
        best_bc = max(barcode_priorities, key=barcode_priorities.get)
        assert best_bc == "BC_NEW"
        assert barcode_priorities[best_bc] == 14
