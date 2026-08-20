"""Integration tests for error propagation and CORS headers.

Tests AI Layer failures, Orchestrator validation failures, cloud API failures,
and CORS header presence on all responses.

Requirements: 1.1, 3.1, 10.6, 10.7, 10.8
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.ai_layer.exceptions import ParseError, QueryTooLongError
from backend.ai_layer.parser import AILayer
from backend.api.main import app
from backend.models.intent import IntentJSON
from backend.orchestrator.exceptions import (
    UnsupportedActionError,
    UnsupportedProviderError,
    ValidationError,
)
from backend.orchestrator.orchestrator import Orchestrator


@pytest.fixture
def client():
    """Create a TestClient for the FastAPI app."""
    return TestClient(app)


class TestAILayerFailure:
    """Test error propagation when AI Layer fails."""

    def test_parse_error_returns_502(self, client):
        """Mock parse_intent to raise ParseError, verify 502 propagation."""
        with patch("backend.api.routes.query._ai_layer") as mock_ai:
            mock_ai.parse_intent = AsyncMock(
                side_effect=ParseError("Unable to parse intent from query: could not determine action")
            )

            response = client.post("/api/query", json={"query": "do something random"})

        assert response.status_code == 502
        body = response.json()
        assert body["status"] == "error"
        assert body["data"] is None
        assert body["error"]["service"] == "ai_layer"
        assert "parse" in body["error"]["message"].lower() or "intent" in body["error"]["message"].lower()

    def test_query_too_long_returns_502(self, client):
        """Test QueryTooLongError from AI Layer propagates as 502."""
        with patch("backend.api.routes.query._ai_layer") as mock_ai:
            mock_ai.parse_intent = AsyncMock(
                side_effect=QueryTooLongError(length=600)
            )

            response = client.post("/api/query", json={"query": "a" * 501})

        # Note: The route catches ParseError/QueryTooLongError and returns 502
        assert response.status_code == 502
        body = response.json()
        assert body["status"] == "error"
        assert body["error"]["service"] == "ai_layer"
        assert "500" in body["error"]["message"] or "length" in body["error"]["message"].lower()

    def test_unexpected_ai_layer_exception_returns_502(self, client):
        """Test that unexpected exceptions from AI Layer still return 502."""
        with patch("backend.api.routes.query._ai_layer") as mock_ai:
            mock_ai.parse_intent = AsyncMock(
                side_effect=RuntimeError("LLM API connection timeout")
            )

            response = client.post("/api/query", json={"query": "start AWS instance i-abc123"})

        assert response.status_code == 502
        body = response.json()
        assert body["status"] == "error"
        assert body["error"]["service"] == "ai_layer"
        assert "LLM API connection timeout" in body["error"]["message"]


class TestOrchestratorValidationFailure:
    """Test error propagation when Orchestrator validation fails."""

    def test_unsupported_provider_returns_502(self, client):
        """Send query that parses to invalid provider, verify error."""
        mock_intent = IntentJSON(
            intent="start instance on DigitalOcean",
            cloud="DigitalOcean",
            action="start_instance",
            conditions="",
        )

        with patch("backend.api.routes.query._ai_layer") as mock_ai, patch(
            "backend.api.routes.query._orchestrator"
        ) as mock_orch:
            mock_ai.parse_intent = AsyncMock(return_value=mock_intent)
            mock_orch.route = AsyncMock(
                side_effect=UnsupportedProviderError(
                    provider="DigitalOcean",
                    registered_providers=["AWS", "Azure", "GCP"],
                )
            )

            response = client.post("/api/query", json={"query": "start DigitalOcean instance"})

        assert response.status_code == 502
        body = response.json()
        assert body["status"] == "error"
        assert body["error"]["service"] == "orchestrator"
        assert "DigitalOcean" in body["error"]["message"]

    def test_unsupported_action_returns_502(self, client):
        """Test orchestrator rejection when action is not registered."""
        mock_intent = IntentJSON(
            intent="resize instance on AWS",
            cloud="AWS",
            action="resize_instance",
            conditions="",
        )

        with patch("backend.api.routes.query._ai_layer") as mock_ai, patch(
            "backend.api.routes.query._orchestrator"
        ) as mock_orch:
            mock_ai.parse_intent = AsyncMock(return_value=mock_intent)
            mock_orch.route = AsyncMock(
                side_effect=UnsupportedActionError(
                    provider="AWS",
                    action="resize_instance",
                    registered_actions=["start_instance", "stop_instance"],
                )
            )

            response = client.post("/api/query", json={"query": "resize my AWS instance"})

        assert response.status_code == 502
        body = response.json()
        assert body["status"] == "error"
        assert body["error"]["service"] == "orchestrator"
        assert "resize_instance" in body["error"]["message"]

    def test_validation_error_returns_502(self, client):
        """Test orchestrator validation error with malformed intent."""
        mock_intent = IntentJSON(
            intent="",
            cloud="",
            action="start_instance",
            conditions="",
        )

        with patch("backend.api.routes.query._ai_layer") as mock_ai, patch(
            "backend.api.routes.query._orchestrator"
        ) as mock_orch:
            mock_ai.parse_intent = AsyncMock(return_value=mock_intent)
            mock_orch.route = AsyncMock(
                side_effect=ValidationError(
                    field="cloud",
                    reason="Cloud provider field must not be empty",
                    intent_data={"cloud": "", "action": "start_instance"},
                )
            )

            response = client.post("/api/query", json={"query": "start something"})

        assert response.status_code == 502
        body = response.json()
        assert body["status"] == "error"
        assert body["error"]["service"] == "orchestrator"
        assert "cloud" in body["error"]["message"].lower()


class TestCloudAPIFailure:
    """Test error propagation when cloud execution handler fails."""

    def test_handler_raises_exception_returns_502(self, client):
        """Mock execution handler to raise exception, verify 502 in response."""
        mock_intent = IntentJSON(
            intent="start instance i-abc123 on AWS",
            cloud="AWS",
            action="start_instance",
            conditions="instance_id=i-abc123",
        )

        with patch("backend.api.routes.query._ai_layer") as mock_ai, patch(
            "backend.api.routes.query._orchestrator"
        ) as mock_orch:
            mock_ai.parse_intent = AsyncMock(return_value=mock_intent)
            mock_orch.route = AsyncMock(
                side_effect=Exception("AWS EC2 API: InvalidInstanceID.NotFound")
            )

            response = client.post(
                "/api/query", json={"query": "start AWS instance i-abc123"}
            )

        assert response.status_code == 502
        body = response.json()
        assert body["status"] == "error"
        assert body["error"]["service"] == "orchestrator"
        assert "InvalidInstanceID" in body["error"]["message"]

    def test_monitoring_layer_complete_failure_returns_502(self, client):
        """Test that a complete monitoring layer failure returns 502."""
        with patch("backend.api.routes.status.monitoring_layer") as mock_monitoring:
            mock_monitoring.get_resource_status = AsyncMock(
                side_effect=RuntimeError("All provider APIs unreachable")
            )

            response = client.get("/api/status")

        assert response.status_code == 502
        body = response.json()
        assert body["status"] == "error"
        assert body["error"]["service"] == "monitoring_layer"
        assert "unreachable" in body["error"]["message"].lower()

    def test_costs_layer_failure_returns_502(self, client):
        """Test that a costs layer failure returns 502."""
        with patch("backend.api.routes.costs.monitoring_layer") as mock_monitoring:
            mock_monitoring.get_costs = AsyncMock(
                side_effect=RuntimeError("Billing API timeout")
            )

            response = client.get("/api/costs")

        assert response.status_code == 502
        body = response.json()
        assert body["status"] == "error"
        assert body["error"]["service"] == "monitoring_layer"


class TestCORSHeaders:
    """Test CORS headers are present on all responses."""

    def test_cors_on_success_response(self, client):
        """Verify CORS headers on successful query response."""
        with patch("backend.api.routes.query._ai_layer") as mock_ai, patch(
            "backend.api.routes.query._orchestrator"
        ) as mock_orch:
            from backend.models.execution import ExecutionResult

            mock_ai.parse_intent = AsyncMock(
                return_value=IntentJSON(
                    intent="start on AWS",
                    cloud="AWS",
                    action="start_instance",
                    conditions="",
                )
            )
            mock_orch.route = AsyncMock(
                return_value=ExecutionResult(
                    success=True,
                    provider="AWS",
                    resource_id="i-test",
                    action="start_instance",
                    state="running",
                    metadata={},
                )
            )

            response = client.post(
                "/api/query",
                json={"query": "start AWS instance"},
                headers={"Origin": "http://localhost:3000"},
            )

        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers

    def test_cors_on_error_response(self, client):
        """Verify CORS headers on error responses."""
        with patch("backend.api.routes.query._ai_layer") as mock_ai:
            mock_ai.parse_intent = AsyncMock(
                side_effect=ParseError("Cannot parse")
            )

            response = client.post(
                "/api/query",
                json={"query": "something unparseable"},
                headers={"Origin": "http://localhost:3000"},
            )

        assert response.status_code == 502
        assert "access-control-allow-origin" in response.headers

    def test_cors_on_validation_error(self, client):
        """Verify CORS headers on 422 validation error."""
        response = client.post(
            "/api/query",
            json={"query": "   "},
            headers={"Origin": "http://localhost:3000"},
        )

        assert response.status_code == 422
        assert "access-control-allow-origin" in response.headers

    def test_cors_on_status_endpoint(self, client):
        """Verify CORS headers on GET /api/status."""
        with patch("backend.api.routes.status.monitoring_layer") as mock_monitoring:
            mock_monitoring.get_resource_status = AsyncMock(return_value=[])

            response = client.get(
                "/api/status",
                headers={"Origin": "http://localhost:3000"},
            )

        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers

    def test_cors_on_costs_endpoint(self, client):
        """Verify CORS headers on GET /api/costs."""
        with patch("backend.api.routes.costs.monitoring_layer") as mock_monitoring:
            mock_monitoring.get_costs = AsyncMock(return_value=[])

            response = client.get(
                "/api/costs",
                headers={"Origin": "http://localhost:3000"},
            )

        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers

    def test_cors_preflight_request(self, client):
        """Verify CORS preflight (OPTIONS) request is handled."""
        response = client.options(
            "/api/query",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )

        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers
        assert "access-control-allow-methods" in response.headers


class TestEnvelopeStructureConsistency:
    """Verify that all responses use the consistent envelope structure."""

    def test_success_envelope_structure(self, client):
        """Verify success envelope has status, data, error fields."""
        with patch("backend.api.routes.status.monitoring_layer") as mock_monitoring:
            mock_monitoring.get_resource_status = AsyncMock(return_value=[])

            response = client.get("/api/status")

        body = response.json()
        assert "status" in body
        assert "data" in body
        assert "error" in body
        assert body["status"] == "success"
        assert body["error"] is None

    def test_error_envelope_structure(self, client):
        """Verify error envelope has status, data, error fields."""
        with patch("backend.api.routes.query._ai_layer") as mock_ai:
            mock_ai.parse_intent = AsyncMock(side_effect=ParseError("fail"))

            response = client.post("/api/query", json={"query": "test"})

        body = response.json()
        assert "status" in body
        assert "data" in body
        assert "error" in body
        assert body["status"] == "error"
        assert body["data"] is None
        assert body["error"] is not None

    def test_404_envelope_structure(self, client):
        """Verify 404 responses follow envelope structure."""
        response = client.get("/api/nonexistent")

        assert response.status_code == 404
        body = response.json()
        assert body["status"] == "error"
        assert body["data"] is None
        assert body["error"] is not None
