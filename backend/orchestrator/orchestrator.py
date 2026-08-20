"""Orchestrator - Provider registry and intent routing."""

import logging
from datetime import datetime, timezone
from typing import Callable

from backend.models.execution import ExecutionResult
from backend.models.intent import IntentJSON

from .exceptions import UnsupportedActionError, UnsupportedProviderError, ValidationError

logger = logging.getLogger(__name__)


class Orchestrator:
    """Routes validated intents to registered cloud provider handlers.

    The Orchestrator maintains a provider registry mapping (provider, action) tuples
    to async handler functions. It validates incoming intents, performs audit logging,
    and delegates execution to the appropriate handler.
    """

    def __init__(self) -> None:
        self._registry: dict[tuple[str, str], Callable] = {}

    def register(self, provider: str, action: str, handler: Callable) -> None:
        """Register an execution function for a (provider, action) pair.

        Args:
            provider: Cloud provider name (e.g., "AWS", "Azure", "GCP").
            action: Action name (e.g., "start_instance", "stop_instance").
            handler: Async callable that takes a dict of params and returns a dict.
        """
        self._registry[(provider, action)] = handler

    async def route(self, intent: IntentJSON) -> ExecutionResult:
        """Validate and route intent to the registered handler.

        Validation order:
            1. Check cloud field is non-empty.
            2. Check action field is non-empty.
            3. Check (cloud, action) is registered in the provider registry.

        Logs intent_id, provider, action, and timestamp before invoking the handler.

        Args:
            intent: Parsed intent containing cloud, action, and conditions.

        Returns:
            ExecutionResult from the invoked handler.

        Raises:
            ValidationError: If cloud or action fields are empty.
            UnsupportedProviderError: If provider is not in the registry.
            UnsupportedActionError: If action is not registered for the provider.
        """
        intent_data = {
            "intent": intent.intent,
            "cloud": intent.cloud,
            "action": intent.action,
            "conditions": intent.conditions,
        }

        # Validation 1: Check cloud field non-empty
        if not intent.cloud or not intent.cloud.strip():
            raise ValidationError(
                field="cloud",
                reason="Cloud provider field must not be empty",
                intent_data=intent_data,
            )

        # Validation 2: Check action field non-empty
        if not intent.action or not intent.action.strip():
            raise ValidationError(
                field="action",
                reason="Action field must not be empty",
                intent_data=intent_data,
            )

        # Validation 3: Check (cloud, action) is registered
        key = (intent.cloud, intent.action)
        if key not in self._registry:
            # Determine if it's the provider or the action that's unsupported
            registered_providers = list(set(p for p, _ in self._registry.keys()))
            if intent.cloud not in registered_providers:
                raise UnsupportedProviderError(
                    provider=intent.cloud,
                    registered_providers=registered_providers,
                )
            else:
                # Provider exists but action is not registered for it
                registered_actions = [
                    a for p, a in self._registry.keys() if p == intent.cloud
                ]
                raise UnsupportedActionError(
                    provider=intent.cloud,
                    action=intent.action,
                    registered_actions=registered_actions,
                )

        # Audit logging before invocation
        timestamp = datetime.now(timezone.utc).isoformat()
        intent_id = f"{intent.cloud}:{intent.action}:{timestamp}"
        logger.info(
            "Routing intent",
            extra={
                "intent_id": intent_id,
                "provider": intent.cloud,
                "action": intent.action,
                "timestamp": timestamp,
            },
        )

        # Invoke the registered handler
        handler = self._registry[key]
        params = {"conditions": intent.conditions}
        result = await handler(params)

        # Convert handler response dict to ExecutionResult
        if isinstance(result, ExecutionResult):
            return result

        return ExecutionResult(
            success=result.get("success", True),
            provider=result.get("provider", intent.cloud),
            resource_id=result.get("resource_id", ""),
            action=result.get("action", intent.action),
            state=result.get("state"),
            error_code=result.get("error_code"),
            error_message=result.get("error_message"),
            metadata=result.get("metadata", {}),
        )
