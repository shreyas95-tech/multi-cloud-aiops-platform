"""Unit tests for MonitoringLayer.

Tests cover:
- Cost retrieval with mocked cloud APIs (all providers returning data)
- Default time period (current month: 1st to today)
- Cost comparison with tied providers
- Resource status CPU normalization (round to 1 decimal, clamp 0-100)
- Resource status state normalization (AWS states to running/stopped/terminated)
- Partial failure handling (one provider fails, others still return)
- All providers fail (empty list, 3 errors in get_last_errors)

Requirements: 7.1, 7.5, 7.6, 8.1, 8.5
"""

import pytest
from datetime import date
from unittest.mock import AsyncMock

from backend.monitoring.monitoring import MonitoringLayer
from backend.models.monitoring import TimePeriod


@pytest.fixture
def aws_cost_client():
    """Mocked AWS Cost Explorer client."""
    return AsyncMock()


@pytest.fixture
def azure_cost_client():
    """Mocked Azure Cost Management client."""
    return AsyncMock()


@pytest.fixture
def gcp_billing_client():
    """Mocked GCP Billing client."""
    return AsyncMock()


@pytest.fixture
def aws_ec2_client():
    """Mocked AWS EC2/CloudWatch client for status monitoring."""
    return AsyncMock()


@pytest.fixture
def azure_monitor_client():
    """Mocked Azure Monitor client for status monitoring."""
    return AsyncMock()


@pytest.fixture
def gcp_monitoring_client():
    """Mocked GCP Monitoring client for status monitoring."""
    return AsyncMock()


@pytest.fixture
def monitoring_layer(
    aws_cost_client,
    azure_cost_client,
    gcp_billing_client,
    aws_ec2_client,
    azure_monitor_client,
    gcp_monitoring_client,
):
    """Create a MonitoringLayer with all mocked clients."""
    return MonitoringLayer(
        aws_cost_client=aws_cost_client,
        azure_cost_client=azure_cost_client,
        gcp_billing_client=gcp_billing_client,
        aws_ec2_client=aws_ec2_client,
        azure_monitor_client=azure_monitor_client,
        gcp_monitoring_client=gcp_monitoring_client,
    )


class TestGetCosts:
    """Tests for MonitoringLayer.get_costs with all providers returning data."""

    @pytest.mark.asyncio
    async def test_get_costs_all_providers(
        self, monitoring_layer, aws_cost_client, azure_cost_client, gcp_billing_client
    ):
        """All providers return cost data, results are combined and normalized to USD."""
        time_period = TimePeriod(start="2024-01-01", end="2024-01-31")

        aws_cost_client.get_cost_and_usage.return_value = {
            "ResultsByTime": [
                {
                    "TimePeriod": {"Start": "2024-01-01", "End": "2024-01-31"},
                    "Groups": [
                        {
                            "Keys": ["EC2"],
                            "Metrics": {
                                "BlendedCost": {"Amount": "150.00", "Unit": "USD"}
                            },
                        }
                    ],
                }
            ]
        }

        azure_cost_client.query.return_value = {
            "rows": [
                [100.0, "USD", "VirtualMachines", "2024-01-15"],
            ]
        }

        gcp_billing_client.query.return_value = {
            "costs": [
                {"amount": 80.0, "currency": "USD", "resource_type": "ComputeEngine"},
            ]
        }

        entries = await monitoring_layer.get_costs(time_period)

        assert len(entries) == 3
        # AWS entry
        aws_entry = next(e for e in entries if e.provider == "AWS")
        assert aws_entry.resource_type == "EC2"
        assert aws_entry.cost_amount == 150.0
        assert aws_entry.currency == "USD"
        assert aws_entry.period_start == "2024-01-01"
        assert aws_entry.period_end == "2024-01-31"

        # Azure entry
        azure_entry = next(e for e in entries if e.provider == "Azure")
        assert azure_entry.resource_type == "VirtualMachines"
        assert azure_entry.cost_amount == 100.0
        assert azure_entry.currency == "USD"

        # GCP entry
        gcp_entry = next(e for e in entries if e.provider == "GCP")
        assert gcp_entry.resource_type == "ComputeEngine"
        assert gcp_entry.cost_amount == 80.0
        assert gcp_entry.currency == "USD"

        # No errors
        assert monitoring_layer.get_last_errors() == []


class TestDefaultTimePeriod:
    """Tests for the default time period (current calendar month)."""

    @pytest.mark.asyncio
    async def test_default_time_period_is_current_month(
        self, monitoring_layer, aws_cost_client, azure_cost_client, gcp_billing_client
    ):
        """When no time_period is specified, uses 1st of month to today."""
        # Set up clients to return empty data so we can inspect the calls
        aws_cost_client.get_cost_and_usage.return_value = {"ResultsByTime": []}
        azure_cost_client.query.return_value = {"rows": []}
        gcp_billing_client.query.return_value = {"costs": []}

        await monitoring_layer.get_costs()  # No time_period argument

        today = date.today()
        first_of_month = today.replace(day=1)

        # Verify AWS was called with the default period
        aws_cost_client.get_cost_and_usage.assert_called_once_with(
            time_period={"Start": first_of_month.isoformat(), "End": today.isoformat()}
        )

        # Verify Azure was called with the default period
        azure_cost_client.query.assert_called_once_with(
            time_period={"from": first_of_month.isoformat(), "to": today.isoformat()}
        )

        # Verify GCP was called with the default period
        gcp_billing_client.query.assert_called_once_with(
            time_period={
                "startDate": first_of_month.isoformat(),
                "endDate": today.isoformat(),
            }
        )


