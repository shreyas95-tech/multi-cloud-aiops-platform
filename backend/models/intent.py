"""Intent data model for parsed natural language queries."""

from dataclasses import dataclass


@dataclass
class IntentJSON:
    """Structured representation of a parsed natural language intent.

    Attributes:
        intent: Non-empty string describing the parsed intent.
        cloud: One of "AWS", "Azure", "GCP".
        action: Non-empty string describing the action.
        conditions: Additional conditions/parameters (may be empty string).
    """

    intent: str
    cloud: str
    action: str
    conditions: str
