"""Offline currency and response-format checks."""
import io
import os
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("GEMINI_API_KEY", "offline-test-key")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost/datapilot")

import pandas as pd
from openpyxl import Workbook
from app.main import _dataframes_from_upload
from app.services.currency_service import dataframe_currency_context, build_currency_context, output_currency
from app.services.gemini_service import build_insights_prompt
from app.database.metadata import create_dataset_import
from app.services.strict_answer_service import build_dataset_schema_text


class CurrencyOutputTests(unittest.TestCase):
    def test_headers_values_codes_and_default(self):
        frame = pd.DataFrame({"Sales (INR)": [123.45], "Currency": ["INR"], "Cost": ["₹20"]})
        context = dataframe_currency_context(frame)
        self.assertEqual(context["Sales (INR)"], ["₹"])
        self.assertEqual(context["Cost"], ["₹"])
        self.assertEqual(context["Currency"], ["₹"])
        self.assertEqual(output_currency("Sales: 100"), "$")
        self.assertEqual(output_currency("Currency: INR"), "₹")
        self.assertEqual(output_currency("Sales (USD): $100"), "$")
        self.assertIsNone(output_currency("Currency: USD, INR"))
        self.assertEqual(output_currency("Currency: XAF"), "XAF")

    def test_excel_currency_formats_survive_upload_parsing(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Sales", "Orders"])
        sheet.append([123.45, 2])
        sheet["A2"].number_format = '₹#,##0.00'
        content = io.BytesIO()
        workbook.save(content)
        frame = _dataframes_from_upload("sales.xlsx", content.getvalue())[sheet.title]
        self.assertEqual(dataframe_currency_context(frame)["Sales"], ["₹"])
        self.assertEqual(frame.iloc[0]["Sales"], 123.45)

    def test_currency_metadata_is_persisted_as_a_column_comment(self):
        frame = pd.DataFrame({"Sales (INR)": [100]})
        connection = MagicMock()
        connection.execute.return_value.scalar_one.return_value = 1
        connection.execute.return_value.all.return_value = []
        with patch("app.database.metadata.ensure_registry_tables"), patch("app.database.metadata.engine") as engine:
            engine.begin.return_value.__enter__.return_value = connection
            create_dataset_import("Sales", {"Orders": frame})
        statements = [str(call.args[0]) for call in connection.execute.call_args_list]
        self.assertTrue(any('COMMENT ON COLUMN "imported"."orders"."sales_inr"' in sql and "Currency: ₹" in sql for sql in statements))

    def test_selected_schema_includes_persisted_currency(self):
        with patch("app.services.strict_answer_service.inspect") as inspect, patch("app.services.strict_answer_service.engine"):
            inspect.return_value.get_columns.return_value = [{"name": "sales", "type": "NUMERIC", "comment": "Currency: ₹"}]
            schema = build_dataset_schema_text([{"db_table_name": "orders", "dataset_name": "Sales", "display_table_name": "Orders", "column_map": {"Sales": "sales"}}])
        self.assertIn("Currency: ₹", schema)
        self.assertEqual(output_currency(build_currency_context(schema, [])), "₹")

    def test_prompt_is_concise_uses_currency_and_percentage_words(self):
        prompt = build_insights_prompt("total sales", [{"sales": 100}], unit_context="Sales: Currency: ₹")
        self.assertIn("Currency: ₹", prompt)
        self.assertIn("percentage", prompt)
        self.assertIn("concise", prompt)
        self.assertNotIn("Be thorough", prompt)
        self.assertIn("Do not guess", prompt)


if __name__ == "__main__":
    unittest.main()
