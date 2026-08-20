"""Property-based tests for Monitoring Layer.

Validates: Requirements 7.2, 7.3, 7.4, 7.6, 8.2, 8.3, 8.4, 8.5
"""

import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from backend.models.monitoring import CostComparison, CostEntry, ResourceStatus, TimePeriod
from backend.monitoring.monitoring import EXCHANGE_RATES_TO_USD, MonitoringLayer


# --- Strategies ---

# Supported currencies for normalization testing
currency_strategy = st.sampled_from(list(EXCHANGE_RATES_TO_USD.keys()))

# Provider names
provider_strategy = st.sampled_from(["AWS", "Azure", "GCP"])

# Resource type names
resource_type_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
    min_size=1,
    max_size=30,
)

# Positive cost amounts
cost_amount_strategy = st.floats(min_value=0.01, max_value=100000.0, allow_nan=False, allow_infinity=False)

# ISO date strings within a reasonable range (past 12 months)
def date_strategy():
    """Generate ISO date strings within the last 12 months."""
    today = date.today()
    past_limit = today - timedelta(days=365)
    return st.dates(min_value=past_limit, max_value=today).map(lambda d: d.isoformat())


# Time period strategy: start < end, within valid range
def time_period_strategy():
    """Generate valid TimePeriod objects where start < end."""
    today = date.today()
    past_limit = today - timedelta(days=365)
    return st.tuples(
        st.dates(min_value=past_limit, max_value=today - timedelta(days=1)),
        st.dates(min_value=past_limit + timedelta(days=1), max_value=today),
    ).filter(lambda t: t[0] < t[1]).map(
        lambda t: TimePeriod(start=t[0].isoformat(), end=t[1].isoformat())
    )


# Resource ID strategy
resource_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
    min_size=1,
    max_size=40,
)

# CPU utilization: either a valid float or None
cpu_strategy = st.one_of(
    st.none(),
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
)

# AWS instance states
aws_state_strategy = st.sampled_from(["running", "pending", "stopped", "stopping", "terminated", "shutting-down"])

# Azure VM power states
azure_state_strategy = st.sampled_from(["VM running", "VM deallocated", "VM stopped", "VM deallocating", "VM starting", "VM deleted"])

# GCP instance statuses
gcp_state_strategy = st.sampled_from(["RUNNING", "STAGING", "STOPPED", "SUSPENDED", "TERMINATED"])


# --- Property 13: Cost data normalization ---


