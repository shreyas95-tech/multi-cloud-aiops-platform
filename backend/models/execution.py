"""Execution result data model for cloud operations."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExecutionResult:
    """Unified result from a cloud provider operation.

    Attributes:
        success: Whether the operation completed successfully.
        provider: Cloud provider ("AWS", "Azure", or "GCP").
        resource_id: Provider-specific resource identifier.
        action: Action that was performed.
        state: New state after action (None if unknown).
        error_code: Provider error code if failed (None on success).
        error_message: Human-readable error description (None on success).
        metadata: Additional provider-specific details.
    """

    success: bool
    provider: str
    resource_id: str
    action: str
    state: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    metadata: dict = field(default_factory=dict)
