"""Recommendation data model for cost optimization suggestions."""

from dataclasses import dataclass


@dataclass
class Recommendation:
    """A cost optimization recommendation.

    Attributes:
        action: Recommended action description (max 500 chars).
        resource_id: Target resource identifier.
        provider: Affected cloud provider.
        estimated_saving: Monthly saving in USD.
        generated_at: ISO 8601 timestamp of generation.
    """

    action: str
    resource_id: str
    provider: str
    estimated_saving: float
    generated_at: str
