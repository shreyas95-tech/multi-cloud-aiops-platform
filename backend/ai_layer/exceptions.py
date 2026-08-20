"""Custom exceptions for the AI Layer."""


class ParseError(Exception):
    """Raised when the AI Layer cannot determine intent from a query."""

    def __init__(self, message: str = "Unable to parse intent from query"):
        self.message = message
        super().__init__(self.message)


class UnsupportedProviderError(Exception):
    """Raised when the detected cloud provider is not in {AWS, Azure, GCP}."""

    def __init__(self, provider: str, message: str | None = None):
        self.provider = provider
        self.message = message or (
            f"Unsupported cloud provider: '{provider}'. "
            f"Supported providers are: AWS, Azure, GCP."
        )
        super().__init__(self.message)


class QueryTooLongError(Exception):
    """Raised when the input query exceeds 500 characters."""

    def __init__(self, length: int, message: str | None = None):
        self.length = length
        self.message = message or (
            f"Query exceeds maximum length of 500 characters "
            f"(got {length} characters)."
        )
        super().__init__(self.message)


class InsufficientDataError(Exception):
    """Raised when there is insufficient monitoring data to generate recommendations.

    This error is raised when the monitoring data does not cover at least 24 hours
    of resource usage, or when no cost entries and no resource statuses are available.
    """

    def __init__(self, message: str | None = None):
        self.message = message or (
            "Insufficient monitoring data to generate recommendations. "
            "At least 24 hours of monitoring data with cost entries or "
            "resource statuses is required."
        )
        super().__init__(self.message)
