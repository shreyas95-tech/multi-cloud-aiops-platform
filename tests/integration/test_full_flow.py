"""Integration tests for the full request flow: query -> parse -> route -> execute -> response.

Tests the complete end-to-end pipeline with mocked cloud SDKs to verify
wiring between AI Layer, Orchestrator, Execution Layer, and API.

Requirements: 1.1, 3.1, 10.6, 10.7
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.ai_layer.parser import AILayer
from backend.models.execution import ExecutionResult
from backend.models.intent import IntentJSON
from backend.orchestrator.orchestrator import Orchestrator


@pytest.fixture
def client():
    """Create a TestClient for the FastAPI app."""
    return TestClient(app)


class TestFullRequestFlowMockedAIAndOrchestrator:
    """Test query -> parse -> route -> execute -> response with fully mocked services."""

    def test_full_flow_returns_success_envelope(self, client):
        """Mock AILayer to return a known IntentJSON, mock Orchestrator to return
        a known ExecutionResult, verify the full envelope response at POST /api/query.
        """
        mock_intent = IntentJSON(
            intent="start instance i-abc123 on AWS",
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
            metadata={"region": "us-east-1"},
        )

        with patch(
            "backend.api.routes.query._ai_layer"
        ) as mock_ai, patch(
            "backend.api.routes.query._orchestrator"
        ) as mock_orch:
            mock_ai.parse_intent = AsyncMock(return_value=mock_intent)
            mock_orch.route = AsyncMock(return_value=mock_result)

            response = client.post("/api/query", json={"query": "start my AWS instance i-abc123"})

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["error"] is None
        assert body["data"]["success"] is True
        assert body["data"]["provider"] == "AWS"
        assert body["data"]["resource_id"] == "i-abc123"
        assert body["data"]["action"] == "start_instance"
        assert body["data"]["state"] == "running"

    def test_full_flow_azure_stop(self, client):
        """Test full flow for Azure stop operation."""
        mock_intent = IntentJSON(
            intent="stop VM myvm on Azure",
            cloud="Azure",
            action="stop_instance",
            conditions="vm_name=myvm",
        )
        mock_result = ExecutionResult(
            success=True,
            provider="Azure",
            resource_id="myvm",
            action="stop_instance",
            state="Deallocated",
            error_code=None,
            error_message=None,
            metadata={},
        )

        with patch(
            "backend.api.routes.query._ai_layer"
        ) as mock_ai, patch(
            "backend.api.routes.query._orchestrator"
        ) as mock_orch:
            mock_ai.parse_intent = AsyncMock(return_value=mock_intent)
            mock_orch.route = AsyncMock(return_value=mock_result)

            response = client.post("/api/query", json={"query": "stop Azure VM myvm"})

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["data"]["provider"] == "Azure"
        assert body["data"]["state"] == "Deallocated"


class TestFullFlowWithRealAILayer:
    """Test with real AILayer (pattern matching) + mock Orchestrator."""

    def test_parse_and_route_aws_start(self, client):
        """Send 'start my AWS instance i-abc123', verify intent is parsed correctly
        and routed to the orchestrator.
        """
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

        with patch(
            "backend.api.routes.query._ai_layer", new=AILayer()
        ), patch(
            "backend.api.routes.query._orchestrator"
        ) as mock_orch:
            mock_orch.route = AsyncMock(return_value=mock_result)

            response = client.post(
                "/api/query", json={"query": "start my AWS instance i-abc123"}
            )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["data"]["provider"] == "AWS"
        assert body["data"]["resource_id"] == "i-abc123"
        assert body["data"]["state"] == "running"

        # Verify the orchestrator was called with the correct intent
        call_args = mock_orch.route.call_args[0][0]
        assert call_args.cloud == "AWS"
        assert call_args.action == "start_instance"
        assert "i-abc123" in call_args.conditions

    def test_parse_and_route_gcp_stop(self, client):
        """Send a GCP stop query and verify parsing + routing."""
        mock_result = ExecutionResult(
            success=True,
            provider="GCP",
            resource_id="web-server-1",
            action="stop_instance",
            state="TERMINATED",
            error_code=None,
            error_message=None,
            metadata={},
        )

        with patch(
            "backend.api.routes.query._ai_layer", new=AILayer()
        ), patch(
            "backend.api.routes.query._orchestrator"
        ) as mock_orch:
            mock_orch.route = AsyncMock(return_value=mock_result)

            response = client.post(
                "/api/query", json={"query": "stop GCP instance web-server-1"}
            )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["data"]["provider"] == "GCP"

        # Verify the orchestrator received a GCP stop intent
        call_args = mock_orch.route.call_args[0][0]
        assert call_args.cloud == "GCP"
        assert call_args.action == "stop_instance"


class TestFullFlowWithMockedCloudSDK:
    """Test complete wired flow with mock cloud handlers registered in the orchestrator."""

    def test_end_to_end_with_real_orchestrator_and_mock_handler(self, client):
        """Configure the orchestrator with mock handlers, send a query, get a full response."""
        # Create a real orchestrator with a mock handler
        real_orchestrator = Orchestrator()

        async def mock_aws_start(params: dict) -> dict:
            return {
                "success": True,
                "provider": "AWS",
                "resource_id": "i-1234567890abcdef0",
                "action": "start_instance",
                "state": "running",
                "error_code": None,
                "error_message": None,
                "metadata": {"launch_time": "2024-01-01T00:00:00Z"},
            }

        real_orchestrator.register("AWS", "start_instance", mock_aws_start)
        real_orchestrator.register("AWS", "stop_instance", AsyncMock(return_value={
            "success": True,
            "provider": "AWS",
            "resource_id": "i-1234567890abcdef0",
            "action": "stop_instance",
            "state": "stopped",
            "metadata": {},
        }))

        with patch(
            "backend.api.routes.query._ai_layer", new=AILayer()
        ), patch(
            "backend.api.routes.query._orchestrator", new=real_orchestrator
        ):
            response = client.post(
                "/api/query",
                json={"query": "start my AWS instance i-1234567890abcdef0"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["data"]["success"] is True
        assert body["data"]["resource_id"] == "i-1234567890abcdef0"
        assert body["data"]["state"] == "running"
        assert body["data"]["metadata"]["launch_time"] == "2024-01-01T00:00:00Z"

    def test_end_to_end_execution_failure_from_handler(self, client):
        """Test that a handler returning an error dict flows back properly."""
        real_orchestrator = Orchestrator()

        async def mock_aws_start_fail(params: dict) -> dict:
            return {
                "success": False,
                "provider": "AWS",
                "resource_id": "i-abc123",
                "action": "start_instance",
                "state": None,
                "error_code": "InvalidInstanceID.NotFound",
                "error_message": "Instance not found",
                "metadata": {},
            }

        real_orchestrator.register("AWS", "start_instance", mock_aws_start_fail)

        with patch(
            "backend.api.routes.query._ai_layer", new=AILayer()
        ), patch(
            "backend.api.routes.query._orchestrator", new=real_orchestrator
        ):
            response = client.post(
                "/api/query",
                json={"query": "start my AWS instance i-abc123"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        # The execution layer returned a failure result (but the API call itself succeeded)
        assert body["data"]["success"] is False
        assert body["data"]["error_code"] == "InvalidInstanceID.NotFound"
        assert body["data"]["error_message"] == "Instance not found"
