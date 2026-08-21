"""Unit tests for AI Layer (Intent Parser).

Tests parsing of specific query examples for each provider (start/stop),
error cases (unparseable queries, unsupported providers, queries exceeding 500 chars),
and timeout behavior.

Requirements: 2.1, 2.3, 2.6, 2.7
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from backend.ai_layer.exceptions import (
    ParseError,
    QueryTooLongError,
    UnsupportedProviderError,
)
from backend.ai_layer.parser import AILayer


@pytest.fixture
def ai_layer():
    """Create an AILayer instance for testing."""
    return AILayer()


# --- Test parsing of specific query examples for each provider ---


@pytest.mark.asyncio
async def test_parse_start_aws_instance(ai_layer):
    """Parse 'start my AWS instance i-abc123' -> cloud=AWS, action=start_instance."""
    result = await ai_layer.parse_intent("start my AWS instance i-abc123")

    assert result.cloud == "AWS"
    assert result.action == "start_instance"
    assert result.intent  # non-empty
    assert "i-abc123" in result.conditions


@pytest.mark.asyncio
async def test_parse_stop_azure_vm(ai_layer):
    """Parse 'stop Azure VM myvm' -> cloud=Azure, action=stop_instance."""
    result = await ai_layer.parse_intent("stop Azure VM myvm")

    assert result.cloud == "Azure"
    assert result.action == "stop_instance"
    assert result.intent  # non-empty


@pytest.mark.asyncio
async def test_parse_start_gcp_instance(ai_layer):
    """Parse 'start GCP instance web-server' -> cloud=GCP, action=start_instance."""
    result = await ai_layer.parse_intent("start GCP instance web-server")

    assert result.cloud == "GCP"
    assert result.action == "start_instance"
    assert result.intent  # non-empty


@pytest.mark.asyncio
async def test_parse_launch_aws_instance(ai_layer):
    """Test 'launch' synonym maps to start_instance for AWS."""
    result = await ai_layer.parse_intent("launch AWS EC2 instance i-1234567890abcdef0")

    assert result.cloud == "AWS"
    assert result.action == "start_instance"


@pytest.mark.asyncio
async def test_parse_shutdown_azure_vm(ai_layer):
    """Test 'shutdown' synonym maps to stop_instance for Azure."""
    result = await ai_layer.parse_intent("shutdown my Azure VM web-server-1")

    assert result.cloud == "Azure"
    assert result.action == "stop_instance"


@pytest.mark.asyncio
async def test_parse_terminate_gcp_instance(ai_layer):
    """Test 'terminate' synonym maps to stop_instance for GCP."""
    result = await ai_layer.parse_intent("terminate GCP instance test-vm")

    assert result.cloud == "GCP"
    assert result.action == "stop_instance"


# --- Test error cases: unparseable queries ---


@pytest.mark.asyncio
async def test_unparseable_query_raises_parse_error(ai_layer):
    """Unparseable query (e.g., 'hello world') raises ParseError."""
    with pytest.raises(ParseError):
        await ai_layer.parse_intent("hello world")


@pytest.mark.asyncio
async def test_no_action_detected_raises_parse_error(ai_layer):
    """Query with provider but no action raises ParseError."""
    with pytest.raises(ParseError):
        await ai_layer.parse_intent("AWS is great")


@pytest.mark.asyncio
async def test_no_provider_detected_raises_parse_error(ai_layer):
    """Query with action but no provider raises ParseError."""
    with pytest.raises(ParseError):
        await ai_layer.parse_intent("start the instance please")


# --- Test error cases: unsupported providers ---


@pytest.mark.asyncio
async def test_unsupported_provider_digitalocean(ai_layer):
    """Query mentioning DigitalOcean raises UnsupportedProviderError."""
    with pytest.raises(UnsupportedProviderError) as exc_info:
        await ai_layer.parse_intent("start DigitalOcean droplet")

    assert "DigitalOcean" in exc_info.value.provider


@pytest.mark.asyncio
async def test_unsupported_provider_linode(ai_layer):
    """Query mentioning Linode raises UnsupportedProviderError."""
    with pytest.raises(UnsupportedProviderError):
        await ai_layer.parse_intent("stop Linode server")


@pytest.mark.asyncio
async def test_unsupported_provider_heroku(ai_layer):
    """Query mentioning Heroku raises UnsupportedProviderError."""
    with pytest.raises(UnsupportedProviderError):
        await ai_layer.parse_intent("start Heroku dyno")


# --- Test error cases: queries exceeding 500 chars ---


@pytest.mark.asyncio
async def test_query_exceeding_500_chars_raises_error(ai_layer):
    """Query > 500 characters raises QueryTooLongError."""
    long_query = "start AWS instance " + "a" * 500

    with pytest.raises(QueryTooLongError) as exc_info:
        await ai_layer.parse_intent(long_query)

    assert exc_info.value.length == len(long_query)
    assert exc_info.value.length > 500


@pytest.mark.asyncio
async def test_query_exactly_500_chars_does_not_raise(ai_layer):
    """Query exactly 500 characters should not raise QueryTooLongError."""
    # Build a query that's exactly 500 chars with a valid provider and action
    base = "start AWS instance "
    padding = "x" * (500 - len(base))
    query = base + padding
    assert len(query) == 500

    # Should not raise QueryTooLongError
    result = await ai_layer.parse_intent(query)
    assert result.cloud == "AWS"
    assert result.action == "start_instance"


@pytest.mark.asyncio
async def test_query_501_chars_raises_error(ai_layer):
    """Query of 501 characters raises QueryTooLongError."""
    base = "start AWS instance "
    padding = "x" * (501 - len(base))
    query = base + padding
    assert len(query) == 501

    with pytest.raises(QueryTooLongError):
        await ai_layer.parse_intent(query)


# --- Test timeout behavior ---


@pytest.mark.asyncio
async def test_timeout_raises_parse_error(ai_layer):
    """Parsing that exceeds timeout raises ParseError with timeout message."""
    # Mock _parse_with_patterns to simulate a timeout by making asyncio.wait_for raise TimeoutError
    with patch.object(
        ai_layer,
        "_parse_with_patterns",
        new_callable=AsyncMock,
        side_effect=asyncio.TimeoutError(),
    ):
        with pytest.raises(ParseError) as exc_info:
            await ai_layer.parse_intent("start AWS instance i-abc123")

        assert "timed out" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_timeout_uses_30_second_limit():
    """Verify the PARSE_TIMEOUT_SECONDS constant is 30."""
    from backend.ai_layer.parser import PARSE_TIMEOUT_SECONDS

    assert PARSE_TIMEOUT_SECONDS == 30
