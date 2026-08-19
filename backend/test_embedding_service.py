from app.services.semantic_retrieval_service import create_embedding

embedding = create_embedding("revenue and sales performance")

assert isinstance(embedding, list)
assert len(embedding) > 0
assert all(isinstance(value, float) for value in embedding)

print(f"Embedding test passed. Vector size: {len(embedding)}")  