class TestProperty13CostDataNormalization:
    """Property 13: Cost data normalization.

    For any cost data retrieved from any combination of AWS, Azure, and GCP providers,
    the Monitoring Layer SHALL normalize all currency values to USD and present results
    in the unified CostEntry format grouped by provider and resource type.

    **Validates: Requirements 7.2**
    """

    @settings(max_examples=100)
    @given(
        aws_amounts=st.lists(
            st.tuples(cost_amount_strategy, currency_strategy, resource_type_strategy),
            min_size=0,
            max_size=5,
        ),
        azure_amounts=st.lists(
            st.tuples(cost_amount_strategy, currency_strategy, resource_type_strategy),
            min_size=0,
            max_size=5,
        ),
        gcp_amounts=st.lists(
            st.tuples(cost_amount_strategy, currency_strategy, resource_type_strategy),
            min_size=0,
            max_size=5,
        ),
    )
    @pytest.mark.asyncio
    async def test_all_costs_normalized_to_usd(
        self,
        aws_amounts: list[tuple[float, str, str]],
        azure_amounts: list[tuple[float, str, str]],
        gcp_amounts: list[tuple[float, str, str]],
    ) -> None:
        """All cost entries returned are normalized to USD currency."""
        # Build mock AWS response
        aws_results = []
        for amount, currency, resource_type in aws_amounts:
            aws_results.append({
                "TimePeriod": {"Start": "2024-01-01", "End": "2024-01-31"},
                "Groups": [{
                    "Keys": [resource_type],
                    "Metrics": {"BlendedCost": {"Amount": str(amount), "Unit": currency}},
                }],
            })

        aws_mock = AsyncMock()
        aws_mock.get_cost_and_usage.return_value = {"ResultsByTime": aws_results}

        # Build mock Azure response
        azure_rows = []
        for amount, currency, resource_type in azure_amounts:
            azure_rows.append([amount, currency, resource_type, "2024-01-01"])

        azure_mock = AsyncMock()
        azure_mock.query.return_value = {"rows": azure_rows}

        # Build mock GCP response
        gcp_costs = []
        for amount, currency, resource_type in gcp_amounts:
            gcp_costs.append({
                "amount": amount,
                "currency": currency,
                "resource_type": resource_type,
            })

        gcp_mock = AsyncMock()
        gcp_mock.query.return_value = {"costs": gcp_costs}

        # Create monitoring layer and fetch costs
        layer = MonitoringLayer(
            aws_cost_client=aws_mock,
            azure_cost_client=azure_mock,
            gcp_billing_client=gcp_mock,
        )

        period = TimePeriod(start="2024-01-01", end="2024-01-31")
        entries = await layer.get_costs(period)

        # Verify all entries are CostEntry with USD currency
        for entry in entries:
            assert isinstance(entry, CostEntry)
            assert entry.currency == "USD"
            assert entry.provider in ("AWS", "Azure", "GCP")
            assert isinstance(entry.cost_amount, float)
            assert isinstance(entry.resource_type, str)
            assert isinstance(entry.period_start, str)
            assert isinstance(entry.period_end, str)

        # Verify correct total number of entries
        expected_count = len(aws_amounts) + len(azure_amounts) + len(gcp_amounts)
        assert len(entries) == expected_count

    @settings(max_examples=100)
    @given(
        amount=cost_amount_strategy,
        currency=currency_strategy,
    )
    @pytest.mark.asyncio
    async def test_normalization_uses_correct_exchange_rate(
        self,
        amount: float,
        currency: str,
    ) -> None:
        """Normalized USD amount matches manual conversion using exchange rates."""
        layer = MonitoringLayer()
        normalized = layer._normalize_to_usd(amount, currency)

        expected_rate = EXCHANGE_RATES_TO_USD[currency]
        if currency == "USD":
            assert normalized == amount
        else:
            expected = round(amount * expected_rate, 6)
            assert normalized == expected


# --- Property 14: Cheapest provider comparison ---


