from app.services.gemini_service import validate_sql

valid_identifiers = {
    "fact_sales",
    "net_sales",
}

sql = """
WITH totals AS (
    SELECT SUM(net_sales) AS total_sales
    FROM fact_sales
)
SELECT total_sales
FROM totals
"""

is_valid, result = validate_sql(sql, valid_identifiers)

assert is_valid is True

print("SQL validation test passed.")    