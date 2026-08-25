# """Wraps Gemini calls for SQL generation."""

# import re

# from google import genai
# from app.config.settings import settings
# from sqlglot import exp, parse
# from sqlglot.errors import ParseError

# client = genai.Client(api_key=settings.gemini_api_key)

# SQL_SYSTEM_INSTRUCTION = """You generate PostgreSQL queries from natural-language questions.

# The user does not know the database's table or column names. Business terms in their
# question (e.g. "revenue", "sales", "product") almost always map to a real column or a
# computation over real columns — your job is to find that mapping, not to reject the question.

# Rules:
# - Use ONLY the tables and columns given in the schema below. Never invent a table or column name.
# - If the question uses a business term with no exact matching column (e.g. "revenue" when the
#   column is "sales_amount"), map it to the closest real column or compute it with an aggregate
#   (e.g. SUM(sales_amount)). Do this silently — do not ask the user to clarify.
# - If the question refers to an entity loosely (e.g. "product 12" when the real identifier is
#   product_id or product_code), match it to the appropriate key column and filter on it.
# - Only generate SELECT or WITH queries. Never INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, or CREATE.
# - Use explicit JOIN conditions based on the foreign keys shown.
# - Add a reasonable LIMIT unless the question clearly needs all rows (e.g. an aggregate).
# - Use deterministic ORDER BY when ranking or returning top-N results.
# - Return ONLY the raw SQL query. No markdown fences, no explanation, no commentary.
# """


# def generate_sql(question: str, schema_text: str, history: list[dict] = None) -> str:
#     history_text = ""
#     if history:
#         recent = history[-3:]
#         history_text = "\n".join(
#             f"Q: {h['question']}\nSQL: {h['sql']}" for h in recent
#         )
#         history_text = f"\nPrevious questions in this conversation:\n{history_text}\n"

#     prompt = f"Schema:\n{schema_text}\n{history_text}\nQuestion: {question}\n\nSQL:"

#     try:
#         response = client.models.generate_content(
#             model="gemini-3.1-flash-lite",
#             contents=prompt,
#             config={
#                 "system_instruction": SQL_SYSTEM_INSTRUCTION,
#                 "temperature": 0,
#                 "http_options": {"timeout": 20000},  # 20 seconds, in ms
#             },
#         )
#     except Exception as e:
#         raise RuntimeError(f"SQL generation failed: {e}")

#     sql = response.text.strip()
#     if sql.startswith("```"):
#         sql = sql.strip("`").removeprefix("sql").strip()
#     return sql


# def build_insights_prompt(question: str, rows: list[dict], data_sources: list[dict] | None = None) -> str:
#     """Build a dynamic, data-grounded prompt for the answer AI."""
#     return f"""
# Question: {question}

# Result rows (use only these values; at most the first 20 rows):
# {rows[:20]}

# Rules:
# - Decide what is relevant for this specific question; do not follow a fixed report template.
# - Base every factual statement only on the result rows provided above.
# - Do not guess, infer, or invent causes, trends, events, or numbers.
# - Never invent causes, trends, numbers, recommendations, or context.
# - Use exact values and comparisons when supported by the rows.
# - If the data cannot answer part of the question, say what is missing.
# - Write in plain, simple business English, as if explaining to a non-technical manager. No jargon or technical terms.
# - Be thorough, not brief: explain what the numbers mean, compare categories against each other, call out anything notable (highs, lows, gaps, missing data), and give the full picture in multiple sentences or paragraphs rather than one-line summaries.
# - Never use Markdown tables. Present numbers and comparisons as plain sentences or bullet points instead.
# - Return only the user-facing answer with no fixed section labels.
# """


# def generate_insights(question: str, rows: list[dict], data_sources: list[dict] | None = None) -> dict:
#     """Generate dynamic report sections with transparent rationale."""
#     if not rows:
#         return {
#             "overview": "No data matched this question.",
#             "key_findings": ["Insufficient evidence: no result rows were returned. Rationale: there are no observations to analyze."],
#             "recommendations": ["Review the filters or date range. Rationale: broader criteria may return analyzable data."],
#             "next_steps": ["Check which filter or date range should be broadened. Rationale: the current query returned no rows."],
#             "data_sources": ["Insufficient evidence: source contribution cannot be confirmed from an empty result. Rationale: provide a successful result or schema context."],
#         }

#     prompt = build_insights_prompt(question, rows)
#     try:
#         response = client.models.generate_content(
#             model="gemini-3.1-flash-lite",
#             contents=prompt,
#             config={
#                 "temperature": 0,
#                 "http_options": {"timeout": 20000},
#             },
#         )
#     except Exception as e:
#         raise RuntimeError(f"Insight generation failed: {e}")

#     text_out = response.text.strip()

#     sections = {
#         "text": text_out,
#         "overview": "",
#         "key_findings": [],
#         "recommendations": [],
#         "next_steps": [],
#         "data_sources": [],
#     }
#     current_key = None