class TestProperty14CheapestProviderComparison:
    """Property 14: Cheapest provider comparison.

    For any set of cost data across providers for a given resource type and time period,
    the Monitoring Layer SHALL correctly identify the provider(s) with the lowest total cost.
    If two or more providers have equal cost, all tied providers SHALL be returned.

    **Validates: Requirements 7.3**
    """

    @settings(max_examples=100)
    @given(
        aws_cost=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        azure_cost=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        gcp_cost=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        resource_type=resource_type_strategy,
    )
    @pytest.mark.asyncio
    async def test_cheapest_provider_identified(
        self,
        aws_cost: float,
        azure_cost: float,
        gcp_cost: float,
        resource_type: str,
    ) -> None:
        """The cheapest provider(s) are correctly identified including ties."""
        # Mock AWS client
        aws_mock = AsyncMock()
        aws_mock.get_cost_and_usage.return_value = {
            "ResultsByTime": [{
                "TimePeriod": {"Start": "2024-01-01", "End": "2024-01-31"},
                "Groups": [{
                    "Keys": [resource_type],
                    "Metrics": {"BlendedCost": {"Amount": str(aws_cost), "Unit": "USD"}},
                }],
            }]
        }

        # Mock Azure client
        azure_mock = AsyncMock()
        azure_mock.query.return_value = {
            "rows": [[azure_cost, "USD", resource_type, "2024-01-01"]]
        }

        # Mock GCP client
        gcp_mock = AsyncMock()
        gcp_mock.query.return_value = {
            "costs": [{"amount": gcp_cost, "currency": "USD", "resource_type": resource_type}]
        }

        layer = MonitoringLayer(
            aws_cost_client=aws_mock,
            azure_cost_client=azure_mock,
            gcp_billing_client=gcp_mock,
        )

        period = TimePeriod(start="2024-01-01", end="2024-01-31")
        result = await layer.compare_costs(resource_type, period)

        # Verify structure
        assert isinstance(result, CostComparison)
        assert result.resource_type == resource_type
        assert result.period == period

        # Manually determine cheapest
        provider_costs = {"AWS": aws_cost, "Azure": azure_cost, "GCP": gcp_cost}
        min_cost = min(provider_costs.values())
        expected_cheapest = sorted(
            p for p, c in provider_costs.items() if c == min_cost
        )

        assert result.cheapest_providers == expected_cheapest

    @settings(max_examples=100)
    @given(
        cost=st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False),
        resource_type=resource_type_strategy,
    )
    @pytest.mark.asyncio
    async def test_tied_providers_all_returned(
        self,
        cost: float,
        resource_type: str,
    ) -> None:
        """When providers have equal cost, all tied providers are returned."""
        # All providers return same cost
        aws_mock = AsyncMock()
        aws_mock.get_cost_and_usage.return_value = {
            "ResultsByTime": [{
                "TimePeriod": {"Start": "2024-01-01", "End": "2024-01-31"},
                "Groups": [{
                    "Keys": [resource_type],
                    "Metrics": {"BlendedCost": {"Amount": str(cost), "Unit": "USD"}},
                }],
            }]
        }

        azure_mock = AsyncMock()
        azure_mock.query.return_value = {
            "rows": [[cost, "USD", resource_type, "2024-01-01"]]
        }

        gcp_mock = AsyncMock()
        gcp_mock.query.return_value = {
            "costs": [{"amount": cost, "currency": "USD", "resource_type": resource_type}]
        }

        layer = MonitoringLayer(
            aws_cost_client=aws_mock,
            azure_cost_client=azure_mock,
            gcp_billing_client=gcp_mock,
        )

        period = TimePeriod(start="2024-01-01", end="2024-01-31")
        result = await layer.compare_costs(resource_type, period)

        # All three providers should be tied
        assert len(result.cheapest_providers) == 3
        assert sorted(result.cheapest_providers) == ["AWS", "Azure", "GCP"]


# --- Property 15: Cost time period filtering ---


