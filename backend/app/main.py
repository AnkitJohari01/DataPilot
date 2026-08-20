from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel

from app.config.settings import settings
from app.database.connection import get_db
from app.database.metadata import (
    get_schema_summary,
    get_compact_schema,
    get_valid_identifiers,
    get_schema_catalog,
    get_catalog_for_llm,
)
from app.services.semantic_retrieval_service import (
    build_clarification_question,
    get_semantic_catalog_selection,
    has_direct_catalog_match,
    needs_clarification,
)
from app.services.gemini_service import (
    extract_data_sources,
    generate_insights,
    generate_sql,
    validate_sql,
)

import logging
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("datapilot")

app = FastAPI(title="DataPilot API")

SCHEMA_KEYWORDS = {"table", "tables", "column", "columns", "schema", "field", "fields"}


def is_schema_question(question: str) -> bool:
    words = set(re.findall(r"[a-zA-Z]+", question.lower()))
    return bool(words & SCHEMA_KEYWORDS)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/health/db")
def health_db(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}


@app.get("/api/schema")
def get_schema():
    return get_schema_summary()


@app.get("/api/schema/compact")
def get_schema_compact():
    return {"schema_text": get_compact_schema()}


@app.get("/api/catalog")
def get_catalog():
    return get_schema_catalog()


class AskRequest(BaseModel):
    question: str
    history: list[dict] = []


@app.post("/api/ask")
def ask(request: AskRequest, db: Session = Depends(get_db)):
    if is_schema_question(request.question):
        schema_text = get_catalog_for_llm()

        return {
            "question": request.question,
            "sql": None,
            "rows": [],
            "insights": {
                            "overview": f"Here's the structure of the connected database:\n\n{schema_text}",
                            "key_findings": [],
                            "recommendations": [],
                            "next_steps": ["Ask a business question about this data — e.g. 'What are total sales by category?'"],
                        },        
            }

    selection = get_semantic_catalog_selection(request.question)

    direct_catalog_match = has_direct_catalog_match(
        request.question,
        selection["candidate_tables"],
    )

    if (
        needs_clarification(
            selection["best_score"],
            selection["second_best_score"],
        )
        and not direct_catalog_match
    ):
        clarification_question = build_clarification_question(
            selection["candidate_table_names"]
        )

        return {
            "question": request.question,
            "sql": None,
            "rows": [],
            "clarification_required": True,
            "insights": {
                "overview": clarification_question,
                "key_findings": [],
                "recommendations": [],
                "next_steps": [],
            },
        }

    schema_text = selection["schema_text"]

    try:
        raw_sql = generate_sql(request.question, schema_text, request.history)
    except RuntimeError as e:
        logger.error(str(e))
        raise HTTPException(
            status_code=503,
            detail="AI service is unavailable right now. Please try again.",
        )

    valid_identifiers = get_valid_identifiers()
    is_valid, result = validate_sql(raw_sql, valid_identifiers)

    if not is_valid:
        raise HTTPException(status_code=400, detail=result)

    try:
        db.execute(text("SET statement_timeout = 5000"))
        rows = db.execute(text(result)).mappings().all()
    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(
            status_code=400,
            detail="The query took too long or failed. Try a narrower question.",
        )

    row_dicts = [dict(row) for row in rows]

    try:
        insights = generate_insights(request.question, row_dicts)
    except RuntimeError as e:
        logger.error(str(e))
        raise HTTPException(
            status_code=503,
            detail="AI service is unavailable right now. Please try again.",
        )

    return {
        "question": request.question,
        "sql": result,
        "rows": row_dicts,
        "insights": insights,
        "data_sources": extract_data_sources(result),
    }