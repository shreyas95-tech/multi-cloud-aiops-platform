"""Property-based tests for frontend input validation (whitespace query rejection).

Tests the POST /api/query endpoint to verify that whitespace-only and empty
queries are rejected with HTTP 422 and proper error structure.

Validates: Requirements 1.6
"""

import hypothesis.strategies as st
from hypothesis import given, settings
from fastapi.testclient import TestClient

from backend.api.main import app


client = TestClient(app)

# Strategy for whitespace-only strings: spaces, tabs, newlines, carriage returns
whitespace_strategy = st.from_regex(r"[\s\t\n\r]*", fullmatch=True)


class TestProperty1WhitespaceQueryRejection:
    """Property 1: Whitespace query rejection.

    For any string composed entirely of whitespace characters (spaces, tabs,
    newlines, or empty string), the input validation layer SHALL reject it
    and prevent submission to the backend.

    Validates: Requirements 1.6
    """

    @settings(max_examples=100)
    @given(query=whitespace_strategy)
    def test_whitespace_only_queries_return_422(self, query: str) -> None:
        """Whitespace-only queries must be rejected with HTTP 422."""
        response = client.post("/api/query", json={"query": query})
        assert response.status_code == 422, (
            f"Expected 422 for whitespace-only query {query!r}, got {response.status_code}"
        )

    @settings(max_examples=100)
    @given(query=whitespace_strategy)
    def test_whitespace_only_queries_return_error_status(self, query: str) -> None:
        """Whitespace-only query responses must have status 'error'."""
        response = client.post("/api/query", json={"query": query})
        body = response.json()
        assert body["status"] == "error", (
            f"Expected status 'error' for query {query!r}, got {body['status']}"
        )

    @settings(max_examples=100)
    @given(query=whitespace_strategy)
    def test_whitespace_only_queries_have_error_field_info(self, query: str) -> None:
        """Whitespace-only query error responses must identify the 'query' field."""
        response = client.post("/api/query", json={"query": query})
        body = response.json()
        assert body["error"] is not None, "Error field must be present"
        assert body["error"]["field"] == "query", (
            f"Expected error field 'query', got {body['error'].get('field')}"
        )

    @settings(max_examples=100)
    @given(query=whitespace_strategy)
    def test_whitespace_only_queries_have_null_data(self, query: str) -> None:
        """Whitespace-only query error responses must have null data field."""
        response = client.post("/api/query", json={"query": query})
        body = response.json()
        assert body["data"] is None, (
            f"Expected null data for whitespace query {query!r}, got {body['data']}"
        )

    @settings(max_examples=100)
    @given(query=whitespace_strategy)
    def test_whitespace_only_queries_prevent_downstream_processing(self, query: str) -> None:
        """Whitespace-only queries must be blocked before reaching downstream services.

        This is confirmed by the 422 status code (not 502 which would indicate
        downstream service involvement).
        """
        response = client.post("/api/query", json={"query": query})
        assert response.status_code == 422, (
            f"Expected 422 (validation block) not 502 (downstream), got {response.status_code}"
        )