class TestProperty15CostTimePeriodFiltering:
    """Property 15: Cost time period filtering.

    For any cost query specifying a time period within the valid range (1 day to 12 months
    in the past), the Monitoring Layer SHALL return only cost entries whose period falls
    within the specified range, excluding all entries outside it.

    **Validates: Requirements 7.4**
    """

    @settings(max_examples=100)
    @given(
        time_period=time_period_strategy(),
    )
    @pytest.mark.asyncio
    async def test_time_period_passed_to_providers(
        self,
        time_period: TimePeriod,
    ) -> None:
        """The requested time period is correctly forwarded to all provider APIs."""
        aws_mock = AsyncMock()
        aws_mock.get_cost_and_usage.return_value = {"ResultsByTime": []}

        azure_mock = AsyncMock()
        azure_mock.query.return_value = {"rows": []}

        gcp_mock = AsyncMock()
        gcp_mock.query.return_value = {"costs": []}

        layer = MonitoringLayer(
            aws_cost_client=aws_mock,
            azure_cost_client=azure_mock,
            gcp_billing_client=gcp_mock,
        )

        await layer.get_costs(time_period)

        # Verify the time period was passed to AWS
        aws_mock.get_cost_and_usage.assert_called_once()
        aws_call_args = aws_mock.get_cost_and_usage.call_args
        assert aws_call_args[1]["time_period"]["Start"] == time_period.start
        assert aws_call_args[1]["time_period"]["End"] == time_period.end

        # Verify the time period was passed to Azure
        azure_mock.query.assert_called_once()
        azure_call_args = azure_mock.query.call_args
        assert azure_call_args[1]["time_period"]["from"] == time_period.start
        assert azure_call_args[1]["time_period"]["to"] == time_period.end

        # Verify the time period was passed to GCP
        gcp_mock.query.assert_called_once()
        gcp_call_args = gcp_mock.query.call_args
        assert gcp_call_args[1]["time_period"]["startDate"] == time_period.start
        assert gcp_call_args[1]["time_period"]["endDate"] == time_period.end

    @settings(max_examples=100)
    @given(
        time_period=time_period_strategy(),
        resource_type=resource_type_strategy,
        cost=cost_amount_strategy,
    )
    @pytest.mark.asyncio
    async def test_returned_entries_have_period_within_range(
        self,
        time_period: TimePeriod,
        resource_type: str,
        cost: float,
    ) -> None:
        """Returned cost entries have period_start and period_end within the query range."""
        # AWS returns data with a period within the queried range
        aws_mock = AsyncMock()
        aws_mock.get_cost_and_usage.return_value = {
            "ResultsByTime": [{
                "TimePeriod": {"Start": time_period.start, "End": time_period.end},
                "Groups": [{
                    "Keys": [resource_type],
                    "Metrics": {"BlendedCost": {"Amount": str(cost), "Unit": "USD"}},
                }],
            }]
        }

        azure_mock = AsyncMock()
        azure_mock.query.return_value = {"rows": []}

        gcp_mock = AsyncMock()
        gcp_mock.query.return_value = {"costs": []}

        layer = MonitoringLayer(
            aws_cost_client=aws_mock,
            azure_cost_client=azure_mock,
            gcp_billing_client=gcp_mock,
        )

        entries = await layer.get_costs(time_period)

        # All returned entries should have dates within the queried range
        for entry in entries:
            assert entry.period_start >= time_period.start
            assert entry.period_end <= time_period.end


# --- Property 16: Partial provider failure resilience ---


