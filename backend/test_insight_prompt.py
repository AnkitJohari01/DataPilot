from app.services.gemini_service import build_insights_prompt

prompt = build_insights_prompt(
    "Which shipment status has the most delays?",
    [{"shipment_status": "Delayed", "delay_count": 187}],
)

assert "Do not guess" in prompt
assert "data does not show the cause" in prompt
assert "only the result rows" in prompt

print("Insight prompt safety test passed.")