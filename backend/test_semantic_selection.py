from app.services.semantic_retrieval_service import (
    get_semantic_catalog_selection,
)

selection = get_semantic_catalog_selection(
    "What is our total revenue?"
)

assert "schema_text" in selection
assert "candidate_table_names" in selection
assert "best_score" in selection
assert "Table: fact_sales" in selection["schema_text"]

print("Semantic selection test passed.")