#     for line in text_out.splitlines():
#         line = line.strip()
#         if not line:
#             continue
#         if line.startswith("OVERVIEW:"):
#             sections["overview"] = line.replace("OVERVIEW:", "").strip()
#             current_key = None
#         elif line.startswith("KEY FINDINGS:"):
#             current_key = "key_findings"
#         elif line.startswith("RECOMMENDATIONS:"):
#             current_key = "recommendations"
#         elif line.startswith("NEXT STEPS:"):
#             current_key = "next_steps"
#         elif line.startswith("DATA SOURCES:"):
#             current_key = "data_sources"
#         elif line.startswith("-") and current_key:
#             sections[current_key].append(line.lstrip("-").strip())

#     return sections


# FORBIDDEN_SQL_NODE_NAMES = {
#     "alter",
#     "attach",
#     "command",
#     "commit",
#     "copy",
#     "create",
#     "delete",
#     "detach",
#     "drop",
#     "grant",
#     "insert",
#     "merge",
#     "revoke",
#     "rollback",
#     "transaction",
#     "truncate",
#     "truncatetable",
#     "update",
#     "use",
#     "vacuum",
# }


# def validate_sql(sql: str, valid_identifiers: set[str]) -> tuple[bool, str]:
#     """
#     Allow one read-only PostgreSQL query that references only known tables.

#     SQLGlot parses the query into an AST before it is checked, so SQL keywords
#     inside text values cannot bypass validation.
#     """
#     cleaned_sql = sql.strip()

#     if not cleaned_sql:
#         return False, "The generated query was empty."

#     if cleaned_sql.endswith(";"):
#         cleaned_sql = cleaned_sql[:-1].strip()

#     try:
#         statements = parse(cleaned_sql, read="postgres")
#     except ParseError:
#         return False, "The generated query is not valid SQL."

#     if len(statements) != 1:
#         return False, "Only one SQL statement is allowed."

#     expression = statements[0]

#     allowed_root_types = (
#         exp.Select,
#         exp.Union,
#         exp.Intersect,
#         exp.Except,
#     )

#     if not isinstance(expression, allowed_root_types):
#         return False, "Only read-only SELECT queries are allowed."

#     for node in expression.walk():
#         node_name = type(node).__name__.lower()

#         if node_name in FORBIDDEN_SQL_NODE_NAMES:
#             return False, "Only read-only SELECT queries are allowed."

#     known_identifiers = {
#         identifier.lower()
#         for identifier in valid_identifiers
#     }

#     cte_names = {
#         cte.alias_or_name.lower()
#         for cte in expression.find_all(exp.CTE)
#         if cte.alias_or_name
#     }

#     referenced_tables = {
#         table.name.lower()
#         for table in expression.find_all(exp.Table)
#         if table.name
#     }

#     unknown_tables = (
#         referenced_tables
#         - known_identifiers
#         - cte_names
#     )

#     if unknown_tables:
#         return (
#             False,
#             "Query references an unknown table: "
#             + ", ".join(sorted(unknown_tables)),
#         )

#     if expression.args.get("limit") is None:
#         expression = expression.limit(100)

#     return True, expression.sql(dialect="postgres")


# def extract_data_sources(sql: str) -> list[dict]:
#     """
#     Parse the validated SQL to report which tables and columns the answer
#     actually used, for a "Data sources" citation in the UI.
#     """
#     try:
#         statements = parse(sql, read="postgres")
#     except ParseError:
#         return []

#     if not statements:
#         return []

#     expression = statements[0]

#     alias_to_table = {
#         table.alias_or_name: table.name
#         for table in expression.find_all(exp.Table)
#         if table.name
#     }

#     sources: dict[str, set[str]] = {}

#     for column in expression.find_all(exp.Column):
#         column_name = column.name
#         if not column_name:
#             continue

#         table_ref = column.table
#         if table_ref:
#             table_name = alias_to_table.get(table_ref, table_ref)
#         elif len(alias_to_table) == 1:
#             table_name = next(iter(alias_to_table.values()))
#         else:
#             continue

#         sources.setdefault(table_name, set()).add(column_name)

#     return [
#         {"table": table, "columns": sorted(columns)}
#         for table, columns in sources.items()
#     ]


















































# """Wraps Gemini calls for SQL generation."""

# import re

# from google import genai
# from app.config.settings import settings
# from sqlglot import exp, parse
# from sqlglot.errors import ParseError

# client = genai.Client(api_key=settings.gemini_api_key)

# SQL_SYSTEM_INSTRUCTION = """You generate PostgreSQL queries from natural-language questions.

# The user does not know the database's table or column names. Business terms in their
# question (e.g. "revenue", "sales", "product") almost always map to a real column or a
# computation over real columns — your job is to find that mapping, not to reject the question.

# Rules:
# - Use ONLY the tables and columns given in the schema below. Never invent a table or column name.
# - If the question uses a business term with no exact matching column (e.g. "revenue" when the
#   column is "sales_amount"), map it to the closest real column or compute it with an aggregate
#   (e.g. SUM(sales_amount)). Do this silently — do not ask the user to clarify.
# - If the question refers to an entity loosely (e.g. "product 12" when the real identifier is
#   product_id or product_code), match it to the appropriate key column and filter on it.
# - Only generate SELECT or WITH queries. Never INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, or CREATE.
# - Use explicit JOIN conditions based on the foreign keys shown.
# - Add a reasonable LIMIT unless the question clearly needs all rows (e.g. an aggregate).
# - Use deterministic ORDER BY when ranking or returning top-N results.
# - Return ONLY the raw SQL query. No markdown fences, no explanation, no commentary.
# """


