import pandas as pd
from dataforge.matching import Match


def test_match_from_row_handles_missing_values():
    s = pd.Series({"oz_sku": None, "wb_sku": None, "barcode_hit": "B1", "matched_by": "any↔any", "match_score": None, "punta_external_code_oz": None})
    m = Match.from_row(s)
    assert m.oz_sku is None
    assert m.wb_sku is None
    assert m["barcode_hit"] == "B1"
    assert m.get("nonexistent", 42) == 42

