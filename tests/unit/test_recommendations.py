"""Unit tests for recommendation generation logic.

Tests the AILayer.generate_recommendations() method including:
- Validation of minimum 24 hours of monitoring data
- Handling of insufficient data (no entries)
- Constraint enforcement: 1-50 results, max 500 chars per action
- ISO 8601 timestamp on each recommendation
- Idle resource detection and high-cost resource detection

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5
"""

from datetime import datetime, timedelta, timezone

import pytest

from backend.ai_layer.exceptions import InsufficientDataError
from backend.ai_layer.parser import AILayer
from backend.models.monitoring import (
    CostEntry,
    MonitoringData,
    ResourceStatus,
    TimePeriod,
)
from backend.models.recommendation import Recommendation


@pytest.fixture
def ai_layer():
    """Create an AILayer instance for testing."""
    return AILayer()


def _make_period(hours: int = 48) -> TimePeriod:
    """Create a TimePeriod spanning the specified number of hours from now."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    return TimePeriod(start=start.isoformat(), end=end.isoformat())


def _make_monitoring_data(
    cost_entries=None,
    resource_statuses=None,
    period_hours: int = 48,
) -> MonitoringData:
    """Helper to build MonitoringData with defaults."""
    return MonitoringData(
        cost_entries=cost_entries or [],
        resource_statuses=resource_statuses or [],
        period=_make_period(period_hours),
    )


# --- Test: Insufficient data raises InsufficientDataError ---


class TestInsufficientData:
    """Tests for insufficient monitoring data handling."""

    @pytest.mark.asyncio
    async def test_no_data_raises_insufficient_data_error(self, ai_layer):
        """No cost entries and no resource statuses raises InsufficientDataError."""
        monitoring_data = _make_monitoring_data(
            cost_entries=[], resource_statuses=[]
        )

        with pytest.raises(InsufficientDataError) as exc_info:
            await ai_layer.generate_recommendations(monitoring_data)

        assert "No cost entries or resource statuses" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_less_than_24h_coverage_raises_error(self, ai_layer):
        """Data covering less than 24 hours raises InsufficientDataError."""
        monitoring_data = _make_monitoring_data(
            cost_entries=[
                CostEntry(
                    provider="AWS",
                    resource_type="EC2",
                    cost_amount=50.0,
                    currency="USD",
                    period_start="2024-01-01T00:00:00+00:00",
                    period_end="2024-01-01T12:00:00+00:00",
                )
            ],
            period_hours=12,  # Only 12 hours
        )

        with pytest.raises(InsufficientDataError) as exc_info:
            await ai_layer.generate_recommendations(monitoring_data)

        assert "24 hours" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_exactly_24h_coverage_does_not_raise(self, ai_layer):
        """Data covering exactly 24 hours should not raise error."""
        monitoring_data = _make_monitoring_data(
            cost_entries=[
                CostEntry(
                    provider="AWS",
                    resource_type="EC2",
                    cost_amount=50.0,
                    currency="USD",
                    period_start="2024-01-01T00:00:00+00:00",
                    period_end="2024-01-02T00:00:00+00:00",
                )
            ],
            period_hours=24,  # Exactly 24 hours
        )

        result = await ai_layer.generate_recommendations(monitoring_data)
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_error_message_is_informative(self, ai_layer):
        """Error message clearly states what is needed."""
        monitoring_data = _make_monitoring_data(
            cost_entries=[], resource_statuses=[]
        )

        with pytest.raises(InsufficientDataError) as exc_info:
            await ai_layer.generate_recommendations(monitoring_data)

        # Should mention monitoring data and/or cost entries
        msg = str(exc_info.value)
        assert "monitoring data" in msg.lower() or "cost entries" in msg.lower()


# --- Test: Output count constraints (1-50) ---


class TestOutputCountConstraints:
    """Tests for recommendation count between 1 and 50."""

    @pytest.mark.asyncio
    async def test_at_least_one_recommendation(self, ai_layer):
        """Even with no optimization opportunities, at least 1 recommendation is returned."""
        monitoring_data = _make_monitoring_data(
            cost_entries=[
                CostEntry(
                    provider="AWS",
                    resource_type="EC2",
                    cost_amount=5.0,  # Low cost, won't trigger
                    currency="USD",
                    period_start="2024-01-01T00:00:00+00:00",
                    period_end="2024-01-03T00:00:00+00:00",
                )
            ],
            resource_statuses=[
                ResourceStatus(
                    resource_id="i-123",
                    provider="AWS",
                    state="running",
                    cpu_utilization=80.0,  # High CPU, won't trigger
                    cpu_available=True,
                )
            ],
        )

        result = await ai_layer.generate_recommendations(monitoring_data)
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_max_50_recommendations(self, ai_layer):
        """Output is capped at 50 recommendations even with more data."""
        # Create 60 high-cost entries that would each generate a recommendation
        cost_entries = [
            CostEntry(
                provider="AWS",
                resource_type=f"type-{i}",
                cost_amount=200.0,
                currency="USD",
                period_start="2024-01-01T00:00:00+00:00",
                period_end="2024-01-03T00:00:00+00:00",
            )
            for i in range(60)
        ]

        monitoring_data = _make_monitoring_data(cost_entries=cost_entries)

        result = await ai_layer.generate_recommendations(monitoring_data)
        assert len(result) <= 50


# --- Test: Action text max 500 characters ---


class TestActionLengthConstraint:
    """Tests that recommendation action text is truncated to 500 chars."""

    @pytest.mark.asyncio
    async def test_action_text_within_500_chars(self, ai_layer):
        """All recommendation actions are at most 500 characters."""
        monitoring_data = _make_monitoring_data(
            cost_entries=[
                CostEntry(
                    provider="AWS",
                    resource_type="EC2",
                    cost_amount=150.0,
                    currency="USD",
                    period_start="2024-01-01T00:00:00+00:00",
                    period_end="2024-01-03T00:00:00+00:00",
                )
            ],
            resource_statuses=[
                ResourceStatus(
                    resource_id="i-abc123",
                    provider="AWS",
                    state="running",
                    cpu_utilization=2.0,
                    cpu_available=True,
                )
            ],
        )

        result = await ai_layer.generate_recommendations(monitoring_data)
        for rec in result:
            assert len(rec.action) <= 500

    @pytest.mark.asyncio
    async def test_long_resource_type_gets_truncated(self, ai_layer):
        """A very long resource_type that would exceed 500 chars is truncated."""
        long_type = "x" * 600  # This will make the action text very long
        monitoring_data = _make_monitoring_data(
            cost_entries=[
                CostEntry(
                    provider="AWS",
                    resource_type=long_type,
                    cost_amount=200.0,
                    currency="USD",
                    period_start="2024-01-01T00:00:00+00:00",
                    period_end="2024-01-03T00:00:00+00:00",
                )
            ],
        )

        result = await ai_layer.generate_recommendations(monitoring_data)
        for rec in result:
            assert len(rec.action) <= 500


# --- Test: ISO 8601 timestamp ---


class TestTimestamp:
    """Tests that generated_at is a valid ISO 8601 timestamp."""

    @pytest.mark.asyncio
    async def test_generated_at_is_valid_iso8601(self, ai_layer):
        """Each recommendation has a valid ISO 8601 generated_at timestamp."""
        monitoring_data = _make_monitoring_data(
            cost_entries=[
                CostEntry(
                    provider="AWS",
                    resource_type="EC2",
                    cost_amount=150.0,
                    currency="USD",
                    period_start="2024-01-01T00:00:00+00:00",
                    period_end="2024-01-03T00:00:00+00:00",
                )
            ],
        )

        result = await ai_layer.generate_recommendations(monitoring_data)
        for rec in result:
            # Should be parseable as ISO 8601
            parsed = datetime.fromisoformat(rec.generated_at)
            assert parsed.tzinfo is not None or "Z" in rec.generated_at

    @pytest.mark.asyncio
    async def test_generated_at_is_utc(self, ai_layer):
        """The generated_at timestamp is in UTC."""
        monitoring_data = _make_monitoring_data(
            resource_statuses=[
                ResourceStatus(
                    resource_id="i-123",
                    provider="AWS",
                    state="running",
                    cpu_utilization=5.0,
                    cpu_available=True,
                )
            ],
        )

        result = await ai_layer.generate_recommendations(monitoring_data)
        for rec in result:
            parsed = datetime.fromisoformat(rec.generated_at)
            assert parsed.tzinfo == timezone.utc


# --- Test: Recommendation logic (idle resources, high-cost) ---


class TestRecommendationLogic:
    """Tests for the recommendation generation logic."""

    @pytest.mark.asyncio
    async def test_idle_resource_gets_stop_recommendation(self, ai_layer):
        """Running resource with < 10% CPU gets stop/downsize recommendation."""
        monitoring_data = _make_monitoring_data(
            resource_statuses=[
                ResourceStatus(
                    resource_id="i-idle123",
                    provider="AWS",
                    state="running",
                    cpu_utilization=3.5,
                    cpu_available=True,
                )
            ],
        )

        result = await ai_layer.generate_recommendations(monitoring_data)
        # Find the recommendation for this resource
        idle_recs = [r for r in result if r.resource_id == "i-idle123"]
        assert len(idle_recs) == 1
        assert "stop" in idle_recs[0].action.lower() or "downsize" in idle_recs[0].action.lower()

    @pytest.mark.asyncio
    async def test_high_cpu_resource_no_idle_recommendation(self, ai_layer):
        """Running resource with > 10% CPU does not get idle recommendation."""
        monitoring_data = _make_monitoring_data(
            resource_statuses=[
                ResourceStatus(
                    resource_id="i-busy456",
                    provider="AWS",
                    state="running",
                    cpu_utilization=75.0,
                    cpu_available=True,
                )
            ],
        )

        result = await ai_layer.generate_recommendations(monitoring_data)
        # Should not have a stop/downsize rec for this resource
        idle_recs = [r for r in result if r.resource_id == "i-busy456"]
        assert len(idle_recs) == 0

    @pytest.mark.asyncio
    async def test_high_cost_resource_gets_review_recommendation(self, ai_layer):
        """Cost entry > $100 triggers a review recommendation."""
        monitoring_data = _make_monitoring_data(
            cost_entries=[
                CostEntry(
                    provider="Azure",
                    resource_type="VirtualMachine",
                    cost_amount=250.0,
                    currency="USD",
                    period_start="2024-01-01T00:00:00+00:00",
                    period_end="2024-01-03T00:00:00+00:00",
                )
            ],
        )

        result = await ai_layer.generate_recommendations(monitoring_data)
        review_recs = [r for r in result if "review" in r.action.lower()]
        assert len(review_recs) >= 1
        assert review_recs[0].provider == "Azure"

    @pytest.mark.asyncio
    async def test_low_cost_resource_no_review_recommendation(self, ai_layer):
        """Cost entry <= $100 does not trigger a review recommendation."""
        monitoring_data = _make_monitoring_data(
            cost_entries=[
                CostEntry(
                    provider="GCP",
                    resource_type="ComputeEngine",
                    cost_amount=50.0,
                    currency="USD",
                    period_start="2024-01-01T00:00:00+00:00",
                    period_end="2024-01-03T00:00:00+00:00",
                )
            ],
        )

        result = await ai_layer.generate_recommendations(monitoring_data)
        # Should get a general "no opportunities" recommendation
        assert len(result) == 1
        assert "no specific" in result[0].action.lower() or "well-utilized" in result[0].action.lower()

    @pytest.mark.asyncio
    async def test_stopped_resource_no_idle_recommendation(self, ai_layer):
        """Stopped resources do not trigger idle recommendations."""
        monitoring_data = _make_monitoring_data(
            resource_statuses=[
                ResourceStatus(
                    resource_id="i-stopped789",
                    provider="AWS",
                    state="stopped",
                    cpu_utilization=None,
                    cpu_available=False,
                )
            ],
        )

        result = await ai_layer.generate_recommendations(monitoring_data)
        # Should not recommend stopping an already-stopped resource
        stop_recs = [r for r in result if r.resource_id == "i-stopped789"]
        assert len(stop_recs) == 0

    @pytest.mark.asyncio
    async def test_recommendation_includes_estimated_saving(self, ai_layer):
        """Each recommendation includes an estimated_saving value."""
        monitoring_data = _make_monitoring_data(
            cost_entries=[
                CostEntry(
                    provider="AWS",
                    resource_type="EC2",
                    cost_amount=300.0,
                    currency="USD",
                    period_start="2024-01-01T00:00:00+00:00",
                    period_end="2024-01-03T00:00:00+00:00",
                )
            ],
        )

        result = await ai_layer.generate_recommendations(monitoring_data)
        for rec in result:
            assert isinstance(rec.estimated_saving, float)
            assert rec.estimated_saving >= 0.0
