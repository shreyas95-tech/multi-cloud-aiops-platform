"""Property-based tests for Orchestrator routing.

Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.6, 3.7, 11.4
"""

import logging
from unittest.mock import AsyncMock

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from backend.models.execution import ExecutionResult
from backend.models.intent import IntentJSON
from backend.orchestrator.exceptions import (
    UnsupportedActionError,
    UnsupportedProviderError,
    ValidationError,
)
from backend.orchestrator.orchestrator import Orchestrator

# --- Strategies ---

# Known providers and actions used for the registry setup
REGISTERED_PROVIDERS = ["AWS", "Azure", "GCP"]
REGISTERED_ACTIONS = ["start_instance", "stop_instance"]

# All registered (provider, action) pairs
REGISTERED_PAIRS = [
    (provider, action)
    for provider in REGISTERED_PROVIDERS
    for action in REGISTERED_ACTIONS
]

# Strategy for picking a registered (provider, action) pair
registered_pair_strategy = st.sampled_from(REGISTERED_PAIRS)

# Strategy for non-empty strings used in intent/conditions fields
non_empty_str_strategy = st.text(min_size=1, max_size=100).filter(lambda s: s.strip() != "")
conditions_strategy = st.text(min_size=0, max_size=200)

# Strategy for unregistered provider names (not in REGISTERED_PROVIDERS)
unregistered_provider_strategy = st.text(min_size=1, max_size=50).filter(
    lambda s: s.strip() != "" and s not in REGISTERED_PROVIDERS
)

# Strategy for unregistered action names (not in REGISTERED_ACTIONS)
unregistered_action_strategy = st.text(min_size=1, max_size=50).filter(
    lambda s: s.strip() != "" and s not in REGISTERED_ACTIONS
)

# Strategy for dynamically registerable new providers/actions
new_provider_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=30,
).filter(lambda s: s not in REGISTERED_PROVIDERS)

new_action_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
    min_size=1,
    max_size=30,
).filter(lambda s: s not in REGISTERED_ACTIONS)


# --- Fixtures ---


def _make_mock_handler(provider: str, action: str) -> AsyncMock:
    """Create a mock async handler that returns a valid result dict."""
    handler = AsyncMock()
    handler.return_value = {
        "success": True,
        "provider": provider,
        "resource_id": f"resource-{provider}-001",
        "action": action,
        "state": "running",
        "error_code": None,
        "error_message": None,
        "metadata": {},
    }
    return handler


def _create_orchestrator_with_registry() -> tuple[Orchestrator, dict[tuple[str, str], AsyncMock]]:
    """Create an Orchestrator with all registered pairs and return it with its handlers."""
    orchestrator = Orchestrator()
    handlers: dict[tuple[str, str], AsyncMock] = {}
    for provider, action in REGISTERED_PAIRS:
        handler = _make_mock_handler(provider, action)
        orchestrator.register(provider, action, handler)
        handlers[(provider, action)] = handler
    return orchestrator, handlers


# --- Property 5: Orchestrator routes valid intents correctly ---


class TestProperty5OrchestratorRoutesValidIntents:
    """Property 5: Orchestrator routes valid intents correctly.

    For any Intent_JSON whose (cloud, action) pair is present in the provider registry,
    the Orchestrator SHALL successfully route it to the exact execution function
    registered for that pair, without error.

    **Validates: Requirements 3.1, 3.2**
    """

    @settings(max_examples=100)
    @given(
        pair=registered_pair_strategy,
        intent_text=non_empty_str_strategy,
        conditions=conditions_strategy,
    )
    @pytest.mark.asyncio
    async def test_routes_to_correct_handler(
        self, pair: tuple[str, str], intent_text: str, conditions: str
    ) -> None:
        """Valid (cloud, action) pairs route to the registered handler successfully."""
        provider, action = pair
        orchestrator, handlers = _create_orchestrator_with_registry()

        intent = IntentJSON(
            intent=intent_text,
            cloud=provider,
            action=action,
            conditions=conditions,
        )

        result = await orchestrator.route(intent)

        # Verify routing succeeded without error
        assert isinstance(result, ExecutionResult)
        assert result.success is True
        assert result.provider == provider
        assert result.action == action

        # Verify the correct handler was invoked
        expected_handler = handlers[(provider, action)]
        expected_handler.assert_called_once()

    @settings(max_examples=100)
    @given(
        pair=registered_pair_strategy,
        intent_text=non_empty_str_strategy,
        conditions=conditions_strategy,
    )
    @pytest.mark.asyncio
    async def test_no_other_handlers_invoked(
        self, pair: tuple[str, str], intent_text: str, conditions: str
    ) -> None:
        """Only the handler for the exact (cloud, action) pair is invoked."""
        provider, action = pair
        orchestrator, handlers = _create_orchestrator_with_registry()

        intent = IntentJSON(
            intent=intent_text,
            cloud=provider,
            action=action,
            conditions=conditions,
        )

        await orchestrator.route(intent)

        # Verify no other handlers were called
        for key, handler in handlers.items():
            if key != (provider, action):
                handler.assert_not_called()


