from app.database.metadata import get_catalog_for_llm

catalog_text = get_catalog_for_llm()

assert isinstance(catalog_text, str)
assert len(catalog_text) > 0
assert "Table:" in catalog_text

print("Catalog context test passed.")