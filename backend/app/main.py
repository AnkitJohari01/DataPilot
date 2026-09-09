import io

import pandas as pd
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
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
    create_dataset_import,
    delete_dataset,
    list_datasets,
    DATASET_SCHEMA,
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
from app.services.strict_answer_service import (
    DatasetSelectionError,
    DECLINED_CAUSAL_MESSAGE,
    NO_EVIDENCE_MESSAGE,
    build_allowlist,
    build_dataset_schema_text,
    is_causal_or_recommendation_question,
    resolve_selected_tables,
    validate_dataset_scoped_sql,
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


# --- Dataset import (shared CSV/Excel datasets) ---

ALLOWED_DATASET_EXTENSIONS = {".csv", ".xlsx"}


class DatasetTableResponse(BaseModel):
    display_table_name: str
    db_table_name: str
    row_count: int
    column_map: dict[str, str]


class DatasetResponse(BaseModel):
    id: int
    name: str
    created_at: str | None = None
    tables: list[DatasetTableResponse] = Field(default_factory=list)


def _dataframes_from_upload(filename: str, content: bytes) -> dict[str, "pd.DataFrame"]:
    """Parse an uploaded CSV or Excel file into display_name -> DataFrame.
    A CSV yields exactly one table named after the file; an Excel workbook
    yields one table per non-empty worksheet. Raises HTTPException on an
    unsupported extension, an unparsable file, or no usable data."""
    lower_name = filename.lower()
    suffix = lower_name[lower_name.rfind(".") :] if "." in lower_name else ""
    if suffix not in ALLOWED_DATASET_EXTENSIONS:
        raise HTTPException(
            status_code=400, detail="Only .csv and .xlsx files are supported."
        )

    if suffix == ".csv":
        try:
            df = pd.read_csv(io.BytesIO(content))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not parse CSV: {e}")
        if df.empty or len(df.columns) == 0:
            raise HTTPException(status_code=400, detail="The uploaded CSV has no data.")
        base_name = filename.rsplit(".", 1)[0]
        return {base_name: df}

    try:
        sheets = pd.read_excel(io.BytesIO(content), sheet_name=None)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse Excel file: {e}")

    non_empty = {
        sheet_name: df
        for sheet_name, df in sheets.items()
        if not df.empty and len(df.columns) > 0
    }
    if not non_empty:
        raise HTTPException(
            status_code=400, detail="The uploaded workbook has no non-empty sheets."
        )
    return non_empty


@app.post("/api/datasets", response_model=DatasetResponse, status_code=201)
def import_dataset(file: UploadFile = File(...), name: str | None = Form(None)):
    content = file.file.read()
    tables = _dataframes_from_upload(file.filename or "", content)
    dataset_name = name or (file.filename or "dataset")

    try:
        dataset = create_dataset_import(dataset_name, tables)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dataset import failed: {e}")
        raise HTTPException(status_code=400, detail=f"Import failed: {e}")

    return dataset


@app.get("/api/datasets", response_model=list[DatasetResponse])
def get_datasets():
    return list_datasets()


@app.delete("/api/datasets/{dataset_id}", status_code=204)
def remove_dataset(dataset_id: int):
    try:
        deleted = delete_dataset(dataset_id)
    except Exception as e:
        logger.error(f"Dataset delete failed: {e}")
        raise HTTPException(status_code=400, detail=f"Delete failed: {e}")

    if not deleted:
        raise HTTPException(status_code=404, detail="Dataset not found.")

    return None


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


# --- Strict, dataset-scoped ask (evidence only: no narrative, no causal
# inference, no recommendations). A parallel path to /api/ask above, which
# stays as-is for the existing full-schema, narrative-insights flow. ---


class StrictAskRequest(BaseModel):
    question: str
    dataset_ids: list[int]
    history: list[dict] = Field(default_factory=list)


class StrictAskResponse(BaseModel):
    question: str
    sql: str | None = None
    rows: list[dict] = Field(default_factory=list)
    result_count: int = 0
    sources: list[dict] = Field(default_factory=list)
    declined: bool = False
    message: str | None = None


@app.post("/api/ask/strict", response_model=StrictAskResponse)
def ask_strict(request: StrictAskRequest, db: Session = Depends(get_db)):
    try:
        tables = resolve_selected_tables(request.dataset_ids)
    except DatasetSelectionError as e:
        raise HTTPException(status_code=400, detail=e.detail)

    if is_causal_or_recommendation_question(request.question):
        return {
            "question": request.question,
            "sql": None,
            "rows": [],
            "result_count": 0,
            "sources": [],
            "declined": True,
            "message": DECLINED_CAUSAL_MESSAGE,
        }

    allowlist = build_allowlist(tables)
    schema_text = build_dataset_schema_text(tables)

    feedback = None
    rows = None
    result = None

    for attempt in range(3):
        try:
            raw_sql = generate_sql(request.question, schema_text, request.history, feedback)
        except RuntimeError as e:
            logger.error(str(e))
            raise HTTPException(
                status_code=503,
                detail="AI service is unavailable right now. Please try again.",
            )

        is_valid, validation_result = validate_dataset_scoped_sql(raw_sql, allowlist)

        if not is_valid:
            feedback = validation_result
            if attempt == 1:
                raise HTTPException(status_code=400, detail=validation_result)
            continue

        result = validation_result
        try:
            db.execute(text(f'SET search_path TO "{DATASET_SCHEMA}", public'))
            db.execute(text("SET statement_timeout = 15000"))
            rows = db.execute(text(result)).mappings().all()
            break
        except Exception as e:
            logger.error(f"Strict-ask query failed: {e}")
            db.rollback()
            feedback = f"The database rejected this query: {e}"
            if attempt == 1:
                raise HTTPException(status_code=400, detail=f"The query failed: {e}")

    row_dicts = [dict(row) for row in rows]
    sources = extract_data_sources(result)

    return {
        "question": request.question,
        "sql": result,
        "rows": row_dicts,
        "result_count": len(row_dicts),
        "sources": sources,
        "declined": False,
        "message": None if row_dicts else NO_EVIDENCE_MESSAGE,
    }