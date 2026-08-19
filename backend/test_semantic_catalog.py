from app.services.semantic_retrieval_service import (
    get_semantically_relevant_catalog_for_llm,
)

context = get_semantically_relevant_catalog_for_llm(
    "What is our total revenue?"
)

assert "Table: fact_sales" in context
assert "net_sales" in context

print("Semantic catalog test passed.")