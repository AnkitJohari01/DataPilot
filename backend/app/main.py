from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database.metadata import get_schema_summary, get_compact_schema
from app.config.settings import settings
from app.database.connection import get_db
from pydantic import BaseModel
from app.services.gemini_service import generate_insights, generate_sql, validate_sql

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("datapilot")

app = FastAPI(title="DataPilot API")

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


class AskRequest(BaseModel):
    question: str
    history: list[dict] = []


@app.post("/api/ask")
def ask(request: AskRequest, db: Session = Depends(get_db)):
    schema_text = get_compact_schema()

    try:
        raw_sql = generate_sql(request.question, schema_text, request.history)
    except RuntimeError as e:
        logger.error(str(e))
        raise HTTPException(status_code=503, detail="AI service is unavailable right now. Please try again.")

    is_valid, result = validate_sql(raw_sql)
    if not is_valid:
        raise HTTPException(status_code=400, detail=result)

    try:
        db.execute(text("SET statement_timeout = 5000"))
        rows = db.execute(text(result)).mappings().all()
    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(status_code=400, detail="The query took too long or failed. Try a narrower question.")

    row_dicts = [dict(row) for row in rows]

    try:
        insights = generate_insights(request.question, row_dicts)
    except RuntimeError as e:
        logger.error(str(e))
        raise HTTPException(status_code=503, detail="AI service is unavailable right now. Please try again.")

    return {
        "question": request.question,
        "sql": result,
        "rows": row_dicts,
        "insights": insights,
    }