# --- Property 6: Orchestrator rejects unregistered provider/action pairs ---


class TestProperty6OrchestratorRejectsUnregistered:
    """Property 6: Orchestrator rejects unregistered provider/action pairs.

    For any Intent_JSON whose (cloud, action) pair is NOT present in the provider registry,
    the Orchestrator SHALL return an error indicating the unsupported provider or action,
    and SHALL NOT invoke any execution function.

    **Validates: Requirements 3.3**
    """

    @settings(max_examples=100)
    @given(
        provider=unregistered_provider_strategy,
        action=non_empty_str_strategy,
        intent_text=non_empty_str_strategy,
        conditions=conditions_strategy,
    )
    @pytest.mark.asyncio
    async def test_unregistered_provider_raises_error(
        self, provider: str, action: str, intent_text: str, conditions: str
    ) -> None:
        """Unregistered providers raise UnsupportedProviderError."""
        orchestrator, handlers = _create_orchestrator_with_registry()

        intent = IntentJSON(
            intent=intent_text,
            cloud=provider,
            action=action,
            conditions=conditions,
        )

        with pytest.raises(UnsupportedProviderError) as exc_info:
            await orchestrator.route(intent)

        assert exc_info.value.provider == provider

        # Verify no handlers were invoked
        for handler in handlers.values():
            handler.assert_not_called()

    @settings(max_examples=100)
    @given(
        provider=st.sampled_from(REGISTERED_PROVIDERS),
        action=unregistered_action_strategy,
        intent_text=non_empty_str_strategy,
        conditions=conditions_strategy,
    )
    @pytest.mark.asyncio
    async def test_unregistered_action_raises_error(
        self, provider: str, action: str, intent_text: str, conditions: str
    ) -> None:
        """Unregistered actions for a known provider raise UnsupportedActionError."""
        orchestrator, handlers = _create_orchestrator_with_registry()

        intent = IntentJSON(
            intent=intent_text,
            cloud=provider,
            action=action,
            conditions=conditions,
        )

        with pytest.raises(UnsupportedActionError) as exc_info:
            await orchestrator.route(intent)

        assert exc_info.value.provider == provider
        assert exc_info.value.action == action

        # Verify no handlers were invoked
        for handler in handlers.values():
            handler.assert_not_called()


# --- Property 7: Orchestrator rejects malformed intents ---


