"""Unit tests for GCPProvider execution layer.

Tests cover:
- Start instance success (state="RUNNING")
- Stop instance success (state="TERMINATED")
- NotFound error handling
- DefaultCredentialsError with project_id in error message
- GoogleAPICallError handling

Requirements: 4.1, 4.2, 4.6, 5.1, 5.2, 5.5, 5.6, 6.1, 6.2, 6.5, 6.6
"""

import pytest
from unittest.mock import MagicMock, patch

from google.api_core.exceptions import NotFound, GoogleAPICallError
from google.auth.exceptions import DefaultCredentialsError

from backend.execution.gcp_provider import GCPProvider


@pytest.fixture
def mock_instances_client():
    """Create a mocked GCP InstancesClient."""
    return MagicMock()


@pytest.fixture
def gcp_provider(mock_instances_client):
    """Create a GCPProvider with the mocked instances client."""
    return GCPProvider(instances_client=mock_instances_client)


@pytest.fixture
def valid_params():
    """Common valid GCP parameters."""
    return {
        "project_id": "my-gcp-project",
        "zone": "us-central1-a",
        "instance_name": "my-instance-01",
    }


class TestGCPStartInstance:
    """Tests for GCPProvider.start_instance."""

    @pytest.mark.asyncio
    async def test_start_success(self, gcp_provider, mock_instances_client, valid_params):
        """Start instance returns success with state='RUNNING'."""
        mock_operation = MagicMock()
        mock_operation.result.return_value = None
        mock_instances_client.start.return_value = mock_operation

        result = await gcp_provider.start_instance(valid_params)

        assert result["success"] is True
        assert result["provider"] == "GCP"
        assert result["resource_id"] == "my-instance-01"
        assert result["action"] == "start_instance"
        assert result["state"] == "RUNNING"
        assert result["error_code"] is None
        assert result["error_message"] is None
        assert result["metadata"]["project_id"] == "my-gcp-project"
        assert result["metadata"]["zone"] == "us-central1-a"

        mock_instances_client.start.assert_called_once_with(
            project="my-gcp-project", zone="us-central1-a", instance="my-instance-01"
        )

    @pytest.mark.asyncio
    async def test_start_not_found(self, gcp_provider, mock_instances_client, valid_params):
        """Start instance with non-existent resource returns ResourceNotFound error."""
        mock_instances_client.start.side_effect = NotFound("Instance not found")

        result = await gcp_provider.start_instance(valid_params)

        assert result["success"] is False
        assert result["provider"] == "GCP"
        assert result["resource_id"] == "my-instance-01"
        assert result["action"] == "start_instance"
        assert result["state"] is None
        assert result["error_code"] == "ResourceNotFound"
        assert "my-instance-01" in result["error_message"]
        assert "my-gcp-project" in result["error_message"]
        assert "us-central1-a" in result["error_message"]

    @pytest.mark.asyncio
    async def test_start_credentials_error(self, gcp_provider, mock_instances_client, valid_params):
        """Start instance with auth failure includes project_id in error."""
        mock_instances_client.start.side_effect = DefaultCredentialsError(
            "Could not automatically determine credentials"
        )

        result = await gcp_provider.start_instance(valid_params)

        assert result["success"] is False
        assert result["provider"] == "GCP"
        assert result["error_code"] == "AuthenticationFailure"
        assert "my-gcp-project" in result["error_message"]
        assert result["metadata"]["project_id"] == "my-gcp-project"

    @pytest.mark.asyncio
    async def test_start_google_api_error(self, gcp_provider, mock_instances_client, valid_params):
        """Start instance with GoogleAPICallError returns structured error."""
        error = GoogleAPICallError("Quota exceeded")
        error._grpc_status_code = None  # Simulate no gRPC code
        # GoogleAPICallError.grpc_status_code is a property, so we mock it
        mock_instances_client.start.side_effect = error

        result = await gcp_provider.start_instance(valid_params)

        assert result["success"] is False
        assert result["provider"] == "GCP"
        assert result["resource_id"] == "my-instance-01"
        assert result["metadata"]["project_id"] == "my-gcp-project"

    @pytest.mark.asyncio
    async def test_start_missing_params(self, gcp_provider, mock_instances_client):
        """Start instance with missing required params returns validation error."""
        result = await gcp_provider.start_instance({"project_id": "proj"})

        assert result["success"] is False
        assert result["error_code"] == "InvalidParameterValue"
        assert "zone" in result["error_message"]
        assert "instance_name" in result["error_message"]
        mock_instances_client.start.assert_not_called()


