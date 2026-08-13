from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database.metadata import get_schema_summary, get_compact_schema
from app.config.settings import settings
from app.database.connection import get_db
from pydantic import BaseModel
from app.services.gemini_service import generate_sql, validate_sql

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

@app.post("/api/ask")
def ask(request: AskRequest):
    schema_text = get_compact_schema()
    raw_sql = generate_sql(request.question, schema_text)

    is_valid, result = validate_sql(raw_sql)
    if not is_valid:
        raise HTTPException(status_code=400, detail=result)

    return {"question": request.question, "sql": result}