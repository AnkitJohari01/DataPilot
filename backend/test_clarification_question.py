from app.services.semantic_retrieval_service import (
    build_clarification_question,
)

question = build_clarification_question(
    ["fact_sales", "fact_returns"]
)

assert "sales" in question.lower()
assert "returns" in question.lower()
assert question.endswith("?")

print("Clarification-question test passed.")