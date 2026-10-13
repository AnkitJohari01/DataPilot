"""Offline route checks: python -m unittest test_dataset_summary.py."""
import os
import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

os.environ.setdefault("GEMINI_API_KEY", "offline-test-key")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost/datapilot")

from fastapi import HTTPException
import app.main as main


class DatasetSummaryTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.tables = [{"db_table_name": "orders", "column_map": {"Revenue": "revenue"}}]
        self.resolve = self.stack.enter_context(patch.object(main, "resolve_selected_tables", return_value=self.tables))
        self.schema = self.stack.enter_context(patch.object(main, "build_dataset_schema_text", return_value="selected orders only"))
        self.sql = "SELECT SUM(revenue) AS total_sales FROM imported.orders"
        self.generate_sql = self.stack.enter_context(patch.object(main, "generate_sql", return_value=self.sql))
        self.validate = self.stack.enter_context(patch.object(main, "validate_dataset_scoped_sql", return_value=(True, self.sql)))
        self.sources = [{"table": "orders", "columns": ["revenue"]}]
        self.stack.enter_context(patch.object(main, "extract_data_sources", return_value=self.sources))
        self.insights = self.stack.enter_context(patch.object(main, "generate_insights", return_value={"text": "Total sales are 500.12."}))
        self.diagnostics = self.stack.enter_context(patch.object(main, "generate_diagnostic_sql"))
        self.db = MagicMock()
        self.rows = [{"total_sales": "500.1234"}]
        self.db.execute.return_value.mappings.return_value.all.return_value = self.rows
        self.request = main.StrictAskRequest(question="summary of sales", dataset_ids=[1])

    def test_summary_uses_only_selected_query_rows_and_keeps_response_fields(self):
        response = main.StrictAskResponse(**main.ask_strict(self.request, self.db))
        self.assertEqual(response.insights["text"], "Total sales are 500.12.")
        self.assertEqual(response.rows, self.rows)
        self.assertEqual(response.result_count, 1)
        self.assertEqual(response.sources, self.sources)
        self.assertEqual(response.sql, self.sql)
        self.resolve.assert_called_once_with([1])
        self.schema.assert_called_once_with(self.tables)
        self.validate.assert_called_once_with(self.sql, {"orders", "revenue"})
        self.insights.assert_called_once_with(self.request.question, self.rows, data_sources=self.sources, unit_context="")
        self.diagnostics.assert_not_called()

    def test_empty_results_keep_message_without_generating_summary(self):
        self.db.execute.return_value.mappings.return_value.all.return_value = []
        response = main.StrictAskResponse(**main.ask_strict(self.request, self.db))
        self.assertEqual(response.message, main.NO_EVIDENCE_MESSAGE)
        self.assertEqual(response.insights, {})
        self.insights.assert_not_called()

    def test_currency_context_reaches_summary_and_response(self):
        self.schema.return_value = "- sales (NUMERIC, measure) | Currency: ₹"
        response = main.StrictAskResponse(**main.ask_strict(self.request, self.db))
        self.assertEqual(response.currency, "₹")
        self.assertIn("Currency: ₹", self.insights.call_args.kwargs["unit_context"])

    def test_summary_failure_preserves_results_with_clear_message(self):
        self.insights.side_effect = RuntimeError("offline")
        response = main.StrictAskResponse(**main.ask_strict(self.request, self.db))
        self.assertEqual(response.rows, self.rows)
        self.assertIn("summary", response.message.lower())
        self.assertEqual(response.insights, {})

    def test_declined_question_never_generates_summary_or_sql(self):
        self.request.question = "why did sales drop?"
        response = main.StrictAskResponse(**main.ask_strict(self.request, self.db))
        self.assertTrue(response.declined)
        self.generate_sql.assert_not_called()
        self.insights.assert_not_called()

    def test_invalid_query_never_runs_or_generates_summary(self):
        self.validate.return_value = (False, "Query references a table outside the selected datasets: other")
        with self.assertRaises(HTTPException) as error:
            main.ask_strict(self.request, self.db)
        self.assertEqual(error.exception.status_code, 400)
        self.db.execute.assert_not_called()
        self.insights.assert_not_called()


if __name__ == "__main__":
    unittest.main()