class TestProperty16PartialProviderFailureResilience:
    """Property 16: Partial provider failure resilience.

    For any monitoring query (cost or status) where a strict subset of provider APIs fail,
    the Monitoring Layer SHALL return valid data from the remaining responsive providers
    and include an error indicator identifying each failed provider by name.

    **Validates: Requirements 7.6, 8.5**
    """

    @settings(max_examples=100)
    @given(
        failing_providers=st.lists(
            provider_strategy,
            min_size=1,
            max_size=2,
        ).map(lambda ps: list(set(ps))).filter(lambda ps: len(ps) < 3),
    )
    @pytest.mark.asyncio
    async def test_cost_partial_failure_returns_remaining_data(
        self,
        failing_providers: list[str],
    ) -> None:
        """When some providers fail, data from remaining providers is still returned."""
        # Set up mocks - failing providers raise exceptions, others return data
        aws_mock = AsyncMock()
        azure_mock = AsyncMock()
        gcp_mock = AsyncMock()

        if "AWS" in failing_providers:
            aws_mock.get_cost_and_usage.side_effect = RuntimeError("AWS unavailable")
        else:
            aws_mock.get_cost_and_usage.return_value = {
                "ResultsByTime": [{
                    "TimePeriod": {"Start": "2024-01-01", "End": "2024-01-31"},
                    "Groups": [{
                        "Keys": ["compute"],
                        "Metrics": {"BlendedCost": {"Amount": "10.0", "Unit": "USD"}},
                    }],
                }]
            }

        if "Azure" in failing_providers:
            azure_mock.query.side_effect = RuntimeError("Azure unavailable")
        else:
            azure_mock.query.return_value = {
                "rows": [[15.0, "USD", "compute", "2024-01-01"]]
            }

        if "GCP" in failing_providers:
            gcp_mock.query.side_effect = RuntimeError("GCP unavailable")
        else:
            gcp_mock.query.return_value = {
                "costs": [{"amount": 12.0, "currency": "USD", "resource_type": "compute"}]
            }

        layer = MonitoringLayer(
            aws_cost_client=aws_mock,
            azure_cost_client=azure_mock,
            gcp_billing_client=gcp_mock,
        )

        period = TimePeriod(start="2024-01-01", end="2024-01-31")
        entries = await layer.get_costs(period)
        errors = layer.get_last_errors()

        # Verify remaining providers returned data
        successful_providers = [p for p in ["AWS", "Azure", "GCP"] if p not in failing_providers]
        entry_providers = {e.provider for e in entries}
        for provider in successful_providers:
            assert provider in entry_providers

        # Verify error indicators identify failed providers
        error_provider_names = {e["provider"] for e in errors}
        for failed in failing_providers:
            assert failed in error_provider_names

        # Verify errors contain required fields
        for error in errors:
            assert "provider" in error
            assert "error" in error
            assert "error_type" in error

    @settings(max_examples=100)
    @given(
        failing_providers=st.lists(
            provider_strategy,
            min_size=1,
            max_size=2,
        ).map(lambda ps: list(set(ps))).filter(lambda ps: len(ps) < 3),
    )
    @pytest.mark.asyncio
    async def test_status_partial_failure_returns_remaining_data(
        self,
        failing_providers: list[str],
    ) -> None:
        """When some status providers fail, data from remaining providers is returned."""
        # Set up mocks for status monitoring
        aws_ec2_mock = AsyncMock()
        azure_monitor_mock = AsyncMock()
        gcp_monitoring_mock = AsyncMock()

        if "AWS" in failing_providers:
            aws_ec2_mock.describe_instances.side_effect = RuntimeError("AWS EC2 unavailable")
        else:
            aws_ec2_mock.describe_instances.return_value = {
                "Reservations": [{
                    "Instances": [{
                        "InstanceId": "i-abc123",
                        "State": {"Name": "running"},
                    }]
                }]
            }
            aws_ec2_mock.get_cpu_utilization.return_value = {"cpu": 45.5}

        if "Azure" in failing_providers:
            azure_monitor_mock.list_vms.side_effect = RuntimeError("Azure Monitor unavailable")
        else:
            azure_monitor_mock.list_vms.return_value = {
                "vms": [{"name": "vm-1", "power_state": "VM running", "cpu": 60.2}]
            }

        if "GCP" in failing_providers:
            gcp_monitoring_mock.list_instances.side_effect = RuntimeError("GCP Monitoring unavailable")
        else:
            gcp_monitoring_mock.list_instances.return_value = {
                "instances": [{"name": "instance-1", "status": "RUNNING", "cpu": 30.1}]
            }

        layer = MonitoringLayer(
            aws_ec2_client=aws_ec2_mock,
            azure_monitor_client=azure_monitor_mock,
            gcp_monitoring_client=gcp_monitoring_mock,
        )

        statuses = await layer.get_resource_status()
        errors = layer.get_last_errors()

        # Verify remaining providers returned data
        successful_providers = [p for p in ["AWS", "Azure", "GCP"] if p not in failing_providers]
        status_providers = {s.provider for s in statuses}
        for provider in successful_providers:
            assert provider in status_providers

        # Verify error indicators identify failed providers
        error_provider_names = {e["provider"] for e in errors}
        for failed in failing_providers:
            assert failed in error_provider_names


# --- Property 17: Resource status unified structure ---