# def generate_sql(question: str, schema_text: str, history: list[dict] = None) -> str:
#     history_text = ""
#     if history:
#         recent = history[-3:]
#         history_text = "\n".join(
#             f"Q: {h['question']}\nSQL: {h['sql']}" for h in recent
#         )
#         history_text = f"\nPrevious questions in this conversation:\n{history_text}\n"

#     prompt = f"Schema:\n{schema_text}\n{history_text}\nQuestion: {question}\n\nSQL:"

#     try:
#         response = client.models.generate_content(
#             model="gemini-3.1-flash-lite",
#             contents=prompt,
#             config={
#                 "system_instruction": SQL_SYSTEM_INSTRUCTION,
#                 "temperature": 0,
#                 "http_options": {"timeout": 20000},  # 20 seconds, in ms
#             },
#         )
#     except Exception as e:
#         raise RuntimeError(f"SQL generation failed: {e}")

#     sql = response.text.strip()
#     if sql.startswith("```"):
#         sql = sql.strip("`").removeprefix("sql").strip()
#     return sql


# def build_insights_prompt(question: str, rows: list[dict], data_sources: list[dict] | None = None) -> str:
#     """Build a dynamic, data-grounded prompt for the answer AI."""
#     return f"""
# Question: {question}

# Result rows (use only these values; at most the first 20 rows):
# {rows[:20]}

# Rules:
# - Decide what is relevant for this specific question; do not follow a fixed report template.
# - Base every factual statement only on the result rows provided above.
# - Do not guess, infer, or invent causes, trends, events, or numbers.
# - Never invent causes, trends, numbers, recommendations, or context.
# - Use exact values and comparisons when supported by the rows.
# - If the data cannot answer part of the question, say what is missing.
# - Write in plain, simple business English, as if explaining to a non-technical manager. No jargon or technical terms.
# - Be thorough, not brief: explain what the numbers mean, compare categories against each other, call out anything notable (highs, lows, gaps, missing data), and give the full picture in multiple sentences or paragraphs rather than one-line summaries.
# - Never use Markdown tables. Present numbers and comparisons as plain sentences or bullet points instead.
# - Return only the user-facing answer with no fixed section labels.
# """


# def generate_insights(question: str, rows: list[dict], data_sources: list[dict] | None = None) -> dict:
#     """Generate dynamic report sections with transparent rationale."""
#     if not rows:
#         return {
#             "overview": "No data matched this question.",
#             "key_findings": ["Insufficient evidence: no result rows were returned. Rationale: there are no observations to analyze."],
#             "recommendations": ["Review the filters or date range. Rationale: broader criteria may return analyzable data."],
#             "next_steps": ["Check which filter or date range should be broadened. Rationale: the current query returned no rows."],
#             "data_sources": ["Insufficient evidence: source contribution cannot be confirmed from an empty result. Rationale: provide a successful result or schema context."],
#         }

#     prompt = build_insights_prompt(question, rows)
#     try:
#         response = client.models.generate_content(
#             model="gemini-3.1-flash-lite",
#             contents=prompt,
#             config={
#                 "temperature": 0,
#                 "http_options": {"timeout": 20000},
#             },
#         )
#     except Exception as e:
#         raise RuntimeError(f"Insight generation failed: {e}")

#     text_out = response.text.strip()

#     sections = {
#         "text": text_out,
#         "overview": "",
#         "key_findings": [],
#         "recommendations": [],
#         "next_steps": [],
#         "data_sources": [],
#     }
#     current_key = None

#     for line in text_out.splitlines():
#         line = line.strip()
#         if not line:
#             continue
#         if line.startswith("OVERVIEW:"):
#             sections["overview"] = line.replace("OVERVIEW:", "").strip()
#             current_key = None
#         elif line.startswith("KEY FINDINGS:"):
#             current_key = "key_findings"
#         elif line.startswith("RECOMMENDATIONS:"):
#             current_key = "recommendations"
#         elif line.startswith("NEXT STEPS:"):
#             current_key = "next_steps"
#         elif line.startswith("DATA SOURCES:"):
#             current_key = "data_sources"
#         elif line.startswith("-") and current_key:
#             sections[current_key].append(line.lstrip("-").strip())

#     return sections


# FORBIDDEN_SQL_NODE_NAMES = {
#     "alter",
#     "attach",
#     "command",
#     "commit",
#     "copy",
#     "create",
#     "delete",
#     "detach",
#     "drop",
#     "grant",
#     "insert",
#     "merge",
#     "revoke",
#     "rollback",
#     "transaction",
#     "truncate",
#     "truncatetable",
#     "update",
#     "use",
#     "vacuum",
# }


# def validate_sql(sql: str, valid_identifiers: set[str]) -> tuple[bool, str]:
#     """
#     Allow one read-only PostgreSQL query that references only known tables.

