"""Unit tests for the FastAPI API Layer.

Tests each endpoint with valid requests, 422 for invalid inputs,
502 for downstream failures, 404 for non-existent endpoints, and CORS headers.

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.7, 10.8, 10.9
"""

from unittest.mock import AsyncMock, patch
from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.models.intent import IntentJSON
from backend.models.execution import ExecutionResult
from backend.models.monitoring import CostEntry, ResourceStatus, TimePeriod
from backend.models.recommendation import Recommendation


@pytest.fixture
def client():
    """Create a TestClient for the FastAPI app."""
    return TestClient(app)


# --- 1. GET / health check ---


class TestHealthCheck:
    """Tests for the root health-check endpoint."""

    def test_health_check_returns_200(self, client):
        """GET / returns 200 with envelope {status: 'success', data: {service: 'multi-cloud-aiops'}}."""
        response = client.get("/")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["data"] == {"service": "multi-cloud-aiops"}
        assert body["error"] is None


# --- 2-5. POST /api/query ---


class TestPostQuery:
    """Tests for the POST /api/query endpoint."""

    @patch("backend.api.routes.query._orchestrator")
    @patch("backend.api.routes.query._ai_layer")
    def test_valid_query_returns_200(self, mock_ai_layer, mock_orchestrator, client):
        """POST /api/query with valid body returns 200 with execution result."""
        mock_intent = IntentJSON(
            intent="start instance on AWS",
            cloud="AWS",
            action="start_instance",
            conditions="instance_id=i-abc123",
        )
        mock_result = ExecutionResult(
            success=True,
            provider="AWS",
            resource_id="i-abc123",
            action="start_instance",
            state="running",
            error_code=None,
            error_message=None,
            metadata={},
        )
        mock_ai_layer.parse_intent = AsyncMock(return_value=mock_intent)
        mock_orchestrator.route = AsyncMock(return_value=mock_result)

        response = client.post("/api/query", json={"query": "start my AWS instance i-abc123"})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["data"]["provider"] == "AWS"
        assert body["data"]["success"] is True

    def test_empty_query_returns_422(self, client):
        """POST /api/query with empty query returns 422 with field='query'."""
        response = client.post("/api/query", json={"query": ""})
        assert response.status_code == 422
        body = response.json()
        assert body["status"] == "error"
        assert body["error"]["field"] == "query"

    def test_whitespace_only_query_returns_422(self, client):
        """POST /api/query with whitespace-only query returns 422 with field='query'."""
        response = client.post("/api/query", json={"query": "   \t\n  "})
        assert response.status_code == 422
        body = response.json()
        assert body["status"] == "error"
        assert body["error"]["field"] == "query"

    def test_too_long_query_returns_422(self, client):
        """POST /api/query with query > 2000 chars returns 422."""
        long_query = "a" * 2001
        response = client.post("/api/query", json={"query": long_query})
        assert response.status_code == 422
        body = response.json()
        assert body["status"] == "error"
        # The error should reference the 'query' field
        assert "query" in body["error"].get("field", "").lower() or "query" in str(body["error"])


# --- 6-7. GET /api/costs ---


class TestGetCosts:
    """Tests for the GET /api/costs endpoint."""

    @patch("backend.api.routes.costs.monitoring_layer")
    def test_costs_without_params_returns_200(self, mock_monitoring, client):
        """GET /api/costs without params returns 200 with envelope."""
        mock_cost = CostEntry(
            provider="AWS",
            resource_type="EC2",
            cost_amount=150.0,
            currency="USD",
            period_start="2024-01-01",
            period_end="2024-01-31",
        )
        mock_monitoring.get_costs = AsyncMock(return_value=[mock_cost])

        response = client.get("/api/costs")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert len(body["data"]) == 1
        assert body["data"][0]["provider"] == "AWS"

    def test_costs_with_start_only_returns_422(self, client):
        """GET /api/costs with start only returns 422 with field='end'."""
        response = client.get("/api/costs?start=2024-01-01")
        assert response.status_code == 422
        body = response.json()
        assert body["status"] == "error"
        assert body["error"]["field"] == "end"


# --- 8. GET /api/status ---


class TestGetStatus:
    """Tests for the GET /api/status endpoint."""

    @patch("backend.api.routes.status.monitoring_layer")
    def test_status_returns_200(self, mock_monitoring, client):
        """GET /api/status returns 200 with resource statuses."""
        mock_status = ResourceStatus(
            resource_id="i-abc123",
            provider="AWS",
            state="running",
            cpu_utilization=45.3,
            cpu_available=True,
        )
        mock_monitoring.get_resource_status = AsyncMock(return_value=[mock_status])

        response = client.get("/api/status")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert len(body["data"]) == 1
        assert body["data"][0]["state"] == "running"


# --- 9. GET /api/recommendations ---