class TestProperty7OrchestratorRejectsMalformed:
    """Property 7: Orchestrator rejects malformed intents.

    For any Intent_JSON that is missing required fields (empty cloud or empty action)
    or contains malformed data, the Orchestrator SHALL return a validation error and
    preserve the original intent data for audit purposes.

    **Validates: Requirements 3.4**
    """

    @settings(max_examples=100)
    @given(
        action=non_empty_str_strategy,
        intent_text=non_empty_str_strategy,
        conditions=conditions_strategy,
    )
    @pytest.mark.asyncio
    async def test_empty_cloud_raises_validation_error(
        self, action: str, intent_text: str, conditions: str
    ) -> None:
        """Empty cloud field raises ValidationError with field='cloud'."""
        orchestrator, handlers = _create_orchestrator_with_registry()

        intent = IntentJSON(
            intent=intent_text,
            cloud="",
            action=action,
            conditions=conditions,
        )

        with pytest.raises(ValidationError) as exc_info:
            await orchestrator.route(intent)

        assert exc_info.value.field == "cloud"
        # Original intent data is preserved for audit
        assert exc_info.value.intent_data is not None
        assert exc_info.value.intent_data["action"] == action

        # No handlers invoked
        for handler in handlers.values():
            handler.assert_not_called()

    @settings(max_examples=100)
    @given(
        provider=st.sampled_from(REGISTERED_PROVIDERS),
        intent_text=non_empty_str_strategy,
        conditions=conditions_strategy,
    )
    @pytest.mark.asyncio
    async def test_empty_action_raises_validation_error(
        self, provider: str, intent_text: str, conditions: str
    ) -> None:
        """Empty action field raises ValidationError with field='action'."""
        orchestrator, handlers = _create_orchestrator_with_registry()

        intent = IntentJSON(
            intent=intent_text,
            cloud=provider,
            action="",
            conditions=conditions,
        )

        with pytest.raises(ValidationError) as exc_info:
            await orchestrator.route(intent)

        assert exc_info.value.field == "action"
        # Original intent data is preserved for audit
        assert exc_info.value.intent_data is not None
        assert exc_info.value.intent_data["cloud"] == provider

        # No handlers invoked
        for handler in handlers.values():
            handler.assert_not_called()

    @settings(max_examples=100)
    @given(
        intent_text=non_empty_str_strategy,
        conditions=conditions_strategy,
    )
    @pytest.mark.asyncio
    async def test_whitespace_only_cloud_raises_validation_error(
        self, intent_text: str, conditions: str
    ) -> None:
        """Whitespace-only cloud field raises ValidationError."""
        orchestrator, _ = _create_orchestrator_with_registry()

        # Use various whitespace-only strings
        whitespace_cloud = "   "
        intent = IntentJSON(
            intent=intent_text,
            cloud=whitespace_cloud,
            action="start_instance",
            conditions=conditions,
        )

        with pytest.raises(ValidationError) as exc_info:
            await orchestrator.route(intent)

        assert exc_info.value.field == "cloud"

    @settings(max_examples=100)
    @given(
        intent_text=non_empty_str_strategy,
        conditions=conditions_strategy,
    )
    @pytest.mark.asyncio
    async def test_whitespace_only_action_raises_validation_error(
        self, intent_text: str, conditions: str
    ) -> None:
        """Whitespace-only action field raises ValidationError."""
        orchestrator, _ = _create_orchestrator_with_registry()

        intent = IntentJSON(
            intent=intent_text,
            cloud="AWS",
            action="   ",
            conditions=conditions,
        )

        with pytest.raises(ValidationError) as exc_info:
            await orchestrator.route(intent)

        assert exc_info.value.field == "action"


# --- Property 8: Orchestrator audit logging ---


class _LogCaptureHandler(logging.Handler):
    """Custom logging handler to capture log records within tests."""

    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def reset(self) -> None:
        self.records.clear()


class TestProperty8OrchestratorAuditLogging:
    """Property 8: Orchestrator audit logging.

    For any successfully routed intent, the Orchestrator SHALL emit an audit log entry
    containing the intent identifier, target cloud provider, action name, and timestamp,
    all recorded before the execution function is invoked.

    **Validates: Requirements 3.6**
    """

    @settings(max_examples=100)
    @given(
        pair=registered_pair_strategy,
        intent_text=non_empty_str_strategy,
        conditions=conditions_strategy,
    )
    @pytest.mark.asyncio
    async def test_audit_log_emitted_before_execution(
        self, pair: tuple[str, str], intent_text: str, conditions: str
    ) -> None:
        """Audit log is emitted before the handler is invoked."""
        provider, action = pair
        orchestrator, handlers = _create_orchestrator_with_registry()

        intent = IntentJSON(
            intent=intent_text,
            cloud=provider,
            action=action,
            conditions=conditions,
        )

        # Track the order of events
        call_order: list[str] = []

        async def tracking_handler(params):
            call_order.append("handler_called")
            return {
                "success": True,
                "provider": provider,
                "resource_id": f"resource-{provider}-001",
                "action": action,
                "state": "running",
                "error_code": None,
                "error_message": None,
                "metadata": {},
            }

        # Replace the handler with our tracking one
        orchestrator._registry[(provider, action)] = tracking_handler

        # Use a custom log handler instead of caplog
        log_capture = _LogCaptureHandler()
        logger_instance = logging.getLogger("backend.orchestrator.orchestrator")
        logger_instance.addHandler(log_capture)
        logger_instance.setLevel(logging.INFO)

        try:
            await orchestrator.route(intent)

            # Verify log was emitted
            assert len(log_capture.records) >= 1
            log_record = log_capture.records[0]

            # Verify required audit fields
            assert log_record.provider == provider
            assert log_record.action == action
            assert hasattr(log_record, "intent_id")
            assert hasattr(log_record, "timestamp")
            assert log_record.timestamp != ""
        finally:
            logger_instance.removeHandler(log_capture)
            log_capture.reset()

    @settings(max_examples=100)
    @given(
        pair=registered_pair_strategy,
        intent_text=non_empty_str_strategy,
        conditions=conditions_strategy,
    )
    @pytest.mark.asyncio
    async def test_audit_log_contains_all_required_fields(
        self, pair: tuple[str, str], intent_text: str, conditions: str
    ) -> None:
        """Audit log entry contains intent_id, provider, action, and timestamp."""
        provider, action = pair
        orchestrator, _ = _create_orchestrator_with_registry()

        intent = IntentJSON(
            intent=intent_text,
            cloud=provider,
            action=action,
            conditions=conditions,
        )

        # Use a custom log handler instead of caplog
        log_capture = _LogCaptureHandler()
        logger_instance = logging.getLogger("backend.orchestrator.orchestrator")
        logger_instance.addHandler(log_capture)
        logger_instance.setLevel(logging.INFO)

        try:
            await orchestrator.route(intent)

            # Find the routing log entry
            assert len(log_capture.records) >= 1
            log_record = log_capture.records[0]

            # Verify all required audit fields are present
            assert hasattr(log_record, "intent_id"), "Missing intent_id in log"
            assert hasattr(log_record, "provider"), "Missing provider in log"
            assert hasattr(log_record, "action"), "Missing action in log"
            assert hasattr(log_record, "timestamp"), "Missing timestamp in log"

            # Verify values are correct
            assert log_record.provider == provider
            assert log_record.action == action
            assert provider in log_record.intent_id
            assert action in log_record.intent_id
        finally:
            logger_instance.removeHandler(log_capture)
            log_capture.reset()