#     SQLGlot parses the query into an AST before it is checked, so SQL keywords
#     inside text values cannot bypass validation.
#     """
#     cleaned_sql = sql.strip()

#     if not cleaned_sql:
#         return False, "The generated query was empty."

#     if cleaned_sql.endswith(";"):
#         cleaned_sql = cleaned_sql[:-1].strip()

#     try:
#         statements = parse(cleaned_sql, read="postgres")
#     except ParseError:
#         return False, "The generated query is not valid SQL."

#     if len(statements) != 1:
#         return False, "Only one SQL statement is allowed."

#     expression = statements[0]

#     allowed_root_types = (
#         exp.Select,
#         exp.Union,
#         exp.Intersect,
#         exp.Except,
#     )

#     if not isinstance(expression, allowed_root_types):
#         return False, "Only read-only SELECT queries are allowed."

#     for node in expression.walk():
#         node_name = type(node).__name__.lower()

#         if node_name in FORBIDDEN_SQL_NODE_NAMES:
#             return False, "Only read-only SELECT queries are allowed."

#     known_identifiers = {
#         identifier.lower()
#         for identifier in valid_identifiers
#     }

#     cte_names = {
#         cte.alias_or_name.lower()
#         for cte in expression.find_all(exp.CTE)
#         if cte.alias_or_name
#     }

#     referenced_tables = {
#         table.name.lower()
#         for table in expression.find_all(exp.Table)
#         if table.name
#     }

#     unknown_tables = (
#         referenced_tables
#         - known_identifiers
#         - cte_names
#     )

#     if unknown_tables:
#         return (
#             False,
#             "Query references an unknown table: "
#             + ", ".join(sorted(unknown_tables)),
#         )

#     if expression.args.get("limit") is None:
#         expression = expression.limit(100)

#     return True, expression.sql(dialect="postgres")


# def extract_data_sources(sql: str) -> list[dict]:
#     """
#     Parse the validated SQL to report which tables and columns the answer
#     actually used, for a "Data sources" citation in the UI.
#     """
#     try:
#         statements = parse(sql, read="postgres")
#     except ParseError:
#         return []

#     if not statements:
#         return []

#     expression = statements[0]

#     alias_to_table = {
#         table.alias_or_name: table.name
#         for table in expression.find_all(exp.Table)
#         if table.name
#     }

#     sources: dict[str, set[str]] = {}

#     for column in expression.find_all(exp.Column):
#         column_name = column.name
#         if not column_name:
#             continue

#         table_ref = column.table
#         if table_ref:
#             table_name = alias_to_table.get(table_ref, table_ref)
#         elif len(alias_to_table) == 1:
#             table_name = next(iter(alias_to_table.values()))
#         else:
#             continue

#         sources.setdefault(table_name, set()).add(column_name)

#     return [
#         {"table": table, "columns": sorted(columns)}
#         for table, columns in sources.items()
#     ]

















































# """Wraps Gemini calls for SQL generation."""

# import re

# from google import genai
# from app.config.settings import settings
# from sqlglot import exp, parse
# from sqlglot.errors import ParseError

# client = genai.Client(api_key=settings.gemini_api_key)

# SQL_SYSTEM_INSTRUCTION = """You generate PostgreSQL queries from natural-language questions.

# The user does not know the database's table or column names. Business terms in their
# question (e.g. "revenue", "sales", "product") almost always map to a real column or a
# computation over real columns — your job is to find that mapping, not to reject the question.

# Rules:
# - Use ONLY the tables and columns given in the schema below. Never invent a table or column name.
# - If the question uses a business term with no exact matching column (e.g. "revenue" when the
#   column is "sales_amount"), map it to the closest real column or compute it with an aggregate
#   (e.g. SUM(sales_amount)). Do this silently — do not ask the user to clarify.
# - If the question refers to an entity loosely (e.g. "product 12" when the real identifier is
#   product_id or product_code), match it to the appropriate key column and filter on it.
# - Only generate SELECT or WITH queries. Never INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, or CREATE.
# - Use explicit JOIN conditions based on the foreign keys shown.
# - Add a reasonable LIMIT unless the question clearly needs all rows (e.g. an aggregate).
# - Use deterministic ORDER BY when ranking or returning top-N results.
# - Return ONLY the raw SQL query. No markdown fences, no explanation, no commentary.
# """


# def generate_sql(question: str, schema_text: str, history: list[dict] = None) -> str:
#     history_text = ""
#     if history:
#         recent = history[-3:]
#         history_text = "\n".join(
#             f"Q: {h['question']}\nSQL: {h['sql']}" for h in recent
#         )
#         history_text = f"\nPrevious questions in this conversation:\n{history_text}\n"

#     prompt = f"Schema:\n{schema_text}\n{history_text}\nQuestion: {question}\n\nSQL:"

#     try:
#         response = client.models.generate_content(
#             model="gemini-3.1-flash-lite",
#             contents=prompt,
#             config={
#                 "system_instruction": SQL_SYSTEM_INSTRUCTION,
#                 "temperature": 0,
#                 "http_options": {"timeout": 20000},  # 20 seconds, in ms
#             },
#         )
#     except Exception as e:
#         raise RuntimeError(f"SQL generation failed: {e}")

