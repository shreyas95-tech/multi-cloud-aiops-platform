"""AI API endpoints: chat queries, forecasting, knowledge base management."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.auth import get_current_user
from app.api.admin import require_admin
from app.models.user import User
from app.services.chat_query import query_data
from app.services.forecaster import forecast_report
from app.services.knowledge_base import (
    ingest_document, list_documents, delete_document, retrieve_relevant_context,
)
from app.services.ai_summary import generate_deviation_summary
from app.services.llm_provider import get_llm

router = APIRouter(prefix="/ai", tags=["ai"])


# --- Schemas ---


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str
    context_used: str


# --- Chat Endpoint ---


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ask a natural language question about your data.

    Examples:
    - "What metrics dropped last week?"
    - "Compare Create Customer this month vs last month"
    - "Which reports have high severity deviations?"
    """
    result = await query_data(
        db=db,
        question=body.question,
        user_id=str(current_user.id),
        group_id=str(current_user.group_id) if current_user.group_id else None,
    )
    return ChatResponse(**result)


# --- Forecasting ---


@router.get("/forecast/{report_id}")
async def get_forecast(
    report_id: str,
    days: int = 7,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get 7-day forecast for all metrics in a report."""
    if days < 1 or days > 30:
        raise HTTPException(status_code=400, detail="Days must be between 1 and 30.")

    forecasts = await forecast_report(db, report_id, days_ahead=days)
    return {"report_id": report_id, "days_ahead": days, "forecasts": forecasts}


# --- Knowledge Base ---


@router.post("/knowledge-base/upload")
async def upload_knowledge_doc(
    file: UploadFile = File(...),
    doc_type: str = Form(default="runbook"),
    admin: User = Depends(require_admin),
):
    """Upload a document to the knowledge base (admin only).

    Supports .txt, .md, .pdf files. Documents are chunked and embedded
    for RAG retrieval when deviations are detected.
    """
    filename = file.filename or "unknown"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in ("txt", "md", "pdf", "csv"):
        raise HTTPException(status_code=400, detail="Supported formats: .txt, .md, .pdf, .csv")

    content_bytes = await file.read()
    if len(content_bytes) == 0:
        raise HTTPException(status_code=400, detail="File is empty.")

    # Extract text content
    if ext == "pdf":
        try:
            import pdfplumber
            import io
            with pdfplumber.open(io.BytesIO(content_bytes)) as pdf:
                text_content = "\n\n".join(
                    page.extract_text() or "" for page in pdf.pages
                )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to extract PDF text: {e}")
    else:
        text_content = content_bytes.decode("utf-8", errors="replace")

    if not text_content.strip():
        raise HTTPException(status_code=400, detail="No text content found in file.")

    result = ingest_document(
        filename=filename,
        content=text_content,
        doc_type=doc_type,
    )

    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error", "Ingestion failed."))

    return result


@router.get("/knowledge-base")
async def list_kb_documents(
    current_user: User = Depends(get_current_user),
):
    """List all documents in the knowledge base."""
    docs = list_documents()
    return {"documents": docs, "count": len(docs)}


@router.delete("/knowledge-base/{doc_id}")
async def delete_kb_document(
    doc_id: str,
    admin: User = Depends(require_admin),
):
    """Delete a document from the knowledge base (admin only)."""
    success = delete_document(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"message": "Document deleted."}


@router.post("/knowledge-base/search")
async def search_knowledge_base(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    """Search the knowledge base for relevant information."""
    results = retrieve_relevant_context(body.question, top_k=5)
    return {"results": results, "count": len(results)}


# --- LLM Status ---


@router.get("/status")
async def ai_status(
    current_user: User = Depends(get_current_user),
):
    """Check if the AI/LLM service is available."""
    llm = get_llm()
    available = llm.is_available()
    return {
        "llm_available": available,
        "provider": type(llm).__name__,
        "model": getattr(llm, "model", "unknown"),
    }
