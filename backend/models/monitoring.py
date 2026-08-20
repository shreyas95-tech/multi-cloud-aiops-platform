"""Monitoring data models for cost and resource status tracking."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class CostEntry:
    """A single cost record from a cloud provider.

    Attributes:
        provider: Cloud provider ("AWS", "Azure", or "GCP").
        resource_type: Normalized resource type.
        cost_amount: Cost in USD.
        currency: Always "USD" (normalized).
        period_start: ISO 8601 date string for period start.
        period_end: ISO 8601 date string for period end.
    """

    provider: str
    resource_type: str
    cost_amount: float
    currency: str
    period_start: str
    period_end: str


@dataclass
class ResourceStatus:
    """Status of a cloud resource.

    Attributes:
        resource_id: Provider-specific identifier.
        provider: Cloud provider ("AWS", "Azure", or "GCP").
        state: Normalized state: "running", "stopped", or "terminated".
        cpu_utilization: CPU usage 0.0-100.0 rounded to 1 decimal, or None.
        cpu_available: Whether CPU metric was available.
    """

    resource_id: str
    provider: str
    state: str
    cpu_utilization: Optional[float]
    cpu_available: bool


@dataclass
class TimePeriod:
    """A time range for filtering queries.

    Attributes:
        start: ISO 8601 date string.
        end: ISO 8601 date string.
    """

    start: str
    end: str


@dataclass
class CostComparison:
    """Cost comparison across providers for a resource type.

    Attributes:
        resource_type: The resource type being compared.
        period: The time period for the comparison.
        cheapest_providers: One or more providers with lowest cost.
        breakdown: Per-provider cost details.
    """

    resource_type: str
    period: TimePeriod
    cheapest_providers: list[str]
    breakdown: list[CostEntry]


@dataclass
class MonitoringData:
    """Aggregated monitoring data used for generating recommendations.

    Attributes:
        cost_entries: List of cost records across providers.
        resource_statuses: List of resource statuses across providers.
        period: The time period the data covers.
    """

    cost_entries: list[CostEntry]
    resource_statuses: list[ResourceStatus]
    period: TimePeriod