#     sql = response.text.strip()
#     if sql.startswith("```"):
#         sql = sql.strip("`").removeprefix("sql").strip()
#     return sql


# def build_insights_prompt(question: str, rows: list[dict], data_sources: list[dict] | None = None) -> str:
#     """Build a dynamic, data-grounded prompt for the answer AI."""
#     return f"""
# Question: {question}

# Result rows (use only these values; at most the first 20 rows):
# {rows[:20]}

# Rules:
# - Decide what is relevant for this specific question; do not follow a fixed report template.
# - Base every factual statement only on the result rows provided above.
# - Do not guess, infer, or invent causes, trends, events, or numbers.
# - Never invent causes, trends, numbers, recommendations, or context.
# - Use exact values and comparisons when supported by the rows.
# - If the data cannot answer part of the question, say what is missing.
# - Write in plain, simple business English, as if explaining to a non-technical manager. No jargon or technical terms.
# - Be thorough, not brief: explain what the numbers mean, compare categories against each other, call out anything notable (highs, lows, gaps, missing data), and give the full picture in multiple sentences or paragraphs rather than one-line summaries.
# - Never use Markdown tables. Present numbers and comparisons as plain sentences or bullet points instead.
# - Return only the user-facing answer with no fixed section labels.
# """


# def generate_insights(question: str, rows: list[dict], data_sources: list[dict] | None = None) -> dict:
#     """Generate dynamic report sections with transparent rationale."""
#     if not rows:
#         return {
#             "overview": "No data matched this question.",
#             "key_findings": ["Insufficient evidence: no result rows were returned. Rationale: there are no observations to analyze."],
#             "recommendations": ["Review the filters or date range. Rationale: broader criteria may return analyzable data."],
#             "next_steps": ["Check which filter or date range should be broadened. Rationale: the current query returned no rows."],
#             "data_sources": ["Insufficient evidence: source contribution cannot be confirmed from an empty result. Rationale: provide a successful result or schema context."],
#         }

#     prompt = build_insights_prompt(question, rows)
#     try:
#         response = client.models.generate_content(
#             model="gemini-3.1-flash-lite",
#             contents=prompt,
#             config={
#                 "temperature": 0,
#                 "http_options": {"timeout": 20000},
#             },
#         )
#     except Exception as e:
#         raise RuntimeError(f"Insight generation failed: {e}")

#     text_out = response.text.strip()

#     sections = {
#         "text": text_out,
#         "overview": "",
#         "key_findings": [],
#         "recommendations": [],
#         "next_steps": [],
#         "data_sources": [],
#     }
#     current_key = None

#     for line in text_out.splitlines():
#         line = line.strip()
#         if not line:
#             continue
#         if line.startswith("OVERVIEW:"):
#             sections["overview"] = line.replace("OVERVIEW:", "").strip()
#             current_key = None
#         elif line.startswith("KEY FINDINGS:"):
#             current_key = "key_findings"
#         elif line.startswith("RECOMMENDATIONS:"):
#             current_key = "recommendations"
#         elif line.startswith("NEXT STEPS:"):
#             current_key = "next_steps"
#         elif line.startswith("DATA SOURCES:"):
#             current_key = "data_sources"
#         elif line.startswith("-") and current_key:
#             sections[current_key].append(line.lstrip("-").strip())

#     return sections


# FORBIDDEN_SQL_NODE_NAMES = {
#     "alter",
#     "attach",
#     "command",
#     "commit",
#     "copy",
#     "create",
#     "delete",
#     "detach",
#     "drop",
#     "grant",
#     "insert",
#     "merge",
#     "revoke",
#     "rollback",
#     "transaction",
#     "truncate",
#     "truncatetable",
#     "update",
#     "use",
#     "vacuum",
# }


# def validate_sql(sql: str, valid_identifiers: set[str]) -> tuple[bool, str]:
#     """
#     Allow one read-only PostgreSQL query that references only known tables.

#     SQLGlot parses the query into an AST before it is checked, so SQL keywords
#     inside text values cannot bypass validation.
#     """
#     cleaned_sql = sql.strip()

#     if not cleaned_sql:
#         return False, "The generated query was empty."

#     if cleaned_sql.endswith(";"):
#         cleaned_sql = cleaned_sql[:-1].strip()

#     try:
#         statements = parse(cleaned_sql, read="postgres")
#     except ParseError:
#         return False, "The generated query is not valid SQL."

#     if len(statements) != 1:
#         return False, "Only one SQL statement is allowed."

#     expression = statements[0]

#     allowed_root_types = (
#         exp.Select,
#         exp.Union,
#         exp.Intersect,
#         exp.Except,
#     )

#     if not isinstance(expression, allowed_root_types):
#         return False, "Only read-only SELECT queries are allowed."

#     for node in expression.walk():
#         node_name = type(node).__name__.lower()

#         if node_name in FORBIDDEN_SQL_NODE_NAMES:
#             return False, "Only read-only SELECT queries are allowed."

#     known_identifiers = {
#         identifier.lower()
#         for identifier in valid_identifiers
#     }

