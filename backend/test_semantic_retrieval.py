from app.services.semantic_retrieval_service import rank_by_similarity

question_embedding = [1.0, 0.0, 0.0]

candidates = [
    {
        "name": "net_sales",
        "embedding": [0.95, 0.10, 0.00],
    },
    {
        "name": "shipment_status",
        "embedding": [0.05, 0.90, 0.10],
    },
]

matches = rank_by_similarity(
    question_embedding,
    candidates,
    limit=1,
)

assert matches[0]["name"] == "net_sales"

print("Semantic retrieval test passed.")