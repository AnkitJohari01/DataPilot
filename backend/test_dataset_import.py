"""
Dataset import tests — run directly against the configured database:

    python test_dataset_import.py

Not pytest-based, matching this project's existing test_*.py convention
(no test framework is installed). Creates its own dataset rows and drops
its own imported tables at the end, so it's safe to re-run.
"""
import io

import pandas as pd
from fastapi import HTTPException
from sqlalchemy import text

from app.database.connection import engine
from app.database.metadata import (
    DATASET_SCHEMA,
    create_dataset_import,
    delete_dataset,
    list_datasets,
    normalize_identifier,
)
from app.main import _dataframes_from_upload

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


try:
    # 1. CSV import creates exactly one table
    csv_bytes = b"name,amount\nAlice,10\nBob,20\n"
    tables = _dataframes_from_upload("customers test.csv", csv_bytes)
    assert list(tables.keys()) == ["customers test"]

    dataset = create_dataset_import("Customers Test", tables)
    created_dataset_ids.append(dataset["id"])
    created_table_names += [t["db_table_name"] for t in dataset["tables"]]

    assert len(dataset["tables"]) == 1
    assert dataset["tables"][0]["row_count"] == 2
    print("CSV import test passed.")

    # 2. Multi-sheet Excel import: one table per non-empty sheet, empty sheet skipped
    xlsx_buffer = io.BytesIO()
    with pd.ExcelWriter(xlsx_buffer, engine="openpyxl") as writer:
        pd.DataFrame({"region": ["East", "West"], "sales": [100, 200]}).to_excel(
            writer, sheet_name="Regions", index=False
        )
        pd.DataFrame({"product": ["Widget"], "price": [9.99]}).to_excel(
            writer, sheet_name="Products", index=False
        )
        pd.DataFrame().to_excel(writer, sheet_name="Empty", index=False)
    xlsx_bytes = xlsx_buffer.getvalue()

    tables = _dataframes_from_upload("Workbook.xlsx", xlsx_bytes)
    assert set(tables.keys()) == {"Regions", "Products"}, tables.keys()

    dataset = create_dataset_import("Workbook Test", tables)
    created_dataset_ids.append(dataset["id"])
    created_table_names += [t["db_table_name"] for t in dataset["tables"]]

    assert len(dataset["tables"]) == 2
    print("Multi-sheet Excel import test passed.")

    # 3. Empty CSV (headers only, no rows) is rejected
    try:
        _dataframes_from_upload("empty.csv", b"name,amount\n")
        assert False, "expected HTTPException for an empty CSV"
    except HTTPException as e:
        assert e.status_code == 400
    print("Empty CSV rejection test passed.")

    # 4. Unsupported extension is rejected
    try:
        _dataframes_from_upload("notes.txt", b"hello")
        assert False, "expected HTTPException for an unsupported extension"
    except HTTPException as e:
        assert e.status_code == 400
    print("Unsupported extension rejection test passed.")

    # 5. A failed import leaves no visible dataset (single transaction, full rollback)
    conflict_tables = _dataframes_from_upload("conflict test.csv", csv_bytes)
    conflicting_name = normalize_identifier("conflict test", set())
    with engine.begin() as connection:
        connection.execute(
            text(f'CREATE TABLE "{DATASET_SCHEMA}"."{conflicting_name}" (id INT)')
        )
    created_table_names.append(conflicting_name)

    dataset_ids_before = {d["id"] for d in list_datasets()}
    try:
        create_dataset_import("Conflict Test", conflict_tables)
        assert False, "expected an exception on table-name collision"
    except Exception:
        pass
    dataset_ids_after = {d["id"] for d in list_datasets()}
    assert dataset_ids_before == dataset_ids_after, "a dataset row leaked after a failed import"
    print("Rollback-on-failure test passed.")

    # 6. Identifier normalization + uniqueness within one import
    messy_df = pd.DataFrame(
        {
            "First Name": ["A"],
            "first name": ["B"],
            "Amount ($)": [1],
        }
    )
    dataset = create_dataset_import("Messy Columns Test", {"Messy Sheet": messy_df})
    created_dataset_ids.append(dataset["id"])
    created_table_names += [t["db_table_name"] for t in dataset["tables"]]

    column_map = dataset["tables"][0]["column_map"]
    assert len(set(column_map.values())) == len(column_map), "column names collided after normalization"
    assert column_map["First Name"] != column_map["first name"]
    print("Identifier normalization test passed.")

    # 7. Re-importing the same file creates a new dataset, never replaces the old one
    tables_again = _dataframes_from_upload("customers test.csv", csv_bytes)
    dataset_again = create_dataset_import("Customers Test", tables_again)
    created_dataset_ids.append(dataset_again["id"])
    created_table_names += [t["db_table_name"] for t in dataset_again["tables"]]

    assert dataset_again["id"] != dataset["id"]
    all_ids = {d["id"] for d in list_datasets()}
    assert dataset["id"] in all_ids and dataset_again["id"] in all_ids
    print("Re-import does not replace existing dataset test passed.")

    # 8. The registry is read live (no cache) — a fresh import is visible immediately
    assert dataset_again["id"] in {d["id"] for d in list_datasets()}
    print("Live registry read test passed.")

    # 9. Deleting a dataset drops its table(s) and removes its registry rows;
    # it's no longer selectable, and deleting an unknown id is a no-op.
    to_delete_tables = _dataframes_from_upload("deleteme.csv", csv_bytes)
    to_delete = create_dataset_import("Delete Me Test", to_delete_tables)
    deleted_table_name = to_delete["tables"][0]["db_table_name"]

    assert delete_dataset(to_delete["id"]) is True
    assert to_delete["id"] not in {d["id"] for d in list_datasets()}
    with engine.connect() as connection:
        table_exists = connection.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = :schema AND table_name = :table"
            ),
            {"schema": DATASET_SCHEMA, "table": deleted_table_name},
        ).first()
    assert table_exists is None, "imported table was not dropped on delete"
    assert delete_dataset(999999) is False, "deleting an unknown id should return False"
    print("Delete dataset test passed.")

    print("\nAll dataset import tests passed.")

finally:
    _cleanup()