#     cte_names = {
#         cte.alias_or_name.lower()
#         for cte in expression.find_all(exp.CTE)
#         if cte.alias_or_name
#     }

#     referenced_tables = {
#         table.name.lower()
#         for table in expression.find_all(exp.Table)
#         if table.name
#     }

#     unknown_tables = (
#         referenced_tables
#         - known_identifiers
#         - cte_names
#     )

#     if unknown_tables:
#         return (
#             False,
#             "Query references an unknown table: "
#             + ", ".join(sorted(unknown_tables)),
#         )

#     if expression.args.get("limit") is None:
#         expression = expression.limit(100)

#     return True, expression.sql(dialect="postgres")


# def extract_data_sources(sql: str) -> list[dict]:
#     """
#     Parse the validated SQL to report which tables and columns the answer
#     actually used, for a "Data sources" citation in the UI.
#     """
#     try:
#         statements = parse(sql, read="postgres")
#     except ParseError:
#         return []

#     if not statements:
#         return []

#     expression = statements[0]

#     alias_to_table = {
#         table.alias_or_name: table.name
#         for table in expression.find_all(exp.Table)
#         if table.name
#     }

#     sources: dict[str, set[str]] = {}

#     for column in expression.find_all(exp.Column):
#         column_name = column.name
#         if not column_name:
#             continue

#         table_ref = column.table
#         if table_ref:
#             table_name = alias_to_table.get(table_ref, table_ref)
#         elif len(alias_to_table) == 1:
#             table_name = next(iter(alias_to_table.values()))
#         else:
#             continue

#         sources.setdefault(table_name, set()).add(column_name)

#     return [
#         {"table": table, "columns": sorted(columns)}
#         for table, columns in sources.items()
#     ]


















































"""Wraps Gemini calls for SQL generation."""

import re

from google import genai
from app.config.settings import settings
from sqlglot import exp, parse
from sqlglot.errors import ParseError

client = genai.Client(api_key=settings.gemini_api_key)

SQL_SYSTEM_INSTRUCTION = """You generate PostgreSQL queries from natural-language questions.

The user does not know the database's table or column names. Business terms in their
question (e.g. "revenue", "sales", "product") almost always map to a real column or a
computation over real columns — your job is to find that mapping, not to reject the question.

Rules:
- Use ONLY the tables and columns given in the schema below. Never invent a table or column name.
- If the question uses a business term with no exact matching column (e.g. "revenue" when the
  column is "sales_amount"), map it to the closest real column or compute it with an aggregate
  (e.g. SUM(sales_amount)). Do this silently — do not ask the user to clarify.
- If the question refers to an entity loosely (e.g. "product 12" when the real identifier is
  product_id or product_code), match it to the appropriate key column and filter on it.
- If the question references a specific month (e.g. "March") without a year, do NOT fall back
  to a full-year or whole-table aggregate. Instead, resolve it to the most recent year in the
  data that has rows for that month — e.g. filter to
  EXTRACT(MONTH FROM date_col) = 3 AND EXTRACT(YEAR FROM date_col) = (the most recent year that
  has rows for month 3, found via a subquery or CTE against the same date column). The query
  must still return data at the granularity the question needs (e.g. a monthly or daily figure
  for that specific month), never just an annual total.
- Only generate SELECT or WITH queries. Never INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, or CREATE.
- Use explicit JOIN conditions based on the foreign keys shown.
- Add a reasonable LIMIT unless the question clearly needs all rows (e.g. an aggregate).
- Use deterministic ORDER BY when ranking or returning top-N results.
- Return ONLY the raw SQL query. No markdown fences, no explanation, no commentary.
"""


def generate_sql(question: str, schema_text: str, history: list[dict] = None) -> str:
    history_text = ""
    if history:
        recent = [
            h for h in history[-3:]
            if isinstance(h, dict) and h.get("question") and h.get("sql")
        ]
        if recent:
            history_text = "\n".join(
                f"Q: {h['question']}\nSQL: {h['sql']}" for h in recent
            )
            history_text = f"\nPrevious questions in this conversation:\n{history_text}\n"

    prompt = f"Schema:\n{schema_text}\n{history_text}\nQuestion: {question}\n\nSQL:"

    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt,
            config={
                "system_instruction": SQL_SYSTEM_INSTRUCTION,
                "temperature": 0,
                "http_options": {"timeout": 20000},  # 20 seconds, in ms
            },
        )
    except Exception as e:
        raise RuntimeError(f"SQL generation failed: {e}")

    sql = response.text.strip()
    if sql.startswith("```"):
        sql = sql.strip("`").removeprefix("sql").strip()
    return sql


DIAGNOSTIC_KEYWORDS = {
    "why",
    "dropped",
    "drop",
    "drops",
    "declined",
    "decline",
    "declines",
    "decrease",
    "decreased",
    "fell",
    "fall",
    "falling",
    "down",
    "worse",
    "underperform",
    "underperformed",
    "underperforming",
    "cause",
    "caused",
    "causing",
    "reason",
    "reasons",
    "wrong",
    "slump",
    "slumped",
    "lower",
    "lagging",
    "lag",
    "shrink",
    "shrunk",
    "shrinking",
}


