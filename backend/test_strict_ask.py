"""
Strict, dataset-scoped /api/ask tests — run directly against the configured
database:

    python test_strict_ask.py

Not pytest-based, matching this project's existing test_*.py convention (no
test framework is installed). Creates its own dataset via
create_dataset_import and drops it at the end, so it's safe to re-run.
Gemini calls are mocked (unittest.mock, stdlib) so this never needs a real
API key or makes a network call.
"""
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import text

from app.database.connection import engine, SessionLocal
from app.database.metadata import DATASET_SCHEMA, create_dataset_import
from app.main import ask_strict, StrictAskRequest
import app.main as main_module

created_dataset_ids: list[int] = []
created_table_names: list[str] = []


def _cleanup():
    with engine.begin() as connection:
        for table_name in created_table_names:
            connection.execute(
                text(f'DROP TABLE IF EXISTS "{DATASET_SCHEMA}"."{table_name}"')
            )
        for dataset_id in created_dataset_ids:
            connection.execute(
                text("DELETE FROM dp_dataset_tables WHERE dataset_id = :id"),
                {"id": dataset_id},
            )
            connection.execute(
                text("DELETE FROM dp_datasets WHERE id = :id"), {"id": dataset_id}
            )


def _call(question: str, dataset_ids: list[int]):
    """Call the route function directly (no HTTP layer / test client dep)."""
    db = SessionLocal()
    try:
        request = StrictAskRequest(question=question, dataset_ids=dataset_ids)
        return ask_strict(request, db=db)
    finally:
        db.close()


