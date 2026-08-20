"""Property-based tests for API Layer.

Validates: Requirements 10.5, 10.6, 10.7, 10.8
"""

from unittest.mock import AsyncMock, patch

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings
from fastapi.testclient import TestClient

from backend.api.main import app


client = TestClient(app)


# --- Strategies ---

# Endpoints that exist in the API
endpoint_strategy = st.sampled_from([
    ("GET", "/api/status"),
    ("GET", "/api/costs"),
    ("GET", "/api/recommendations"),
    ("POST", "/api/query"),
])

# Random string strategies for invalid payloads
empty_or_whitespace_strategy = st.sampled_from(["", " ", "  ", "\t", "\n", "  \t\n  "])

# Strings exceeding 2000 chars for query validation
too_long_query_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=2001,
    max_size=2500,
)

# Random non-empty query strings (valid length)
valid_query_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=100,
)

# Service names that might fail downstream
downstream_service_strategy = st.sampled_from(["ai_layer", "orchestrator", "monitoring_layer"])

# Random error messages
error_message_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=200,
)


# ============================================================================
# Property 19: API envelope consistency
# ============================================================================


class TestAPIEnvelopeConsistency:
    """Property 19: API envelope consistency.

    *For any* response returned by the Backend API (success or error), it SHALL
    conform to the envelope structure containing a `status` field (either "success"
    or "error"), a `data` field (present on success, null on error), and an `error`
    field (present on error, null on success).

    **Validates: Requirements 10.6**
    """

    @settings(max_examples=100)
    @given(data=st.data())
    def test_successful_responses_have_envelope_structure(self, data):
        """Generate random successful requests, verify envelope structure."""
        # Use the health-check endpoint which always succeeds
        response = client.get("/")
        body = response.json()

        # Verify envelope structure
        assert "status" in body, "Response must have 'status' field"
        assert "data" in body, "Response must have 'data' field"
        assert "error" in body, "Response must have 'error' field"
        assert body["status"] == "success"
        assert body["data"] is not None
        assert body["error"] is None

    @settings(max_examples=100)
    @given(path=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1,
        max_size=30,
    ))
    def test_error_responses_have_envelope_structure(self, path):
        """Generate random non-existent paths, verify error envelope structure."""
        response = client.get(f"/api/nonexistent_{path}")
        body = response.json()

        # Verify envelope structure
        assert "status" in body, "Response must have 'status' field"
        assert "data" in body, "Response must have 'data' field"
        assert "error" in body, "Response must have 'error' field"
        assert body["status"] == "error"
        assert body["data"] is None
        assert body["error"] is not None

    @settings(max_examples=100)
    @given(query=empty_or_whitespace_strategy)
    def test_validation_error_responses_have_envelope_structure(self, query):
        """Generate random invalid query inputs, verify envelope structure on 422."""
        response = client.post("/api/query", json={"query": query})
        body = response.json()

        # Verify envelope structure
        assert "status" in body, "Response must have 'status' field"
        assert "data" in body, "Response must have 'data' field"
        assert "error" in body, "Response must have 'error' field"
        assert body["status"] == "error"
        assert body["data"] is None
        assert body["error"] is not None


# ============================================================================
# Property 20: API validation error responses
# ============================================================================


class TestAPIValidationErrorResponses:
    """Property 20: API validation error responses.

    *For any* API request that fails input validation, the Backend SHALL return
    HTTP 422 with a JSON body containing the name of the field that failed validation
    and a human-readable description of the violated rule.

    **Validates: Requirements 10.5**
    """

    @settings(max_examples=100)
    @given(query=empty_or_whitespace_strategy)
    def test_empty_query_returns_422_with_field_and_message(self, query):
        """Empty/whitespace-only queries produce 422 with field name and rule."""
        response = client.post("/api/query", json={"query": query})

        assert response.status_code == 422
        body = response.json()
        error = body["error"]
        assert "field" in error, "Validation error must include 'field'"
        assert "message" in error, "Validation error must include 'message'"
        assert isinstance(error["field"], str) and len(error["field"]) > 0
        assert isinstance(error["message"], str) and len(error["message"]) > 0

    @settings(max_examples=100)
    @given(query=too_long_query_strategy)
    def test_too_long_query_returns_422_with_field_and_message(self, query):
        """Queries exceeding 2000 chars produce 422 with field name and rule."""
        response = client.post("/api/query", json={"query": query})

        assert response.status_code == 422
        body = response.json()
        error = body["error"]
        assert "field" in error, "Validation error must include 'field'"
        assert "message" in error, "Validation error must include 'message'"
        assert isinstance(error["field"], str) and len(error["field"]) > 0
        assert isinstance(error["message"], str) and len(error["message"]) > 0

    @settings(max_examples=100)
    @given(data=st.data())
    def test_missing_query_field_returns_422_with_field_and_message(self, data):
        """Missing required 'query' field produces 422 with field name and rule."""
        # Send a body without the 'query' field
        response = client.post("/api/query", json={})

        assert response.status_code == 422
        body = response.json()
        error = body["error"]
        assert "field" in error, "Validation error must include 'field'"
        assert "message" in error, "Validation error must include 'message'"
        assert isinstance(error["field"], str) and len(error["field"]) > 0
        assert isinstance(error["message"], str) and len(error["message"]) > 0

    @settings(max_examples=100)
    @given(start=st.just("2024-01-01"))
    def test_costs_partial_params_returns_422_with_field_and_message(self, start):
        """Costs endpoint with only 'start' (no 'end') produces 422."""
        response = client.get(f"/api/costs?start={start}")

        assert response.status_code == 422
        body = response.json()
        error = body["error"]
        assert "field" in error, "Validation error must include 'field'"
        assert "message" in error, "Validation error must include 'message'"
        assert isinstance(error["field"], str) and len(error["field"]) > 0
        assert isinstance(error["message"], str) and len(error["message"]) > 0


