from app.services.semantic_retrieval_service import has_direct_catalog_match

candidate_tables = [
    {
        "name": "fact_returns",
        "columns": [
            {"name": "return_id"},
            {"name": "product_key"},
        ],
    },
    {
        "name": "dim_product",
        "columns": [
            {"name": "product_name"},
        ],
    },
    {
        "name": "fact_shipments",
        "columns": [
            {"name": "shipment_status"},
        ],
    },
]

assert has_direct_catalog_match(
    "Which products had the most returns?",
    candidate_tables,
) is True

assert has_direct_catalog_match(
    "How is the business doing?",
    candidate_tables,
) is False

print("Direct catalog match test passed.")