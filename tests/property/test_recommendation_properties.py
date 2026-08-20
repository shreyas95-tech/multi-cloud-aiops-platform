"""Property-based tests for Recommendations.

Property 18: Recommendation structure invariants — generate random monitoring datasets,
verify output constraints (1-50 count, ≤500 chars, valid ISO 8601 timestamp,
monetary value, resource ID, provider).

**Validates: Requirements 9.1, 9.2, 9.5**
"""

from datetime import datetime, timedelta, timezone

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from backend.ai_layer.parser import AILayer
from backend.models.monitoring import (
    CostEntry,
    MonitoringData,
    ResourceStatus,
    TimePeriod,
)
from backend.models.recommendation import Recommendation


# --- Strategies ---

# Supported providers
provider_strategy = st.sampled_from(["AWS", "Azure", "GCP"])

# Resource types
resource_type_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
    min_size=1,
    max_size=30,
)

# Cost amounts (positive floats, varied range to trigger high-cost recommendations)
cost_amount_strategy = st.floats(
    min_value=0.01, max_value=5000.0, allow_nan=False, allow_infinity=False
)

# Resource IDs
resource_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
    min_size=1,
    max_size=40,
)

# CPU utilization (0.0-100.0, varied to trigger low-CPU recommendations)
cpu_strategy = st.floats(
    min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False
)

# Instance states
state_strategy = st.sampled_from(["running", "stopped", "terminated"])


# Strategy for CostEntry
@st.composite
def cost_entry_strategy(draw):
    """Generate a random CostEntry."""
    provider = draw(provider_strategy)
    resource_type = draw(resource_type_strategy)
    cost_amount = draw(cost_amount_strategy)
    return CostEntry(
        provider=provider,
        resource_type=resource_type,
        cost_amount=cost_amount,
        currency="USD",
        period_start="2024-01-01",
        period_end="2024-01-31",
    )


# Strategy for ResourceStatus
@st.composite
def resource_status_strategy(draw):
    """Generate a random ResourceStatus."""
    resource_id = draw(resource_id_strategy)
    provider = draw(provider_strategy)
    state = draw(state_strategy)
    cpu = draw(cpu_strategy)
    cpu_available = state == "running"
    return ResourceStatus(
        resource_id=resource_id,
        provider=provider,
        state=state,
        cpu_utilization=round(cpu, 1) if cpu_available else None,
        cpu_available=cpu_available,
    )


# Strategy for MonitoringData with at least 24h coverage
@st.composite
def monitoring_data_strategy(draw):
    """Generate random MonitoringData with at least 24h coverage and some data."""
    cost_entries = draw(
        st.lists(cost_entry_strategy(), min_size=0, max_size=10)
    )
    resource_statuses = draw(
        st.lists(resource_status_strategy(), min_size=0, max_size=10)
    )

    # Ensure we have at least some data (cost entries or resource statuses)
    if not cost_entries and not resource_statuses:
        # Force at least one cost entry
        cost_entries = [draw(cost_entry_strategy())]

    # Generate a period covering at least 24 hours
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=draw(st.integers(min_value=2, max_value=30)))
    end = now

    period = TimePeriod(
        start=start.isoformat(),
        end=end.isoformat(),
    )

    return MonitoringData(
        cost_entries=cost_entries,
        resource_statuses=resource_statuses,
        period=period,
    )


# --- Property 18: Recommendation structure invariants ---


