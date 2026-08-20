"""API response data model for the unified response envelope."""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class APIResponse:
    """Unified API response envelope.

    Attributes:
        status: "success" or "error".
        data: Response payload on success (None on error).
        error: Error details on failure: {field, message} (None on success).
    """

    status: str
    data: Optional[Any] = None
    error: Optional[dict] = None