class TestCompareCostsTied:
    """Tests for cost comparison with tied providers."""

    @pytest.mark.asyncio
    async def test_compare_costs_tied_providers(
        self, monitoring_layer, aws_cost_client, azure_cost_client, gcp_billing_client
    ):
        """When two providers have equal cost, both appear in cheapest_providers."""
        time_period = TimePeriod(start="2024-01-01", end="2024-01-31")

        # AWS and Azure both have 50.0 for EC2/VM, GCP has 80.0
        aws_cost_client.get_cost_and_usage.return_value = {
            "ResultsByTime": [
                {
                    "TimePeriod": {"Start": "2024-01-01", "End": "2024-01-31"},
                    "Groups": [
                        {
                            "Keys": ["compute"],
                            "Metrics": {
                                "BlendedCost": {"Amount": "50.0", "Unit": "USD"}
                            },
                        }
                    ],
                }
            ]
        }

        azure_cost_client.query.return_value = {
            "rows": [
                [50.0, "USD", "compute", "2024-01-15"],
            ]
        }

        gcp_billing_client.query.return_value = {
            "costs": [
                {"amount": 80.0, "currency": "USD", "resource_type": "compute"},
            ]
        }

        comparison = await monitoring_layer.compare_costs("compute", time_period)

        assert comparison.resource_type == "compute"
        assert len(comparison.cheapest_providers) == 2
        assert "AWS" in comparison.cheapest_providers
        assert "Azure" in comparison.cheapest_providers
        assert "GCP" not in comparison.cheapest_providers
        assert len(comparison.breakdown) == 3


class TestResourceStatusCpuNormalization:
    """Tests for CPU utilization normalization (round to 1 decimal, clamp 0-100)."""

    @pytest.mark.asyncio
    async def test_cpu_rounded_to_one_decimal(self, monitoring_layer, aws_ec2_client):
        """CPU utilization is rounded to 1 decimal place."""
        aws_ec2_client.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {"InstanceId": "i-abc123", "State": {"Name": "running"}}
                    ]
                }
            ]
        }
        aws_ec2_client.get_cpu_utilization.return_value = {"cpu": 45.678}

        statuses = await monitoring_layer.get_resource_status("AWS")

        assert len(statuses) == 1
        assert statuses[0].cpu_utilization == 45.7
        assert statuses[0].cpu_available is True

    @pytest.mark.asyncio
    async def test_cpu_clamped_above_100(self, monitoring_layer, aws_ec2_client):
        """CPU values above 100 are clamped to 100.0."""
        aws_ec2_client.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {"InstanceId": "i-abc123", "State": {"Name": "running"}}
                    ]
                }
            ]
        }
        aws_ec2_client.get_cpu_utilization.return_value = {"cpu": 150.5}

        statuses = await monitoring_layer.get_resource_status("AWS")

        assert statuses[0].cpu_utilization == 100.0

    @pytest.mark.asyncio
    async def test_cpu_clamped_below_zero(self, monitoring_layer, aws_ec2_client):
        """CPU values below 0 are clamped to 0.0."""
        aws_ec2_client.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {"InstanceId": "i-abc123", "State": {"Name": "running"}}
                    ]
                }
            ]
        }
        aws_ec2_client.get_cpu_utilization.return_value = {"cpu": -5.0}

        statuses = await monitoring_layer.get_resource_status("AWS")

        assert statuses[0].cpu_utilization == 0.0

    @pytest.mark.asyncio
    async def test_cpu_none_returns_unavailable(self, monitoring_layer, aws_ec2_client):
        """When CPU is None, cpu_utilization is None and cpu_available is False."""
        aws_ec2_client.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {"InstanceId": "i-abc123", "State": {"Name": "running"}}
                    ]
                }
            ]
        }
        aws_ec2_client.get_cpu_utilization.return_value = {"cpu": None}

        statuses = await monitoring_layer.get_resource_status("AWS")

        assert statuses[0].cpu_utilization is None
        assert statuses[0].cpu_available is False


