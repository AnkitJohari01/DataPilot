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
- Only generate SELECT or WITH queries. Never INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, or CREATE.
- Use explicit JOIN conditions based on the foreign keys shown.
- Add a reasonable LIMIT unless the question clearly needs all rows (e.g. an aggregate).
- Use deterministic ORDER BY when ranking or returning top-N results.
- Return ONLY the raw SQL query. No markdown fences, no explanation, no commentary.
"""


def generate_sql(question: str, schema_text: str, history: list[dict] = None) -> str:
    history_text = ""
    if history:
        recent = history[-3:]
        history_text = "\n".join(
            f"Q: {h['question']}\nSQL: {h['sql']}" for h in recent
        )
        history_text = f"\nPrevious questions in this conversation:\n{history_text}\n"

    prompt = f"Schema:\n{schema_text}\n{history_text}\nQuestion: {question}\n\nSQL:"

    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=prompt,
            config={
                "system_instruction": SQL_SYSTEM_INSTRUCTION,
                "temperature": 0,
                "http_options": {"timeout": 10000},  # 10 seconds, in ms
            },
        )
    except Exception as e:
        raise RuntimeError(f"SQL generation failed: {e}")

    sql = response.text.strip()
    if sql.startswith("```"):
        sql = sql.strip("`").removeprefix("sql").strip()
    return sql       


def build_insights_prompt(question: str, rows: list[dict]) -> str:
    """Build a safe, data-grounded prompt for the answer AI."""
    return f"""
Question: {question}

Use only the result rows below:
{rows[:20]}

Rules:
- Base every statement only on the result rows provided above.
- Do not guess, infer, or invent causes, trends, events, or numbers.
- If the result rows do not contain the reason for something, say:
  "The data does not show the cause."
- Do not claim that an operational problem, customer behavior, or business event happened unless it appears in the result rows.
- Recommendations must be safe data checks or follow-up filters, never a business action based on an assumed cause.
- Next steps must be a safe follow-up question or filter to investigate, not an assumed cause.
- Use simple, humanized business English. Short sentences. No jargon, no internal reasoning, no meta-commentary about how you produced the answer.

Return exactly this format:

OVERVIEW: <one or two short factual sentences answering the question, based only on the result rows>
KEY FINDINGS:
- <a specific fact directly shown by the rows>
- <another specific fact, if the rows support one; omit this line if there is only one finding>
RECOMMENDATIONS:
- <a safe data check or filter to confirm the finding, or "The data does not show the cause." if nothing safe can be recommended>
NEXT STEPS:
- <a safe follow-up question to ask next>
"""


def generate_insights(question: str, rows: list[dict]) -> dict:
    """Turns raw query rows into an Overview / Key Findings / Recommendations / Next Steps narrative."""
    if not rows:
        return {
            "overview": "No data matched this question.",
            "key_findings": [],
            "recommendations": [],
            "next_steps": ["Try rephrasing the question or check if the filters are too narrow."],
        }

    prompt = build_insights_prompt(question, rows)
    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=prompt,
            config={
                "temperature": 0,
                "http_options": {"timeout": 10000},
            },
        )
    except Exception as e:
        raise RuntimeError(f"Insight generation failed: {e}")

    text_out = response.text.strip()

    sections = {"overview": "", "key_findings": [], "recommendations": [], "next_steps": []}
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