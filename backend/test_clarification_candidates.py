from app.services.semantic_retrieval_service import (
    get_clarification_candidates,
)

tables = [
    {
        "name": "fact_sales",
        "relationships": [{"column": ["product_key"]}],
    },
    {
        "name": "dim_date",
        "relationships": [],
    },
    {
        "name": "fact_shipments",
        "relationships": [{"column": ["customer_key"]}],
    },
]

choices = get_clarification_candidates(tables)

assert "fact_sales" in choices
assert "fact_shipments" in choices
assert "dim_date" not in choices

print("Clarification candidates test passed.")