"""Integration tests for the monitoring flow: request -> retrieve -> normalize -> respond.

Tests cost retrieval, status retrieval, and partial failure handling
with mocked cloud provider clients.

Requirements: 7.6, 8.5, 10.6, 10.7
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.monitoring.monitoring import MonitoringLayer


@pytest.fixture
def client():
    """Create a TestClient for the FastAPI app."""
    return TestClient(app)


def _make_monitoring_layer_with_mock_costs():
    """Create a MonitoringLayer with mocked cost clients returning valid data."""
    aws_cost_client = AsyncMock()
    aws_cost_client.get_cost_and_usage = AsyncMock(return_value={
        "ResultsByTime": [
            {
                "TimePeriod": {"Start": "2024-01-01", "End": "2024-01-31"},
                "Groups": [
                    {
                        "Keys": ["EC2"],
                        "Metrics": {"BlendedCost": {"Amount": "150.00", "Unit": "USD"}},
                    }
                ],
            }
        ]
    })

    azure_cost_client = AsyncMock()
    azure_cost_client.query = AsyncMock(return_value={
        "rows": [
            [200.0, "USD", "VirtualMachines", "2024-01-15"],
            [50.0, "USD", "Storage", "2024-01-15"],
        ]
    })

    gcp_billing_client = AsyncMock()
    gcp_billing_client.query = AsyncMock(return_value={
        "costs": [
            {"amount": 120.0, "currency": "USD", "resource_type": "ComputeEngine"},
        ]
    })

    return MonitoringLayer(
        aws_cost_client=aws_cost_client,
        azure_cost_client=azure_cost_client,
        gcp_billing_client=gcp_billing_client,
    )


def _make_monitoring_layer_with_mock_status():
    """Create a MonitoringLayer with mocked status clients."""
    aws_ec2_client = AsyncMock()
    aws_ec2_client.describe_instances = AsyncMock(return_value={
        "Reservations": [
            {
                "Instances": [
                    {
                        "InstanceId": "i-abc123",
                        "State": {"Name": "running"},
                    },
                    {
                        "InstanceId": "i-def456",
                        "State": {"Name": "stopped"},
                    },
                ]
            }
        ]
    })
    aws_ec2_client.get_cpu_utilization = AsyncMock(return_value={"cpu": 45.7})

    azure_monitor_client = AsyncMock()
    azure_monitor_client.list_vms = AsyncMock(return_value={
        "vms": [
            {"name": "web-vm-1", "power_state": "VM running", "cpu": 72.3},
            {"name": "db-vm-1", "power_state": "VM deallocated", "cpu": None},
        ]
    })

    gcp_monitoring_client = AsyncMock()
    gcp_monitoring_client.list_instances = AsyncMock(return_value={
        "instances": [
            {"name": "gcp-instance-1", "status": "RUNNING", "cpu": 30.5},
        ]
    })

    return MonitoringLayer(
        aws_ec2_client=aws_ec2_client,
        azure_monitor_client=azure_monitor_client,
        gcp_monitoring_client=gcp_monitoring_client,
    )


class TestCostRetrieval:
    """Test cost retrieval flow: mock cost clients -> GET /api/costs -> normalized USD response."""

    def test_get_costs_returns_normalized_usd(self, client):
        """Mock cost clients, send GET /api/costs, verify normalized USD response."""
        monitoring = _make_monitoring_layer_with_mock_costs()

        with patch("backend.api.routes.costs.monitoring_layer", new=monitoring):
            response = client.get("/api/costs")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["error"] is None

        data = body["data"]
        assert len(data) == 4  # 1 AWS + 2 Azure + 1 GCP

        # All entries should have currency = "USD"
        for entry in data:
            assert entry["currency"] == "USD"

        # Check AWS entry
        aws_entries = [e for e in data if e["provider"] == "AWS"]
        assert len(aws_entries) == 1
        assert aws_entries[0]["cost_amount"] == 150.0
        assert aws_entries[0]["resource_type"] == "EC2"

        # Check Azure entries
        azure_entries = [e for e in data if e["provider"] == "Azure"]
        assert len(azure_entries) == 2

        # Check GCP entry
        gcp_entries = [e for e in data if e["provider"] == "GCP"]
        assert len(gcp_entries) == 1
        assert gcp_entries[0]["resource_type"] == "ComputeEngine"

    def test_get_costs_with_time_period(self, client):
        """Test cost retrieval with time period query params."""
        monitoring = _make_monitoring_layer_with_mock_costs()

        with patch("backend.api.routes.costs.monitoring_layer", new=monitoring):
            response = client.get("/api/costs?start=2024-01-01&end=2024-01-31")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert len(body["data"]) > 0


class TestStatusRetrieval:
    """Test status retrieval flow: mock status clients -> GET /api/status -> normalized states."""

    def test_get_status_returns_normalized_states(self, client):
        """Mock status clients, send GET /api/status, verify normalized states."""
        monitoring = _make_monitoring_layer_with_mock_status()

        with patch("backend.api.routes.status.monitoring_layer", new=monitoring):
            response = client.get("/api/status")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["error"] is None

        data = body["data"]
        # 2 AWS + 2 Azure + 1 GCP = 5 resources
        assert len(data) == 5

        # Check that states are normalized
        valid_states = {"running", "stopped", "terminated"}
        for resource in data:
            assert resource["state"] in valid_states
            assert resource["provider"] in {"AWS", "Azure", "GCP"}
            assert "resource_id" in resource
            assert "cpu_available" in resource

        # Check specific AWS resource
        aws_running = [r for r in data if r["resource_id"] == "i-abc123"]
        assert len(aws_running) == 1
        assert aws_running[0]["state"] == "running"
        assert aws_running[0]["cpu_utilization"] == 45.7

        # Check Azure deallocated -> stopped
        azure_stopped = [r for r in data if r["resource_id"] == "db-vm-1"]
        assert len(azure_stopped) == 1
        assert azure_stopped[0]["state"] == "stopped"
        assert azure_stopped[0]["cpu_utilization"] is None
        assert azure_stopped[0]["cpu_available"] is False

    def test_get_status_with_provider_filter(self, client):
        """Test status retrieval filtered by provider."""
        monitoring = _make_monitoring_layer_with_mock_status()

        with patch("backend.api.routes.status.monitoring_layer", new=monitoring):
            response = client.get("/api/status?provider=GCP")

        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        assert len(data) == 1
        assert data[0]["provider"] == "GCP"
        assert data[0]["resource_id"] == "gcp-instance-1"
        assert data[0]["state"] == "running"


class TestPartialFailure:
    """Test partial failure scenarios where one provider fails but others succeed."""

    def test_cost_partial_failure_returns_available_data(self, client):
        """Mock one cost provider to fail, verify remaining data is returned."""
        # AWS fails, Azure and GCP succeed
        aws_cost_client = AsyncMock()
        aws_cost_client.get_cost_and_usage = AsyncMock(
            side_effect=RuntimeError("AWS Cost Explorer unavailable")
        )

        azure_cost_client = AsyncMock()
        azure_cost_client.query = AsyncMock(return_value={
            "rows": [[100.0, "USD", "VirtualMachines", "2024-01-15"]]
        })

        gcp_billing_client = AsyncMock()
        gcp_billing_client.query = AsyncMock(return_value={
            "costs": [{"amount": 80.0, "currency": "USD", "resource_type": "ComputeEngine"}]
        })

        monitoring = MonitoringLayer(
            aws_cost_client=aws_cost_client,
            azure_cost_client=azure_cost_client,
            gcp_billing_client=gcp_billing_client,
        )

        with patch("backend.api.routes.costs.monitoring_layer", new=monitoring):
            response = client.get("/api/costs")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"

        data = body["data"]
        # Only Azure + GCP should be present (AWS failed)
        providers = {e["provider"] for e in data}
        assert "AWS" not in providers
        assert "Azure" in providers
        assert "GCP" in providers

        # Check error indicators are stored on the monitoring layer
        errors = monitoring.get_last_errors()
        assert len(errors) == 1
        assert errors[0]["provider"] == "AWS"

    def test_status_partial_failure_returns_available_data(self, client):
        """Mock one status provider to fail, verify remaining data is returned."""
        # Azure fails, AWS and GCP succeed
        aws_ec2_client = AsyncMock()
        aws_ec2_client.describe_instances = AsyncMock(return_value={
            "Reservations": [
                {"Instances": [{"InstanceId": "i-test1", "State": {"Name": "running"}}]}
            ]
        })
        aws_ec2_client.get_cpu_utilization = AsyncMock(return_value={"cpu": 25.0})

        azure_monitor_client = AsyncMock()
        azure_monitor_client.list_vms = AsyncMock(
            side_effect=RuntimeError("Azure Monitor API timeout")
        )

        gcp_monitoring_client = AsyncMock()
        gcp_monitoring_client.list_instances = AsyncMock(return_value={
            "instances": [{"name": "gcp-vm-1", "status": "RUNNING", "cpu": 50.0}]
        })

        monitoring = MonitoringLayer(
            aws_ec2_client=aws_ec2_client,
            azure_monitor_client=azure_monitor_client,
            gcp_monitoring_client=gcp_monitoring_client,
        )

        with patch("backend.api.routes.status.monitoring_layer", new=monitoring):
            response = client.get("/api/status")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"

        data = body["data"]
        # Only AWS + GCP should be present (Azure failed)
        providers = {r["provider"] for r in data}
        assert "Azure" not in providers
        assert "AWS" in providers
        assert "GCP" in providers

        # Check error indicators
        errors = monitoring.get_last_errors()
        assert len(errors) == 1
        assert errors[0]["provider"] == "Azure"

    def test_all_cost_providers_fail(self, client):
        """When all cost providers fail, should return empty data but no crash."""
        aws_cost_client = AsyncMock()
        aws_cost_client.get_cost_and_usage = AsyncMock(side_effect=RuntimeError("AWS down"))

        azure_cost_client = AsyncMock()
        azure_cost_client.query = AsyncMock(side_effect=RuntimeError("Azure down"))

        gcp_billing_client = AsyncMock()
        gcp_billing_client.query = AsyncMock(side_effect=RuntimeError("GCP down"))

        monitoring = MonitoringLayer(
            aws_cost_client=aws_cost_client,
            azure_cost_client=azure_cost_client,
            gcp_billing_client=gcp_billing_client,
        )

        with patch("backend.api.routes.costs.monitoring_layer", new=monitoring):
            response = client.get("/api/costs")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["data"] == []

        # All three providers should have errors
        errors = monitoring.get_last_errors()
        assert len(errors) == 3
