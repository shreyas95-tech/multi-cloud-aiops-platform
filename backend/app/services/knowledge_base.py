"""RAG Knowledge Base service.

Manages document ingestion, chunking, embedding, and retrieval
for providing contextual runbook/SOP steps when deviations are detected.

Uses ChromaDB as the vector store and sentence-transformers for embeddings.
"""

import os
import uuid
from pathlib import Path
from typing import Optional

import structlog
from dotenv import load_dotenv

load_dotenv()

logger = structlog.get_logger(__name__)

# --- Configuration ---

KB_STORAGE_DIR = os.environ.get("KB_STORAGE_DIR", "./knowledge_base")
CHROMA_PERSIST_DIR = os.environ.get("CHROMA_PERSIST_DIR", "./chroma_db")
CHUNK_SIZE = 500  # characters per chunk
CHUNK_OVERLAP = 50  # overlap between chunks
TOP_K_RESULTS = 3  # number of relevant chunks to retrieve


# --- ChromaDB Client ---

_chroma_client = None
_collection = None


def _get_collection():
    """Get or create the ChromaDB collection. Lazy initialization."""
    global _chroma_client, _collection
    if _collection is None:
        try:
            import chromadb
            from chromadb.config import Settings

            os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
            _chroma_client = chromadb.PersistentClient(
                path=CHROMA_PERSIST_DIR,
                settings=Settings(anonymized_telemetry=False),
            )
            _collection = _chroma_client.get_or_create_collection(
                name="knowledge_base",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("chromadb_initialized", persist_dir=CHROMA_PERSIST_DIR)
        except ImportError:
            logger.warning("chromadb_not_installed")
            return None
        except Exception as e:
            logger.warning("chromadb_init_skipped", error=str(e))
            return None
    return _collection


# --- Document Chunking ---


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks for embedding.

    Args:
        text: Full document text.
        chunk_size: Max characters per chunk.
        overlap: Character overlap between consecutive chunks.

    Returns:
        List of text chunks.
    """
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        # Try to break at sentence boundary
        if end < len(text):
            last_period = chunk.rfind(".")
            last_newline = chunk.rfind("\n")
            break_point = max(last_period, last_newline)
            if break_point > chunk_size * 0.5:
                chunk = chunk[: break_point + 1]
                end = start + break_point + 1
        chunks.append(chunk.strip())
        start = end - overlap
    return [c for c in chunks if len(c) > 20]  # Filter tiny chunks


# --- Document Ingestion ---


def ingest_document(
    filename: str,
    content: str,
    doc_type: str = "runbook",
    metadata: dict = None,
) -> dict:
    """Ingest a document into the knowledge base.

    Chunks the document, generates embeddings, and stores in ChromaDB.

    Args:
        filename: Original filename.
        content: Full text content of the document.
        doc_type: Type of document (runbook, sop, guide).
        metadata: Optional additional metadata.

    Returns:
        Dict with ingestion stats.
    """
    collection = _get_collection()
    if collection is None:
        return {"success": False, "error": "ChromaDB not available."}

    # Chunk the document
    chunks = chunk_text(content)
    if not chunks:
        return {"success": False, "error": "No content to index."}

    # Generate IDs and metadata for each chunk
    doc_id = str(uuid.uuid4())
    ids = []
    documents = []
    metadatas = []

    for i, chunk in enumerate(chunks):
        chunk_id = f"{doc_id}_chunk_{i}"
        ids.append(chunk_id)
        documents.append(chunk)
        metadatas.append({
            "doc_id": doc_id,
            "filename": filename,
            "doc_type": doc_type,
            "chunk_index": i,
            "total_chunks": len(chunks),
            **(metadata or {}),
        })

    # Add to ChromaDB (uses built-in embedding function)
    try:
        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )
        logger.info("document_ingested", filename=filename, chunks=len(chunks), doc_id=doc_id)
        return {
            "success": True,
            "doc_id": doc_id,
            "filename": filename,
            "chunks_created": len(chunks),
        }
    except Exception as e:
        logger.error("ingestion_error", error=str(e))
        return {"success": False, "error": str(e)}


# --- Retrieval ---


def retrieve_relevant_context(query: str, top_k: int = TOP_K_RESULTS) -> list[dict]:
    """Retrieve relevant knowledge base chunks for a query.

    Args:
        query: Search query (e.g., metric name + deviation description).
        top_k: Number of results to return.

    Returns:
        List of dicts with 'text', 'filename', 'doc_type', 'relevance_score'.
    """
    collection = _get_collection()
    if collection is None:
        return []

    try:
        results = collection.query(
            query_texts=[query],
            n_results=top_k,
        )

        if not results or not results["documents"] or not results["documents"][0]:
            return []

        context_items = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            distance = results["distances"][0][i] if results["distances"] else 1.0
            context_items.append({
                "text": doc,
                "filename": meta.get("filename", "unknown"),
                "doc_type": meta.get("doc_type", "unknown"),
                "relevance_score": round(1 - distance, 3),  # Convert distance to similarity
            })

        return context_items
    except Exception as e:
        logger.error("retrieval_error", error=str(e))
        return []


def get_runbook_steps(metric_name: str, severity: str, deviation_description: str) -> str:
    """Retrieve and format relevant runbook steps for a deviation.

    This is called during deviation detection to provide actionable steps.

    Args:
        metric_name: The metric that deviated.
        severity: Deviation severity.
        deviation_description: Brief description of what happened.

    Returns:
        Formatted string with relevant steps, or empty string if none found.
    """
    query = f"{metric_name} {severity} deviation: {deviation_description}"
    results = retrieve_relevant_context(query, top_k=TOP_K_RESULTS)

    if not results:
        return ""

    # Format results into actionable steps
    steps = []
    for i, item in enumerate(results, 1):
        source = item["filename"]
        text = item["text"]
        steps.append(f"**From {source}:**\n{text}")

    return "\n\n---\n\n".join(steps)


# --- List Documents ---


def list_documents() -> list[dict]:
    """List all documents in the knowledge base."""
    collection = _get_collection()
    if collection is None:
        return []

    try:
        # Get all unique doc_ids
        all_items = collection.get(include=["metadatas"])
        if not all_items or not all_items["metadatas"]:
            return []

        docs = {}
        for meta in all_items["metadatas"]:
            doc_id = meta.get("doc_id", "")
            if doc_id not in docs:
                docs[doc_id] = {
                    "doc_id": doc_id,
                    "filename": meta.get("filename", "unknown"),
                    "doc_type": meta.get("doc_type", "unknown"),
                    "total_chunks": meta.get("total_chunks", 0),
                }

        return list(docs.values())
    except Exception as e:
        logger.error("list_docs_error", error=str(e))
        return []


def delete_document(doc_id: str) -> bool:
    """Delete a document from the knowledge base by doc_id."""
    collection = _get_collection()
    if collection is None:
        return False

    try:
        # Find all chunk IDs for this document
        results = collection.get(where={"doc_id": doc_id}, include=["metadatas"])
        if results and results["ids"]:
            collection.delete(ids=results["ids"])
            logger.info("document_deleted", doc_id=doc_id)
            return True
        return False
    except Exception as e:
        logger.error("delete_doc_error", error=str(e))
        return False
