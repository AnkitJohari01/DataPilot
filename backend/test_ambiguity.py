from app.services.semantic_retrieval_service import needs_clarification

# The best match is too weak.
assert needs_clarification(0.40, 0.20) is True

# Two possible meanings are almost equally likely.
assert needs_clarification(0.85, 0.82) is True

# One meaning is clearly stronger.
assert needs_clarification(0.85, 0.55) is False

print("Ambiguity test passed.")