try:
    import pandas as pd

    sales_df = pd.DataFrame(
        {
            "Region": ["East", "West", "East", "West"],
            "Amount": [100, 200, 150, 50],
        }
    )
    dataset = create_dataset_import("Strict Ask Test Sales", {"Sales": sales_df})
    created_dataset_ids.append(dataset["id"])
    created_table_names += [t["db_table_name"] for t in dataset["tables"]]
    sales_table = dataset["tables"][0]["db_table_name"]
    region_col = dataset["tables"][0]["column_map"]["Region"]
    amount_col = dataset["tables"][0]["column_map"]["Amount"]

    other_dataset = create_dataset_import(
        "Strict Ask Test Other",
        {"Other": pd.DataFrame({"Widget": ["A"], "Count": [1]})},
    )
    created_dataset_ids.append(other_dataset["id"])
    created_table_names += [t["db_table_name"] for t in other_dataset["tables"]]
    other_table = other_dataset["tables"][0]["db_table_name"]
    other_widget_col = other_dataset["tables"][0]["column_map"]["Widget"]

    # 1. No dataset selected -> 400, no LLM call attempted
    with patch.object(main_module, "generate_sql") as mock_gen:
        try:
            _call("total amount", [])
            assert False, "expected HTTPException for empty dataset_ids"
        except HTTPException as e:
            assert e.status_code == 400
        mock_gen.assert_not_called()
    print("No-dataset-selected rejection test passed.")

    # 2. Invalid dataset id -> 400
    with patch.object(main_module, "generate_sql") as mock_gen:
        try:
            _call("total amount", [-9999])
            assert False, "expected HTTPException for an unknown dataset id"
        except HTTPException as e:
            assert e.status_code == 400
        mock_gen.assert_not_called()
    print("Invalid-dataset-id rejection test passed.")

    # 3. Query referencing a real table outside the selected datasets -> rejected
    with patch.object(
        main_module,
        "generate_sql",
        return_value=f'SELECT * FROM "{DATASET_SCHEMA}"."{other_table}"',
    ):
        try:
            _call("total amount", [dataset["id"]])
            assert False, "expected HTTPException for an out-of-scope table"
        except HTTPException as e:
            assert e.status_code == 400
            assert "outside the selected datasets" in e.detail
    print("Unselected-table rejection test passed.")

    # 4. Non-SELECT statement -> rejected, never executed
    with patch.object(
        main_module,
        "generate_sql",
        return_value=f'DELETE FROM "{DATASET_SCHEMA}"."{sales_table}"',
    ):
        try:
            _call("delete everything", [dataset["id"]])
            assert False, "expected HTTPException for a non-SELECT statement"
        except HTTPException as e:
            assert e.status_code == 400
    with engine.connect() as connection:
        remaining = connection.execute(
            text(f'SELECT COUNT(*) FROM "{DATASET_SCHEMA}"."{sales_table}"')
        ).scalar_one()
        assert remaining == 4, "rows were deleted — non-SELECT statement was executed!"
    print("Non-SELECT rejection test passed.")

    # 5. Multi-statement SQL -> rejected
    with patch.object(
        main_module,
        "generate_sql",
        return_value=(
            f'SELECT 1; DROP TABLE "{DATASET_SCHEMA}"."{sales_table}"'
        ),
    ):
        try:
            _call("drop it", [dataset["id"]])
            assert False, "expected HTTPException for a multi-statement query"
        except HTTPException as e:
            assert e.status_code == 400
    print("Multi-statement rejection test passed.")

    # 6. Syntactically valid SELECT, passes identifier validation (the column
    # is real and in-scope for *some* selected table), but fails at actual
    # execution because it doesn't exist on *this* table -> rejected, not a 500.
    # (validate_sql checks column names globally, not per-table, matching the
    # existing /api/ask behavior — this is exactly the gap that surfaces as a
    # DB-level failure rather than a validation-level one.)
    with patch.object(
        main_module,
        "generate_sql",
        return_value=(
            f'SELECT "{other_widget_col}" FROM "{DATASET_SCHEMA}"."{sales_table}"'
        ),
    ):
        try:
            _call("bad column", [dataset["id"], other_dataset["id"]])
            assert False, "expected HTTPException for a column that fails at execution"
        except HTTPException as e:
            assert e.status_code == 400
            assert "query failed" in e.detail.lower()
    print("Failed-query (execution-time) rejection test passed.")

    # 7. Deterministic response shape: only the documented fields, no free-text insight
    with patch.object(
        main_module,
        "generate_sql",
        return_value=(
            f'SELECT "{region_col}", SUM("{amount_col}") AS total '
            f'FROM "{DATASET_SCHEMA}"."{sales_table}" GROUP BY "{region_col}"'
        ),
    ):
        response = _call("total amount by region", [dataset["id"]])
        assert set(response.keys()) == {
            "question",
            "sql",
            "rows",
            "result_count",
            "sources",
            "declined",
            "message",
        }
        assert response["declined"] is False
        assert response["result_count"] == 2
        assert response["message"] is None
    print("Deterministic response shape test passed.")

    # 8. Empty result -> deterministic "no matching evidence" message
    with patch.object(
        main_module,
        "generate_sql",
        return_value=(
            f'SELECT * FROM "{DATASET_SCHEMA}"."{sales_table}" '
            f'WHERE "{region_col}" = \'Nowhere\''
        ),
    ):
        response = _call("amount in Nowhere region", [dataset["id"]])
        assert response["result_count"] == 0
        assert response["rows"] == []
        assert response["message"] == "No matching evidence was found in the selected datasets."
    print("Empty-result message test passed.")

    # 9. Causal/recommendation question declined, no SQL generation attempted
    with patch.object(main_module, "generate_sql") as mock_gen:
        response = _call("why did sales drop in the West region", [dataset["id"]])
        assert response["declined"] is True
        assert response["sql"] is None
        assert response["rows"] == []
        mock_gen.assert_not_called()
    print("Causal-question decline test passed.")

    # 10. generate_insights / generate_diagnostic_sql never invoked on this path
    with patch.object(
        main_module,
        "generate_sql",
        return_value=f'SELECT * FROM "{DATASET_SCHEMA}"."{sales_table}"',
    ), patch.object(main_module, "generate_insights") as mock_insights, patch.object(
        main_module, "generate_diagnostic_sql"
    ) as mock_diag:
        _call("all rows", [dataset["id"]])
        _call("why did sales drop", [dataset["id"]])
        mock_insights.assert_not_called()
        mock_diag.assert_not_called()
    print("generate_insights/generate_diagnostic_sql never-called test passed.")

    print("\nAll strict-ask tests passed.")

finally:
    _cleanup()
