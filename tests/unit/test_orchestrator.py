"""Unit tests for the Orchestrator class."""

import logging

import pytest

from backend.models.execution import ExecutionResult
from backend.models.intent import IntentJSON
from backend.orchestrator.exceptions import (
    UnsupportedActionError,
    UnsupportedProviderError,
    ValidationError,
)
from backend.orchestrator.orchestrator import Orchestrator


@pytest.fixture
def orchestrator():
    """Set up an Orchestrator with mock handlers for AWS, Azure, GCP."""
    orch = Orchestrator()

    async def mock_handler(params: dict) -> dict:
        return {
            "success": True,
            "provider": "mock",
            "resource_id": "i-123",
            "action": "mock_action",
            "state": "running",
        }

    # Register handlers for all (provider, action) pairs
    for provider in ("AWS", "Azure", "GCP"):
        for action in ("start_instance", "stop_instance"):
            orch.register(provider, action, mock_handler)

    return orch


def _make_intent(cloud: str, action: str) -> IntentJSON:
    """Helper to create an IntentJSON with default fields."""
    return IntentJSON(
        intent=f"{action} on {cloud}",
        cloud=cloud,
        action=action,
        conditions="",
    )


# -------------------------------------------------------------------
# Test routing for each registered (provider, action) pair
# -------------------------------------------------------------------


class TestRoutingValidIntents:
    """Route valid intent for each (provider, action) pair returns success."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "provider,action",
        [
            ("AWS", "start_instance"),
            ("AWS", "stop_instance"),
            ("Azure", "start_instance"),
            ("Azure", "stop_instance"),
            ("GCP", "start_instance"),
            ("GCP", "stop_instance"),
        ],
    )
    async def test_route_valid_intent(self, orchestrator, provider, action):
        intent = _make_intent(provider, action)
        result = await orchestrator.route(intent)

        assert isinstance(result, ExecutionResult)
        assert result.success is True


# -------------------------------------------------------------------
# Test rejection for unregistered pairs
# -------------------------------------------------------------------


class TestUnregisteredPairs:
    """Route intents with unregistered provider or action raises errors."""

    @pytest.mark.asyncio
    async def test_unregistered_provider_raises_error(self, orchestrator):
        intent = _make_intent("DigitalOcean", "start_instance")

        with pytest.raises(UnsupportedProviderError) as exc_info:
            await orchestrator.route(intent)

        assert exc_info.value.provider == "DigitalOcean"
        assert len(exc_info.value.registered_providers) > 0

    @pytest.mark.asyncio
    async def test_unregistered_action_raises_error(self, orchestrator):
        intent = _make_intent("AWS", "delete_instance")

        with pytest.raises(UnsupportedActionError) as exc_info:
            await orchestrator.route(intent)

        assert exc_info.value.provider == "AWS"
        assert exc_info.value.action == "delete_instance"
        assert "start_instance" in exc_info.value.registered_actions
        assert "stop_instance" in exc_info.value.registered_actions


# -------------------------------------------------------------------
# Test validation for malformed intents (missing fields)
# -------------------------------------------------------------------


class TestMalformedIntentValidation:
    """Route intents with empty cloud or action raises ValidationError."""

    @pytest.mark.asyncio
    async def test_empty_cloud_raises_validation_error(self, orchestrator):
        intent = _make_intent("", "start_instance")

        with pytest.raises(ValidationError) as exc_info:
            await orchestrator.route(intent)

        assert exc_info.value.field == "cloud"

    @pytest.mark.asyncio
    async def test_whitespace_cloud_raises_validation_error(self, orchestrator):
        intent = _make_intent("   ", "start_instance")

        with pytest.raises(ValidationError) as exc_info:
            await orchestrator.route(intent)

        assert exc_info.value.field == "cloud"

    @pytest.mark.asyncio
    async def test_empty_action_raises_validation_error(self, orchestrator):
        intent = _make_intent("AWS", "")

        with pytest.raises(ValidationError) as exc_info:
            await orchestrator.route(intent)

        assert exc_info.value.field == "action"

    @pytest.mark.asyncio
    async def test_whitespace_action_raises_validation_error(self, orchestrator):
        intent = _make_intent("AWS", "   ")

        with pytest.raises(ValidationError) as exc_info:
            await orchestrator.route(intent)

        assert exc_info.value.field == "action"


# -------------------------------------------------------------------
# Test audit log output format
# -------------------------------------------------------------------


class TestAuditLogging:
    """Verify audit log entries contain provider, action, and timestamp."""

    @pytest.mark.asyncio
    async def test_audit_log_contains_required_fields(self, orchestrator, caplog):
        intent = _make_intent("AWS", "start_instance")

        with caplog.at_level(logging.INFO, logger="backend.orchestrator.orchestrator"):
            await orchestrator.route(intent)

        # Verify that a log record was emitted
        assert len(caplog.records) >= 1

        record = caplog.records[0]
        assert record.provider == "AWS"
        assert record.action == "start_instance"
        assert record.timestamp is not None
        assert "intent_id" in record.__dict__

    @pytest.mark.asyncio
    async def test_audit_log_timestamp_is_iso_format(self, orchestrator, caplog):
        intent = _make_intent("GCP", "stop_instance")

        with caplog.at_level(logging.INFO, logger="backend.orchestrator.orchestrator"):
            await orchestrator.route(intent)

        record = caplog.records[0]
        # ISO 8601 format check — contains 'T' separator and ends with timezone info
        assert "T" in record.timestamp
        assert "+" in record.timestamp or "Z" in record.timestamp

    @pytest.mark.asyncio
    async def test_audit_log_intent_id_format(self, orchestrator, caplog):
        intent = _make_intent("Azure", "start_instance")

        with caplog.at_level(logging.INFO, logger="backend.orchestrator.orchestrator"):
            await orchestrator.route(intent)

        record = caplog.records[0]
        # intent_id format: "provider:action:timestamp"
        assert record.intent_id.startswith("Azure:start_instance:")