class TestGCPStopInstance:
    """Tests for GCPProvider.stop_instance."""

    @pytest.mark.asyncio
    async def test_stop_success(self, gcp_provider, mock_instances_client, valid_params):
        """Stop instance returns success with state='TERMINATED'."""
        mock_operation = MagicMock()
        mock_operation.result.return_value = None
        mock_instances_client.stop.return_value = mock_operation

        result = await gcp_provider.stop_instance(valid_params)

        assert result["success"] is True
        assert result["provider"] == "GCP"
        assert result["resource_id"] == "my-instance-01"
        assert result["action"] == "stop_instance"
        assert result["state"] == "TERMINATED"
        assert result["error_code"] is None
        assert result["error_message"] is None
        assert result["metadata"]["project_id"] == "my-gcp-project"
        assert result["metadata"]["zone"] == "us-central1-a"

        mock_instances_client.stop.assert_called_once_with(
            project="my-gcp-project", zone="us-central1-a", instance="my-instance-01"
        )

    @pytest.mark.asyncio
    async def test_stop_not_found(self, gcp_provider, mock_instances_client, valid_params):
        """Stop instance with non-existent resource returns ResourceNotFound error."""
        mock_instances_client.stop.side_effect = NotFound("Instance not found")

        result = await gcp_provider.stop_instance(valid_params)

        assert result["success"] is False
        assert result["provider"] == "GCP"
        assert result["resource_id"] == "my-instance-01"
        assert result["action"] == "stop_instance"
        assert result["state"] is None
        assert result["error_code"] == "ResourceNotFound"
        assert "my-instance-01" in result["error_message"]
        assert "my-gcp-project" in result["error_message"]

    @pytest.mark.asyncio
    async def test_stop_credentials_error(self, gcp_provider, mock_instances_client, valid_params):
        """Stop instance with auth failure includes project_id in error."""
        mock_instances_client.stop.side_effect = DefaultCredentialsError(
            "Application default credentials are not available"
        )

        result = await gcp_provider.stop_instance(valid_params)

        assert result["success"] is False
        assert result["provider"] == "GCP"
        assert result["error_code"] == "AuthenticationFailure"
        assert "my-gcp-project" in result["error_message"]
        assert result["metadata"]["project_id"] == "my-gcp-project"

    @pytest.mark.asyncio
    async def test_stop_google_api_error(self, gcp_provider, mock_instances_client, valid_params):
        """Stop instance with GoogleAPICallError returns structured error."""
        error = GoogleAPICallError("Permission denied")
        error._grpc_status_code = None
        mock_instances_client.stop.side_effect = error

        result = await gcp_provider.stop_instance(valid_params)

        assert result["success"] is False
        assert result["provider"] == "GCP"
        assert result["resource_id"] == "my-instance-01"

    @pytest.mark.asyncio
    async def test_stop_missing_params(self, gcp_provider, mock_instances_client):
        """Stop instance with missing required params returns validation error."""
        result = await gcp_provider.stop_instance({"zone": "us-east1-b"})

        assert result["success"] is False
        assert result["error_code"] == "InvalidParameterValue"
        assert "project_id" in result["error_message"]
        assert "instance_name" in result["error_message"]
        mock_instances_client.stop.assert_not_called()
