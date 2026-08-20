"""Property-based tests for AI Layer input validation.

Property 4: AI Layer input validation errors — generate random queries
referencing unsupported providers or exceeding 500 chars, verify error responses.

**Validates: Requirements 2.6, 2.7**
"""

import pytest
import hypothesis.strategies as st
from hypothesis import given, settings

from backend.ai_layer.parser import AILayer, MAX_QUERY_LENGTH
from backend.ai_layer.exceptions import QueryTooLongError, UnsupportedProviderError

# Unsupported providers that the parser recognises
UNSUPPORTED_PROVIDERS = [
    "DigitalOcean",
    "Linode",
    "Oracle Cloud",
    "IBM Cloud",
    "Alibaba",
    "Heroku",
]

# Strategy: random strings longer than 500 characters
long_query_strategy = st.text(
    alphabet=st.characters(categories=("L", "N", "P", "Z")),
    min_size=MAX_QUERY_LENGTH + 1,
    max_size=MAX_QUERY_LENGTH + 200,
)

# Strategy: queries that mention an unsupported provider
unsupported_provider_strategy = st.tuples(
    st.sampled_from(UNSUPPORTED_PROVIDERS),
    st.sampled_from(["start", "stop", "launch", "halt"]),
).map(lambda t: f"{t[1]} my {t[0]} instance")


class TestProperty4AILayerInputValidationErrors:
    """Property 4: AI Layer input validation errors.

    For any natural language query that either references a cloud provider not in
    {"AWS", "Azure", "GCP"} or exceeds 500 characters in length, the AI Layer
    SHALL return an error response containing a message that identifies the
    specific validation failure (unsupported provider or length exceeded).

    **Validates: Requirements 2.6, 2.7**
    """

    @settings(max_examples=100)
    @given(query=long_query_strategy)
    @pytest.mark.asyncio
    async def test_queries_exceeding_500_chars_raise_query_too_long_error(
        self, query: str
    ) -> None:
        """Queries longer than 500 characters must raise QueryTooLongError."""
        ai_layer = AILayer()
        assert len(query) > MAX_QUERY_LENGTH

        with pytest.raises(QueryTooLongError) as exc_info:
            await ai_layer.parse_intent(query)

        # The error must identify the length validation failure
        assert exc_info.value.length == len(query)
        assert "500" in exc_info.value.message or "length" in exc_info.value.message.lower()

    @settings(max_examples=100)
    @given(query=unsupported_provider_strategy)
    @pytest.mark.asyncio
    async def test_unsupported_providers_raise_unsupported_provider_error(
        self, query: str
    ) -> None:
        """Queries mentioning unsupported providers must raise UnsupportedProviderError."""
        ai_layer = AILayer()

        # The query should be within length limits
        assert len(query) <= MAX_QUERY_LENGTH

        with pytest.raises(UnsupportedProviderError) as exc_info:
            await ai_layer.parse_intent(query)

        # The error must identify the unsupported provider
        assert exc_info.value.provider is not None
        assert len(exc_info.value.provider) > 0
        assert "unsupported" in exc_info.value.message.lower() or "supported" in exc_info.value.message.lower()

    @settings(max_examples=100)
    @given(
        provider=st.sampled_from(UNSUPPORTED_PROVIDERS),
        padding=st.text(
            alphabet=st.characters(categories=("L", "N", "Z")),
            min_size=0,
            max_size=50,
        ),
    )
    @pytest.mark.asyncio
    async def test_unsupported_provider_with_random_padding(
        self, provider: str, padding: str
    ) -> None:
        """Queries with unsupported providers and random surrounding text still raise error."""
        ai_layer = AILayer()
        query = f"start {padding} {provider} {padding} instance"

        # Ensure we don't accidentally exceed length limit
        if len(query) > MAX_QUERY_LENGTH:
            query = query[:MAX_QUERY_LENGTH]
            # If truncation removed the provider name, skip this example
            if provider.lower() not in query.lower():
                return

        # If the random padding accidentally contains a supported provider keyword,
        # the parser will legitimately detect the supported provider instead of the
        # unsupported one. Skip those cases as they don't test the intended property.
        query_upper = query.upper()
        supported_keywords = ["AWS", "AMAZON", "EC2", "AZURE", "MICROSOFT", "GCP", "GOOGLE", "GCLOUD"]
        if any(kw in query_upper for kw in supported_keywords):
            return

        with pytest.raises((UnsupportedProviderError, QueryTooLongError)):
            await ai_layer.parse_intent(query)

    @settings(max_examples=100)
    @given(
        base=st.text(
            alphabet=st.characters(categories=("L", "N", "Z")),
            min_size=450,
            max_size=450,
        ),
        extra=st.text(
            alphabet=st.characters(categories=("L", "N")),
            min_size=51,
            max_size=100,
        ),
    )
    @pytest.mark.asyncio
    async def test_length_validation_happens_before_provider_check(
        self, base: str, extra: str
    ) -> None:
        """Length validation must happen before provider detection (>500 chars always raises QueryTooLongError)."""
        ai_layer = AILayer()
        # Create a query that both exceeds length AND mentions an unsupported provider
        query = f"start DigitalOcean {base}{extra}"
        assert len(query) > MAX_QUERY_LENGTH

        # Length check takes priority over provider check
        with pytest.raises(QueryTooLongError) as exc_info:
            await ai_layer.parse_intent(query)

        assert exc_info.value.length == len(query)
