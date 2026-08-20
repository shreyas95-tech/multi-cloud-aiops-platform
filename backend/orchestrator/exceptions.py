"""Custom exceptions for the Orchestrator layer."""


class UnsupportedProviderError(Exception):
    """Raised when the intent references a cloud provider not in the registry."""

    def __init__(self, provider: str, registered_providers: list[str] | None = None):
        self.provider = provider
        self.registered_providers = registered_providers or []
        message = f"Unsupported cloud provider: '{provider}'"
        if self.registered_providers:
            message += f". Supported providers: {', '.join(sorted(set(self.registered_providers)))}"
        super().__init__(message)


class UnsupportedActionError(Exception):
    """Raised when the intent references an action not registered for the provider."""

    def __init__(self, provider: str, action: str, registered_actions: list[str] | None = None):
        self.provider = provider
        self.action = action
        self.registered_actions = registered_actions or []
        message = f"Unsupported action '{action}' for provider '{provider}'"
        if self.registered_actions:
            message += f". Available actions: {', '.join(sorted(self.registered_actions))}"
        super().__init__(message)


class ValidationError(Exception):
    """Raised when the intent fails structural validation."""

    def __init__(self, field: str, reason: str, intent_data: dict | None = None):
        self.field = field
        self.reason = reason
        self.intent_data = intent_data or {}
        message = f"Validation failed for field '{field}': {reason}"
        super().__init__(message)
