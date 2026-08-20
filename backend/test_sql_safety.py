from app.services.gemini_service import validate_sql

valid_identifiers = {
    "fact_sales",
    "net_sales",
}

unsafe_queries = [
    "DELETE FROM fact_sales",
    "DROP TABLE fact_sales",
    "SELECT net_sales FROM fact_sales; DELETE FROM fact_sales",
]

for sql in unsafe_queries:
    is_valid, _ = validate_sql(sql, valid_identifiers)
    assert is_valid is False, f"Unsafe query was allowed: {sql}"

print("SQL safety test passed.")