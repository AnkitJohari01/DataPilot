from app.services.gemini_service import build_insights_prompt

prompt = build_insights_prompt(
    "Which shipment status has the most delays?",
    [{"shipment_status": "Delayed", "delay_count": 187}],
)

assert "Do not guess" in prompt
assert "Never invent causes" in prompt
assert "only on the result rows" in prompt
assert "Be concise" in prompt
assert "percentage" in prompt
assert "default USD ($)" in prompt

print("Insight prompt safety test passed.")
