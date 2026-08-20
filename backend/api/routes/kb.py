"""KB document management routes — upload, list, and download documents."""

import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from backend.api.main import success_response
from backend.api.middleware.auth_middleware import get_current_user
from backend.api.middleware.rbac import require_not_first_time, require_role
from backend.database import get_db

router = APIRouter(prefix="/api/kb", tags=["kb"])

# Allowed content types for KB document upload
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}

# Maximum file size: 10 MB
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB in bytes

# Upload directory path (relative to project root)
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "uploads", "kb")


@router.post(
    "/documents",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("Admin")), Depends(require_not_first_time())],
)
async def upload_document(
    title: str = Form(...),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Upload a KB document (Admin only).

    Accepts a file upload with a title. Validates file type (PDF, DOCX, plain text)
    and size (<=10 MB). Stores the file and saves metadata to the database.

    Returns:
        201 with {"document_id": id}
    """
    # Validate content type
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {file.content_type}. Allowed: PDF, DOCX, plain text.",
        )

    # Read file content and validate size
    content = await file.read()
    file_size = len(content)

    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size ({file_size} bytes) exceeds maximum allowed size of 10 MB.",
        )

    # Generate unique filename and save to disk
    original_filename = file.filename or "unnamed"
    stored_filename = f"{uuid.uuid4()}_{original_filename}"
    file_path = os.path.join(UPLOAD_DIR, stored_filename)

    # Ensure upload directory exists
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    with open(file_path, "wb") as f:
        f.write(content)

    # Insert metadata into database
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO kb_documents (title, filename, file_path, content_type, file_size, uploaded_by, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                original_filename,
                file_path,
                file.content_type,
                file_size,
                current_user["username"],
                datetime.utcnow().isoformat(),
            ),
        )
        await db.commit()
        document_id = cursor.lastrowid

    return {"document_id": document_id}


@router.get(
    "/documents",
    dependencies=[Depends(require_not_first_time())],
)
async def list_documents(current_user: dict = Depends(get_current_user)):
    """List all KB documents (Authenticated users).

    Returns a list of documents with title, upload date, and uploader name.
    """
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, title, filename, content_type, file_size, uploaded_by, uploaded_at FROM kb_documents ORDER BY uploaded_at DESC"
        )
        rows = await cursor.fetchall()

    documents = [
        {
            "id": row[0],
            "title": row[1],
            "filename": row[2],
            "content_type": row[3],
            "file_size": row[4],
            "uploaded_by": row[5],
            "uploaded_at": row[6],
        }
        for row in rows
    ]

    return success_response(documents)


@router.get(
    "/documents/{document_id}",
    dependencies=[Depends(require_not_first_time())],
)
async def get_document(document_id: int, current_user: dict = Depends(get_current_user)):
    """Download a KB document by ID (Authenticated users).

    Returns the file as a download. Returns 404 if not found.
    """
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT file_path, filename, content_type FROM kb_documents WHERE id = ?",
            (document_id,),
        )
        row = await cursor.fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found.",
        )

    file_path = row[0]
    filename = row[1]
    content_type = row[2]

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document file not found on disk.",
        )

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type=content_type,
    )