def is_diagnostic_question(question: str) -> bool:
    """
    Detect questions that ask *why* a metric moved (e.g. "why did sales drop
    in March"), as opposed to questions that just ask for a number or a
    ranking. Diagnostic questions need a segment-level breakdown query in
    addition to the primary aggregate query to be answerable with grounded,
    non-invented detail.
    """
    words = set(re.findall(r"[a-zA-Z]+", question.lower()))
    return bool(words & DIAGNOSTIC_KEYWORDS)


DIAGNOSTIC_SQL_SYSTEM_INSTRUCTION = """You generate a PostgreSQL diagnostic breakdown query.

The user asked a question about WHY a metric changed (e.g. "why did sales drop in March").
A separate query has already computed the overall aggregate for the period in question; your
job is to write ONE query that explains WHERE the change is concentrated, not why it happened.

Your query must:
- Break the relevant metric down by exactly one categorical dimension available in the schema
  that best fits the question (e.g. category, region, segment, product) — pick only one.
- Use the exact "current period" that the primary query below resolved the question to (same
  year and month/quarter it filtered on). Do not re-resolve the period independently — read it
  from the primary query's WHERE/date filter so both queries agree on what "the period" means.
  If the question references a month without a year and no primary query is given, resolve it
  the same way the primary query would: use the most recent year in the data with rows for
  that month, never a full-year or whole-table aggregate.
- Compare that current period against the immediately preceding period of the same length
  (e.g. previous calendar month if the question is about a month, previous quarter if the
  question is about a quarter), using the same aggregate as the metric implied by the question.
- Return, per dimension value: the dimension name, the current-period metric, the
  previous-period metric, and the absolute and/or percent change between them.
- Order rows by the size of the decline (most negative change first) so the biggest movers are
  at the top.
- Use ONLY the tables and columns given in the schema below. Never invent a table or column name.
- Only generate a SELECT or WITH query. Never INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, or CREATE.
- Use explicit JOIN conditions based on the foreign keys shown.
- Add a reasonable LIMIT (e.g. 20) since this is a per-segment breakdown, not a single total.
- Return ONLY the raw SQL query. No markdown fences, no explanation, no commentary.
"""


def generate_diagnostic_sql(question: str, schema_text: str, primary_sql: str | None = None) -> str:
    """
    Generate a second query that breaks the metric implied by a diagnostic
    question (e.g. "why did sales drop") down by the most relevant dimension
    and compares it against the prior comparable period. This gives the
    insights step real, grounded detail to point to instead of only the
    single aggregate number the primary query returns.
    """
    primary_sql_block = ""
    if primary_sql:
        primary_sql_block = f"\nThe primary query already run for this question was:\n{primary_sql}\n"

    prompt = f"Schema:\n{schema_text}\n{primary_sql_block}\nQuestion: {question}\n\nSQL:"

    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt,
            config={
                "system_instruction": DIAGNOSTIC_SQL_SYSTEM_INSTRUCTION,
                "temperature": 0,
                "http_options": {"timeout": 20000},  # 20 seconds, in ms
            },
        )
    except Exception as e:
        raise RuntimeError(f"Diagnostic breakdown SQL generation failed: {e}")

    sql = response.text.strip()
    if sql.startswith("```"):
        sql = sql.strip("`").removeprefix("sql").strip()
    return sql


def build_insights_prompt(
    question: str,
    rows: list[dict],
    data_sources: list[dict] | None = None,
    breakdown_rows: list[dict] | None = None,
) -> str:
    """Build a dynamic, data-grounded prompt for the answer AI."""
    breakdown_block = ""
    if breakdown_rows:
        breakdown_block = f"""
Breakdown data (segment-level comparison against the prior comparable period,
use only these values; at most the first 20 rows):
{breakdown_rows[:20]}

When breakdown data is present, use it to point to the specific segment(s)
(category, region, product, etc.) where the change is concentrated, instead of
only reporting the overall aggregate. Still do not guess at *why* a segment
changed beyond what the numbers themselves show — describe the pattern in the
data (e.g. which segment dropped the most and by how much) rather than
inventing an external cause (e.g. a promotion, a competitor, the weather).
"""

    return f"""
Question: {question}

Result rows (use only these values; at most the first 20 rows):
{rows[:20]}
{breakdown_block}
Rules:
- Decide what is relevant for this specific question; do not follow a fixed report template.
- Base every factual statement only on the result rows (and breakdown data, if provided) above.
- Do not guess, infer, or invent causes, trends, events, or numbers.
- Never invent causes, trends, numbers, recommendations, or context.
- Use exact values and comparisons when supported by the rows.
- If the data cannot answer part of the question, say what is missing.
- Write in plain, simple business English, as if explaining to a non-technical manager. No jargon or technical terms.
- Be thorough, not brief: explain what the numbers mean, compare categories against each other, call out anything notable (highs, lows, gaps, missing data), and give the full picture in multiple sentences or paragraphs rather than one-line summaries.
- Never use Markdown tables. Present numbers and comparisons as plain sentences or bullet points instead.
- Return only the user-facing answer with no fixed section labels.
"""