class TestProperty17ResourceStatusUnifiedStructure:
    """Property 17: Resource status unified structure.

    For any resource status response from any supported cloud provider, the Monitoring Layer
    SHALL return a ResourceStatus object containing: resource identifier (string), provider name
    (one of AWS/Azure/GCP), instance state (one of "running", "stopped", "terminated"), and
    CPU utilization (float 0.0-100.0 rounded to one decimal place, or null if unavailable
    with an availability indicator).

    **Validates: Requirements 8.2, 8.3, 8.4**
    """

    @settings(max_examples=100)
    @given(
        instances=st.lists(
            st.tuples(resource_id_strategy, aws_state_strategy, cpu_strategy),
            min_size=1,
            max_size=5,
        ),
    )
    @pytest.mark.asyncio
    async def test_aws_status_unified_structure(
        self,
        instances: list[tuple[str, str, float | None]],
    ) -> None:
        """AWS resource statuses conform to the unified ResourceStatus structure."""
        aws_instances = []
        for resource_id, state, cpu in instances:
            aws_instances.append({
                "InstanceId": resource_id,
                "State": {"Name": state},
            })

        aws_ec2_mock = AsyncMock()
        aws_ec2_mock.describe_instances.return_value = {
            "Reservations": [{"Instances": aws_instances}]
        }

        # Return CPU for each instance
        cpu_values = {inst[0]: inst[2] for inst in instances}
        async def mock_get_cpu(instance_id):
            return {"cpu": cpu_values.get(instance_id)}
        aws_ec2_mock.get_cpu_utilization.side_effect = mock_get_cpu

        layer = MonitoringLayer(aws_ec2_client=aws_ec2_mock)
        statuses = await layer.get_resource_status(provider="AWS")

        self._verify_resource_status_structure(statuses)

    @settings(max_examples=100)
    @given(
        vms=st.lists(
            st.tuples(resource_id_strategy, azure_state_strategy, cpu_strategy),
            min_size=1,
            max_size=5,
        ),
    )
    @pytest.mark.asyncio
    async def test_azure_status_unified_structure(
        self,
        vms: list[tuple[str, str, float | None]],
    ) -> None:
        """Azure resource statuses conform to the unified ResourceStatus structure."""
        azure_vms = []
        for name, power_state, cpu in vms:
            azure_vms.append({
                "name": name,
                "power_state": power_state,
                "cpu": cpu,
            })

        azure_monitor_mock = AsyncMock()
        azure_monitor_mock.list_vms.return_value = {"vms": azure_vms}

        layer = MonitoringLayer(azure_monitor_client=azure_monitor_mock)
        statuses = await layer.get_resource_status(provider="Azure")

        self._verify_resource_status_structure(statuses)

    @settings(max_examples=100)
    @given(
        instances=st.lists(
            st.tuples(resource_id_strategy, gcp_state_strategy, cpu_strategy),
            min_size=1,
            max_size=5,
        ),
    )
    @pytest.mark.asyncio
    async def test_gcp_status_unified_structure(
        self,
        instances: list[tuple[str, str, float | None]],
    ) -> None:
        """GCP resource statuses conform to the unified ResourceStatus structure."""
        gcp_instances = []
        for name, status, cpu in instances:
            gcp_instances.append({
                "name": name,
                "status": status,
                "cpu": cpu,
            })

        gcp_monitoring_mock = AsyncMock()
        gcp_monitoring_mock.list_instances.return_value = {"instances": gcp_instances}

        layer = MonitoringLayer(gcp_monitoring_client=gcp_monitoring_mock)
        statuses = await layer.get_resource_status(provider="GCP")

        self._verify_resource_status_structure(statuses)

    def _verify_resource_status_structure(self, statuses: list[ResourceStatus]) -> None:
        """Verify all ResourceStatus objects conform to the unified structure."""
        valid_states = {"running", "stopped", "terminated"}
        valid_providers = {"AWS", "Azure", "GCP"}

        for status in statuses:
            # Must be a ResourceStatus instance
            assert isinstance(status, ResourceStatus)

            # resource_id must be a string
            assert isinstance(status.resource_id, str)

            # provider must be one of the supported providers
            assert status.provider in valid_providers

            # state must be one of the normalized states
            assert status.state in valid_states

            # cpu_available must be a boolean
            assert isinstance(status.cpu_available, bool)

            # CPU utilization constraints
            if status.cpu_utilization is not None:
                # Must be float between 0.0 and 100.0
                assert isinstance(status.cpu_utilization, float)
                assert 0.0 <= status.cpu_utilization <= 100.0
                # Must be rounded to 1 decimal place
                assert status.cpu_utilization == round(status.cpu_utilization, 1)
                # If CPU has a value, cpu_available should be True
                assert status.cpu_available is True
            else:
                # If CPU is None, cpu_available should be False
                assert status.cpu_available is False