class TestResourceStatusStateNormalization:
    """Tests for AWS state normalization to running/stopped/terminated."""

    @pytest.mark.asyncio
    async def test_aws_running_states(self, monitoring_layer, aws_ec2_client):
        """AWS 'running' and 'pending' map to 'running'."""
        aws_ec2_client.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {"InstanceId": "i-run1", "State": {"Name": "running"}},
                        {"InstanceId": "i-pend1", "State": {"Name": "pending"}},
                    ]
                }
            ]
        }
        aws_ec2_client.get_cpu_utilization.return_value = {"cpu": None}

        statuses = await monitoring_layer.get_resource_status("AWS")

        states = {s.resource_id: s.state for s in statuses}
        assert states["i-run1"] == "running"
        assert states["i-pend1"] == "running"

    @pytest.mark.asyncio
    async def test_aws_stopped_states(self, monitoring_layer, aws_ec2_client):
        """AWS 'stopped' and 'stopping' map to 'stopped'."""
        aws_ec2_client.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {"InstanceId": "i-stop1", "State": {"Name": "stopped"}},
                        {"InstanceId": "i-stopping1", "State": {"Name": "stopping"}},
                    ]
                }
            ]
        }
        aws_ec2_client.get_cpu_utilization.return_value = {"cpu": None}

        statuses = await monitoring_layer.get_resource_status("AWS")

        states = {s.resource_id: s.state for s in statuses}
        assert states["i-stop1"] == "stopped"
        assert states["i-stopping1"] == "stopped"

    @pytest.mark.asyncio
    async def test_aws_terminated_states(self, monitoring_layer, aws_ec2_client):
        """AWS 'terminated' and 'shutting-down' map to 'terminated'."""
        aws_ec2_client.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {"InstanceId": "i-term1", "State": {"Name": "terminated"}},
                        {
                            "InstanceId": "i-shut1",
                            "State": {"Name": "shutting-down"},
                        },
                    ]
                }
            ]
        }
        aws_ec2_client.get_cpu_utilization.return_value = {"cpu": None}

        statuses = await monitoring_layer.get_resource_status("AWS")

        states = {s.resource_id: s.state for s in statuses}
        assert states["i-term1"] == "terminated"
        assert states["i-shut1"] == "terminated"


class TestPartialFailureHandling:
    """Tests for partial failure: one provider fails, others still return."""

    @pytest.mark.asyncio
    async def test_one_cost_provider_fails(
        self, monitoring_layer, aws_cost_client, azure_cost_client, gcp_billing_client
    ):
        """If one provider fails, others still return data and error is recorded."""
        time_period = TimePeriod(start="2024-01-01", end="2024-01-31")

        # AWS fails
        aws_cost_client.get_cost_and_usage.side_effect = RuntimeError(
            "AWS API unavailable"
        )

        # Azure and GCP succeed
        azure_cost_client.query.return_value = {
            "rows": [[75.0, "USD", "VirtualMachines", "2024-01-10"]]
        }
        gcp_billing_client.query.return_value = {
            "costs": [
                {"amount": 60.0, "currency": "USD", "resource_type": "ComputeEngine"}
            ]
        }

        entries = await monitoring_layer.get_costs(time_period)

        # Data from Azure and GCP still returned
        assert len(entries) == 2
        providers = {e.provider for e in entries}
        assert "Azure" in providers
        assert "GCP" in providers
        assert "AWS" not in providers

        # Error recorded for AWS
        errors = monitoring_layer.get_last_errors()
        assert len(errors) == 1
        assert errors[0]["provider"] == "AWS"
        assert "AWS API unavailable" in errors[0]["error"]

    @pytest.mark.asyncio
    async def test_one_status_provider_fails(
        self, monitoring_layer, aws_ec2_client, azure_monitor_client, gcp_monitoring_client
    ):
        """If one status provider fails, others still return data."""
        # Azure fails
        azure_monitor_client.list_vms.side_effect = RuntimeError(
            "Azure Monitor timeout"
        )

        # AWS succeeds
        aws_ec2_client.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {"InstanceId": "i-abc123", "State": {"Name": "running"}}
                    ]
                }
            ]
        }
        aws_ec2_client.get_cpu_utilization.return_value = {"cpu": 30.0}

        # GCP succeeds
        gcp_monitoring_client.list_instances.return_value = {
            "instances": [
                {"name": "gcp-vm-1", "status": "RUNNING", "cpu": 55.0}
            ]
        }

        statuses = await monitoring_layer.get_resource_status()

        # Data from AWS and GCP returned
        assert len(statuses) == 2
        providers = {s.provider for s in statuses}
        assert "AWS" in providers
        assert "GCP" in providers
        assert "Azure" not in providers

        # Error recorded for Azure
        errors = monitoring_layer.get_last_errors()
        assert len(errors) == 1
        assert errors[0]["provider"] == "Azure"

    @pytest.mark.asyncio
    async def test_all_cost_providers_fail(
        self, monitoring_layer, aws_cost_client, azure_cost_client, gcp_billing_client
    ):
        """When all providers fail, returns empty list with 3 errors."""
        time_period = TimePeriod(start="2024-01-01", end="2024-01-31")

        aws_cost_client.get_cost_and_usage.side_effect = RuntimeError("AWS down")
        azure_cost_client.query.side_effect = RuntimeError("Azure down")
        gcp_billing_client.query.side_effect = RuntimeError("GCP down")

        entries = await monitoring_layer.get_costs(time_period)

        assert entries == []

        errors = monitoring_layer.get_last_errors()
        assert len(errors) == 3
        error_providers = {e["provider"] for e in errors}
        assert error_providers == {"AWS", "Azure", "GCP"}