class TestProperty18RecommendationStructureInvariants:
    """Property 18: Recommendation structure invariants.

    For any AI-generated recommendation, it SHALL contain: a natural language description
    of no more than 500 characters specifying the recommended action, a target resource
    identifier, an affected cloud provider, an estimated monthly saving as a monetary value,
    and a valid ISO 8601 timestamp indicating when it was generated. The total count of
    recommendations for any single request SHALL be between 1 and 50 inclusive.

    **Validates: Requirements 9.1, 9.2, 9.5**
    """

    @settings(max_examples=100)
    @given(monitoring_data=monitoring_data_strategy())
    @pytest.mark.asyncio
    async def test_recommendation_count_between_1_and_50(
        self,
        monitoring_data: MonitoringData,
    ) -> None:
        """The number of recommendations is between 1 and 50 inclusive."""
        ai_layer = AILayer()
        recommendations = await ai_layer.generate_recommendations(monitoring_data)

        assert isinstance(recommendations, list)
        assert 1 <= len(recommendations) <= 50

    @settings(max_examples=100)
    @given(monitoring_data=monitoring_data_strategy())
    @pytest.mark.asyncio
    async def test_recommendation_action_max_500_chars(
        self,
        monitoring_data: MonitoringData,
    ) -> None:
        """Each recommendation action is at most 500 characters."""
        ai_layer = AILayer()
        recommendations = await ai_layer.generate_recommendations(monitoring_data)

        for rec in recommendations:
            assert isinstance(rec.action, str)
            assert len(rec.action) <= 500

    @settings(max_examples=100)
    @given(monitoring_data=monitoring_data_strategy())
    @pytest.mark.asyncio
    async def test_recommendation_valid_iso8601_timestamp(
        self,
        monitoring_data: MonitoringData,
    ) -> None:
        """Each recommendation generated_at is a valid ISO 8601 timestamp."""
        ai_layer = AILayer()
        recommendations = await ai_layer.generate_recommendations(monitoring_data)

        for rec in recommendations:
            assert isinstance(rec.generated_at, str)
            # Must be parseable by datetime.fromisoformat
            parsed = datetime.fromisoformat(rec.generated_at)
            assert isinstance(parsed, datetime)

    @settings(max_examples=100)
    @given(monitoring_data=monitoring_data_strategy())
    @pytest.mark.asyncio
    async def test_recommendation_estimated_saving_is_numeric(
        self,
        monitoring_data: MonitoringData,
    ) -> None:
        """Each recommendation estimated_saving is a float >= 0."""
        ai_layer = AILayer()
        recommendations = await ai_layer.generate_recommendations(monitoring_data)

        for rec in recommendations:
            assert isinstance(rec.estimated_saving, (int, float))
            assert rec.estimated_saving >= 0.0

    @settings(max_examples=100)
    @given(monitoring_data=monitoring_data_strategy())
    @pytest.mark.asyncio
    async def test_recommendation_resource_id_non_empty(
        self,
        monitoring_data: MonitoringData,
    ) -> None:
        """Each recommendation resource_id is a non-empty string."""
        ai_layer = AILayer()
        recommendations = await ai_layer.generate_recommendations(monitoring_data)

        for rec in recommendations:
            assert isinstance(rec.resource_id, str)
            assert len(rec.resource_id) > 0

    @settings(max_examples=100)
    @given(monitoring_data=monitoring_data_strategy())
    @pytest.mark.asyncio
    async def test_recommendation_provider_non_empty(
        self,
        monitoring_data: MonitoringData,
    ) -> None:
        """Each recommendation provider is a non-empty string."""
        ai_layer = AILayer()
        recommendations = await ai_layer.generate_recommendations(monitoring_data)

        for rec in recommendations:
            assert isinstance(rec.provider, str)
            assert len(rec.provider) > 0

    @settings(max_examples=100)
    @given(monitoring_data=monitoring_data_strategy())
    @pytest.mark.asyncio
    async def test_recommendation_all_invariants_combined(
        self,
        monitoring_data: MonitoringData,
    ) -> None:
        """All recommendation structure invariants hold simultaneously."""
        ai_layer = AILayer()
        recommendations = await ai_layer.generate_recommendations(monitoring_data)

        # Count invariant
        assert 1 <= len(recommendations) <= 50

        for rec in recommendations:
            # Must be a Recommendation instance
            assert isinstance(rec, Recommendation)

            # Action: non-empty string, max 500 chars
            assert isinstance(rec.action, str)
            assert 0 < len(rec.action) <= 500

            # generated_at: valid ISO 8601 timestamp
            assert isinstance(rec.generated_at, str)
            parsed_ts = datetime.fromisoformat(rec.generated_at)
            assert isinstance(parsed_ts, datetime)

            # estimated_saving: numeric value >= 0
            assert isinstance(rec.estimated_saving, (int, float))
            assert rec.estimated_saving >= 0.0

            # resource_id: non-empty string
            assert isinstance(rec.resource_id, str)
            assert len(rec.resource_id) > 0

            # provider: non-empty string
            assert isinstance(rec.provider, str)
            assert len(rec.provider) > 0