def generate_insights(
    question: str,
    rows: list[dict],
    data_sources: list[dict] | None = None,
    breakdown_rows: list[dict] | None = None,
) -> dict:
    """Generate dynamic report sections with transparent rationale."""
    if not rows:
        return {
            "overview": "No data matched this question.",
            "key_findings": ["Insufficient evidence: no result rows were returned. Rationale: there are no observations to analyze."],
            "recommendations": ["Review the filters or date range. Rationale: broader criteria may return analyzable data."],
            "next_steps": ["Check which filter or date range should be broadened. Rationale: the current query returned no rows."],
            "data_sources": ["Insufficient evidence: source contribution cannot be confirmed from an empty result. Rationale: provide a successful result or schema context."],
        }

    prompt = build_insights_prompt(question, rows, data_sources=data_sources, breakdown_rows=breakdown_rows)
    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt,
            config={
                "temperature": 0,
                "http_options": {"timeout": 20000},
            },
        )
    except Exception as e:
        raise RuntimeError(f"Insight generation failed: {e}")

    text_out = response.text.strip()

    sections = {
        "text": text_out,
        "overview": "",
        "key_findings": [],
        "recommendations": [],
        "next_steps": [],
        "data_sources": [],
    }
    current_key = None

    for line in text_out.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("OVERVIEW:"):
            sections["overview"] = line.replace("OVERVIEW:", "").strip()
            current_key = None
        elif line.startswith("KEY FINDINGS:"):
            current_key = "key_findings"
        elif line.startswith("RECOMMENDATIONS:"):
            current_key = "recommendations"
        elif line.startswith("NEXT STEPS:"):
            current_key = "next_steps"
        elif line.startswith("DATA SOURCES:"):
            current_key = "data_sources"
        elif line.startswith("-") and current_key:
            sections[current_key].append(line.lstrip("-").strip())

    return sections


FORBIDDEN_SQL_NODE_NAMES = {
    "alter",
    "attach",
    "command",
    "commit",
    "copy",
    "create",
    "delete",
    "detach",
    "drop",
    "grant",
    "insert",
    "merge",
    "revoke",
    "rollback",
    "transaction",
    "truncate",
    "truncatetable",
    "update",
    "use",
    "vacuum",
}


def validate_sql(sql: str, valid_identifiers: set[str]) -> tuple[bool, str]:
    """
    Allow one read-only PostgreSQL query that references only known tables.

    SQLGlot parses the query into an AST before it is checked, so SQL keywords
    inside text values cannot bypass validation.
    """
    cleaned_sql = sql.strip()

    if not cleaned_sql:
        return False, "The generated query was empty."

    if cleaned_sql.endswith(";"):
        cleaned_sql = cleaned_sql[:-1].strip()

    try:
        statements = parse(cleaned_sql, read="postgres")
    except ParseError:
        return False, "The generated query is not valid SQL."

    if len(statements) != 1:
        return False, "Only one SQL statement is allowed."

    expression = statements[0]

    allowed_root_types = (
        exp.Select,
        exp.Union,
        exp.Intersect,
        exp.Except,
    )

    if not isinstance(expression, allowed_root_types):
        return False, "Only read-only SELECT queries are allowed."

    for node in expression.walk():
        node_name = type(node).__name__.lower()

        if node_name in FORBIDDEN_SQL_NODE_NAMES:
            return False, "Only read-only SELECT queries are allowed."

    known_identifiers = {
        identifier.lower()
        for identifier in valid_identifiers
    }

    cte_names = {
        cte.alias_or_name.lower()
        for cte in expression.find_all(exp.CTE)
        if cte.alias_or_name
    }

    referenced_tables = {
        table.name.lower()
        for table in expression.find_all(exp.Table)
        if table.name
    }

    unknown_tables = (
        referenced_tables
        - known_identifiers
        - cte_names
    )

    if unknown_tables:
        return (
            False,
            "Query references an unknown table: "
            + ", ".join(sorted(unknown_tables)),
        )

    if expression.args.get("limit") is None:
        expression = expression.limit(100)

    return True, expression.sql(dialect="postgres")


def extract_data_sources(sql: str) -> list[dict]:
    """
    Parse the validated SQL to report which tables and columns the answer
    actually used, for a "Data sources" citation in the UI.
    """
    try:
        statements = parse(sql, read="postgres")
    except ParseError:
        return []

    if not statements:
        return []

    expression = statements[0]

    alias_to_table = {
        table.alias_or_name: table.name
        for table in expression.find_all(exp.Table)
        if table.name
    }

    sources: dict[str, set[str]] = {}

    for column in expression.find_all(exp.Column):
        column_name = column.name
        if not column_name:
            continue

        table_ref = column.table
        if table_ref:
            table_name = alias_to_table.get(table_ref, table_ref)
        elif len(alias_to_table) == 1:
            table_name = next(iter(alias_to_table.values()))
        else:
            continue

        sources.setdefault(table_name, set()).add(column_name)

    return [
        {"table": table, "columns": sorted(columns)}
        for table, columns in sources.items()
    ]