# ============================================================================
# Property 21: Downstream failure error responses
# ============================================================================


class TestDownstreamFailureErrorResponses:
    """Property 21: Downstream failure error responses.

    *For any* API request where a downstream service (AI Layer, Orchestrator, or
    Monitoring Layer) is unreachable or returns an error, the Backend SHALL return
    HTTP 502 with a JSON body identifying which specific service failed.

    **Validates: Requirements 10.7**
    """

    @settings(max_examples=100)
    @given(error_msg=error_message_strategy)
    def test_ai_layer_failure_returns_502_with_service_id(self, error_msg):
        """When AI Layer fails, 502 response identifies 'ai_layer' service."""
        with patch(
            "backend.api.routes.query._ai_layer.parse_intent",
            new_callable=AsyncMock,
            side_effect=Exception(error_msg),
        ):
            response = client.post("/api/query", json={"query": "start my AWS instance"})

        assert response.status_code == 502
        body = response.json()
        assert body["status"] == "error"
        error = body["error"]
        assert "service" in error, "502 error must identify the failed service"
        assert error["service"] == "ai_layer"
        assert "message" in error

    @settings(max_examples=100)
    @given(error_msg=error_message_strategy)
    def test_monitoring_layer_failure_on_status_returns_502(self, error_msg):
        """When monitoring layer fails on /api/status, 502 identifies service."""
        with patch(
            "backend.api.routes.status.monitoring_layer.get_resource_status",
            new_callable=AsyncMock,
            side_effect=Exception(error_msg),
        ):
            response = client.get("/api/status")

        assert response.status_code == 502
        body = response.json()
        assert body["status"] == "error"
        error = body["error"]
        assert "service" in error, "502 error must identify the failed service"
        assert error["service"] == "monitoring_layer"
        assert "message" in error

    @settings(max_examples=100)
    @given(error_msg=error_message_strategy)
    def test_monitoring_layer_failure_on_costs_returns_502(self, error_msg):
        """When monitoring layer fails on /api/costs, 502 identifies service."""
        with patch(
            "backend.api.routes.costs.monitoring_layer.get_costs",
            new_callable=AsyncMock,
            side_effect=Exception(error_msg),
        ):
            response = client.get("/api/costs")

        assert response.status_code == 502
        body = response.json()
        assert body["status"] == "error"
        error = body["error"]
        assert "service" in error, "502 error must identify the failed service"
        assert error["service"] == "monitoring_layer"
        assert "message" in error

    @settings(max_examples=100)
    @given(error_msg=error_message_strategy)
    def test_monitoring_layer_failure_on_recommendations_returns_502(self, error_msg):
        """When monitoring layer fails on /api/recommendations, 502 identifies service."""
        with patch(
            "backend.api.routes.recommendations._monitoring_layer.get_costs",
            new_callable=AsyncMock,
            side_effect=Exception(error_msg),
        ):
            response = client.get("/api/recommendations")

        assert response.status_code == 502
        body = response.json()
        assert body["status"] == "error"
        error = body["error"]
        assert "service" in error, "502 error must identify the failed service"
        assert "message" in error


# ============================================================================
# Property 22: CORS headers present
# ============================================================================


class TestCORSHeadersPresent:
    """Property 22: CORS headers present.

    *For any* HTTP response returned by the Backend API, the response SHALL include
    CORS headers permitting requests from the web frontend origin.

    **Validates: Requirements 10.8**
    """

    @settings(max_examples=100)
    @given(data=st.data())
    def test_cors_headers_on_successful_request(self, data):
        """Verify CORS headers present on successful responses."""
        response = client.get("/", headers={"Origin": "http://localhost:3000"})

        assert "access-control-allow-origin" in response.headers, (
            "CORS header 'access-control-allow-origin' must be present"
        )

    @settings(max_examples=100)
    @given(path=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1,
        max_size=30,
    ))
    def test_cors_headers_on_error_responses(self, path):
        """Verify CORS headers present on error (404) responses."""
        response = client.get(
            f"/api/nonexistent_{path}",
            headers={"Origin": "http://localhost:3000"},
        )

        assert "access-control-allow-origin" in response.headers, (
            "CORS header 'access-control-allow-origin' must be present"
        )

    @settings(max_examples=100)
    @given(query=empty_or_whitespace_strategy)
    def test_cors_headers_on_validation_errors(self, query):
        """Verify CORS headers present on 422 validation error responses."""
        response = client.post(
            "/api/query",
            json={"query": query},
            headers={"Origin": "http://localhost:3000"},
        )

        assert "access-control-allow-origin" in response.headers, (
            "CORS header 'access-control-allow-origin' must be present"
        )

    @settings(max_examples=100)
    @given(error_msg=error_message_strategy)
    def test_cors_headers_on_downstream_failure(self, error_msg):
        """Verify CORS headers present on 502 downstream failure responses."""
        with patch(
            "backend.api.routes.status.monitoring_layer.get_resource_status",
            new_callable=AsyncMock,
            side_effect=Exception(error_msg),
        ):
            response = client.get(
                "/api/status",
                headers={"Origin": "http://localhost:3000"},
            )

        assert "access-control-allow-origin" in response.headers, (
            "CORS header 'access-control-allow-origin' must be present"
        )
