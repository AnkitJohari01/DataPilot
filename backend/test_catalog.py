from app.database.metadata import get_schema_catalog

catalog = get_schema_catalog()

assert "tables" in catalog
assert len(catalog["tables"]) > 0
assert "columns" in catalog["tables"][0]

print("Catalog test passed.")