class TestGetRecommendations:
    """Tests for the GET /api/recommendations endpoint."""

    @patch("backend.api.routes.recommendations._ai_layer")
    @patch("backend.api.routes.recommendations._monitoring_layer")
    def test_recommendations_returns_200(self, mock_monitoring, mock_ai_layer, client):
        """GET /api/recommendations returns 200 when services are available."""
        mock_cost = CostEntry(
            provider="AWS",
            resource_type="EC2",
            cost_amount=150.0,
            currency="USD",
            period_start="2024-01-01",
            period_end="2024-01-31",
        )
        mock_status = ResourceStatus(
            resource_id="i-abc123",
            provider="AWS",
            state="running",
            cpu_utilization=5.0,
            cpu_available=True,
        )
        mock_recommendation = Recommendation(
            action="Consider stopping idle instance i-abc123",
            resource_id="i-abc123",
            provider="AWS",
            estimated_saving=50.0,
            generated_at="2024-01-15T10:00:00+00:00",
        )

        mock_monitoring.get_costs = AsyncMock(return_value=[mock_cost])
        mock_monitoring.get_resource_status = AsyncMock(return_value=[mock_status])
        mock_monitoring._default_time_period = lambda: TimePeriod(start="2024-01-01", end="2024-01-31")
        mock_ai_layer.generate_recommendations = AsyncMock(return_value=[mock_recommendation])

        response = client.get("/api/recommendations")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert len(body["data"]) == 1
        assert body["data"][0]["provider"] == "AWS"

    @patch("backend.api.routes.recommendations._ai_layer")
    @patch("backend.api.routes.recommendations._monitoring_layer")
    def test_recommendations_downstream_failure_returns_502(self, mock_monitoring, mock_ai_layer, client):
        """GET /api/recommendations returns 502 when monitoring layer fails."""
        mock_monitoring.get_costs = AsyncMock(side_effect=Exception("Service unavailable"))

        response = client.get("/api/recommendations")
        assert response.status_code == 502
        body = response.json()
        assert body["status"] == "error"
        assert body["error"]["service"] == "monitoring_layer"


# --- 10. 404 for non-existent endpoints ---


class TestNotFound:
    """Tests for 404 on non-existent endpoints."""

    def test_nonexistent_endpoint_returns_404(self, client):
        """GET /nonexistent returns 404 with envelope structure."""
        response = client.get("/nonexistent")
        assert response.status_code == 404
        body = response.json()
        assert body["status"] == "error"
        assert body["data"] is None
        assert body["error"] is not None
        assert "message" in body["error"]


# --- 11. CORS headers ---


class TestCORS:
    """Tests for CORS header presence in responses."""

    def test_cors_headers_present(self, client):
        """Verify access-control-allow-origin header in response to preflight."""
        response = client.options(
            "/api/query",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert "access-control-allow-origin" in response.headers


# --- 12. Downstream failure (AI Layer parse_intent raises) ---


class TestDownstreamFailure:
    """Tests for 502 responses when downstream services fail."""

    @patch("backend.api.routes.query._orchestrator")
    @patch("backend.api.routes.query._ai_layer")
    def test_ai_layer_failure_returns_502(self, mock_ai_layer, mock_orchestrator, client):
        """When AILayer.parse_intent raises, POST /api/query returns 502 with service='ai_layer'."""
        mock_ai_layer.parse_intent = AsyncMock(side_effect=Exception("LLM service unavailable"))

        response = client.post("/api/query", json={"query": "start my AWS instance i-abc123"})
        assert response.status_code == 502
        body = response.json()
        assert body["status"] == "error"
        assert body["error"]["service"] == "ai_layer"

    @patch("backend.api.routes.query._orchestrator")
    @patch("backend.api.routes.query._ai_layer")
    def test_orchestrator_failure_returns_502(self, mock_ai_layer, mock_orchestrator, client):
        """When Orchestrator.route raises, POST /api/query returns 502 with service='orchestrator'."""
        mock_intent = IntentJSON(
            intent="start instance on AWS",
            cloud="AWS",
            action="start_instance",
            conditions="instance_id=i-abc123",
        )
        mock_ai_layer.parse_intent = AsyncMock(return_value=mock_intent)
        mock_orchestrator.route = AsyncMock(side_effect=Exception("Orchestrator failure"))

        response = client.post("/api/query", json={"query": "start my AWS instance i-abc123"})
        assert response.status_code == 502
        body = response.json()
        assert body["status"] == "error"
        assert body["error"]["service"] == "orchestrator"

    @patch("backend.api.routes.status.monitoring_layer")
    def test_monitoring_status_failure_returns_502(self, mock_monitoring, client):
        """When MonitoringLayer fails, GET /api/status returns 502."""
        mock_monitoring.get_resource_status = AsyncMock(side_effect=Exception("Connection refused"))

        response = client.get("/api/status")
        assert response.status_code == 502
        body = response.json()
        assert body["status"] == "error"
        assert body["error"]["service"] == "monitoring_layer"

    @patch("backend.api.routes.costs.monitoring_layer")
    def test_monitoring_costs_failure_returns_502(self, mock_monitoring, client):
        """When MonitoringLayer fails, GET /api/costs returns 502."""
        mock_monitoring.get_costs = AsyncMock(side_effect=Exception("Timeout"))

        response = client.get("/api/costs")
        assert response.status_code == 502
        body = response.json()
        assert body["status"] == "error"
        assert body["error"]["service"] == "monitoring_layer"