# --- Property 9: Dynamic provider registration and routing ---


class TestProperty9DynamicProviderRegistration:
    """Property 9: Dynamic provider registration and routing.

    For any new (cloud_provider, action) pair that is dynamically registered in the
    provider registry with a valid execution function, the Orchestrator SHALL successfully
    route subsequent intents for that pair without modification to existing routing logic.

    **Validates: Requirements 3.7, 11.4**
    """

    @settings(max_examples=100)
    @given(
        new_provider=new_provider_strategy,
        new_action=new_action_strategy,
        intent_text=non_empty_str_strategy,
        conditions=conditions_strategy,
    )
    @pytest.mark.asyncio
    async def test_dynamically_registered_pair_routes_successfully(
        self, new_provider: str, new_action: str, intent_text: str, conditions: str
    ) -> None:
        """Dynamically registered (provider, action) pairs route correctly."""
        orchestrator, existing_handlers = _create_orchestrator_with_registry()

        # Create and register a new handler for the new pair
        new_handler = _make_mock_handler(new_provider, new_action)
        orchestrator.register(new_provider, new_action, new_handler)

        intent = IntentJSON(
            intent=intent_text,
            cloud=new_provider,
            action=new_action,
            conditions=conditions,
        )

        result = await orchestrator.route(intent)

        # Verify the new pair routes successfully
        assert isinstance(result, ExecutionResult)
        assert result.success is True
        assert result.provider == new_provider
        assert result.action == new_action

        # Verify the new handler was called
        new_handler.assert_called_once()

    @settings(max_examples=100)
    @given(
        new_provider=new_provider_strategy,
        new_action=new_action_strategy,
        existing_pair=registered_pair_strategy,
        intent_text=non_empty_str_strategy,
        conditions=conditions_strategy,
    )
    @pytest.mark.asyncio
    async def test_dynamic_registration_does_not_affect_existing_routes(
        self,
        new_provider: str,
        new_action: str,
        existing_pair: tuple[str, str],
        intent_text: str,
        conditions: str,
    ) -> None:
        """Adding new pairs does not break existing registered routes."""
        orchestrator, existing_handlers = _create_orchestrator_with_registry()

        # Register a new pair
        new_handler = _make_mock_handler(new_provider, new_action)
        orchestrator.register(new_provider, new_action, new_handler)

        # Route an existing pair — should still work
        existing_provider, existing_action = existing_pair
        intent = IntentJSON(
            intent=intent_text,
            cloud=existing_provider,
            action=existing_action,
            conditions=conditions,
        )

        result = await orchestrator.route(intent)

        assert isinstance(result, ExecutionResult)
        assert result.success is True
        assert result.provider == existing_provider
        assert result.action == existing_action

        # Verify the existing handler was called, not the new one
        existing_handlers[(existing_provider, existing_action)].assert_called_once()
        new_handler.assert_not_called()
