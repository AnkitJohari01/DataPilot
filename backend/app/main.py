from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, Field

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
    refresh_catalog_cache,
)
from app.services.gemini_service import (
    extract_data_sources,
    generate_diagnostic_sql,
    generate_insights,
    generate_sql,
    validate_sql,
)

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


@app.get("/api/catalog")
def get_catalog():
    return get_schema_catalog()

@app.post("/api/catalog/refresh")
def refresh_catalog():
    table_count = refresh_catalog_cache()
    return {
        "status": "refreshed",
        "tables_reembedded": table_count,
    }


class AskRequest(BaseModel):
    question: str
    history: list[dict] = Field(default_factory=list)

class PresentationSection(BaseModel):
    title: str
    items: list[str] = Field(default_factory=list)

class PresentationPayload(BaseModel):
    title: str
    summary: str
    details: list[PresentationSection] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)

class AskResponse(BaseModel):
    question: str
    sql: str | None = None
    rows: list[dict] = Field(default_factory=list)
    insights: dict
    data_sources: list[dict] = Field(default_factory=list)
    clarification_required: bool = False
    presentation: PresentationPayload

def build_presentation(
    question: str,
    insights: dict,
    rows: list[dict],
    data_sources: list[dict],
    sql: str | None = None,
    clarification_required: bool = False,
) -> PresentationPayload:
    details = []
    section_map = (
        ("Key findings", "key_findings"),
        ("Recommendations", "recommendations"),
        ("Next steps", "next_steps"),
        ("Data sources", "data_sources"),
    )
    for title, key in section_map:
        items = [str(item) for item in insights.get(key, [])]
        if items:
            details.append(PresentationSection(title=title, items=items))

    return PresentationPayload(
        title=("Clarification needed" if clarification_required else question.strip()),
        summary=str(insights.get("overview", "")),
        details=details,
        metadata={
            "result_count": len(rows),
            "source_count": len(data_sources),
            "has_sql": sql is not None,
        },
    )

@app.post("/api/ask", response_model=AskResponse)
def ask(request: AskRequest, db: Session = Depends(get_db)):
    selection = get_semantic_catalog_selection(
        request.question, history=request.history
    )

    ambiguous = needs_clarification(
        selection["best_score"],
        selection["second_best_score"],
    )
    direct_match = has_direct_catalog_match(
        request.question, selection["candidate_tables"]
    )

    if ambiguous and not direct_match:
        clarification_question = build_clarification_question(
            selection["candidate_table_names"]
        )

        insights = {
            "overview": clarification_question,
            "key_findings": [],
            "recommendations": [],
            "next_steps": [],
            "data_sources": [],
        }
        return {
            "question": request.question,
            "sql": None,
            "rows": [],
            "clarification_required": True,
            "insights": insights,
            "presentation": build_presentation(
                request.question, insights, [], [], clarification_required=True
            ),
        }

    schema_text = selection["schema_text"]

    valid_identifiers = get_valid_identifiers()
    feedback = None
    rows = None

    for attempt in range(3):
        try:
            raw_sql = generate_sql(request.question, schema_text, request.history, feedback)
        except RuntimeError as e:
            logger.error(str(e))
            raise HTTPException(
                status_code=503,
                detail="AI service is unavailable right now. Please try again.",
            )

        is_valid, result = validate_sql(raw_sql, valid_identifiers)

        if not is_valid:
            feedback = result
            if attempt == 1:
                raise HTTPException(status_code=400, detail=result)
            continue

        try:
            db.execute(text("SET statement_timeout = 15000"))
            rows = db.execute(text(result)).mappings().all()
            break
        except Exception as e:
            logger.error(f"Query failed: {e}")
            db.rollback()
            feedback = f"The database rejected this query: {e}"
            if attempt == 1:
                raise HTTPException(
                    status_code=400,
                    detail=f"The query failed: {e}",
                )

    row_dicts = [dict(row) for row in rows]

    data_sources = extract_data_sources(result)

    breakdown_rows: list[dict] = []
    try:
        # Use the FULL catalog here, not the narrowed semantic selection
        # (`schema_text`) used for the primary query. The semantic
        # selection is scored against the literal question text, so a
        # question like "why did sales drop in March" can easily leave
        # out dimension tables like dim_product (category) or
        # dim_location (region) that never got mentioned by name but are
        # exactly what a breakdown needs to be useful.
        full_schema_text = get_catalog_for_llm()
        diagnostic_sql = generate_diagnostic_sql(
            request.question, full_schema_text, primary_sql=result
        )
        if diagnostic_sql.strip().upper() != "NONE":
            diag_is_valid, diag_result = validate_sql(diagnostic_sql, valid_identifiers)
            if diag_is_valid:
                db.execute(text("SET statement_timeout = 15000"))
                diag_rows = db.execute(text(diag_result)).mappings().all()
                breakdown_rows = [dict(row) for row in diag_rows]
                data_sources = data_sources + [
                    src
                    for src in extract_data_sources(diag_result)
                    if src not in data_sources
                ]
            else:
                logger.warning(
                    "Diagnostic breakdown query invalid, skipping: %s", diag_result
                )
    except Exception as e:
        # A failed diagnostic breakdown should never block the primary answer.
        logger.warning("Diagnostic breakdown query failed, skipping: %s", e)

    try:
        insights = generate_insights(
            request.question,
            row_dicts,
            data_sources=data_sources,
            breakdown_rows=breakdown_rows,
        )
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
        "data_sources": data_sources,
        "presentation": build_presentation(
            request.question, insights, row_dicts, data_sources, sql=result
        ),
    }