from app.database.metadata import get_relevant_catalog_for_llm

context = get_relevant_catalog_for_llm(
    "Show the top 5 products by sales"
)

assert "Table: fact_sales" in context
assert "Table: dim_product" in context

print("Relevant catalog test passed.")