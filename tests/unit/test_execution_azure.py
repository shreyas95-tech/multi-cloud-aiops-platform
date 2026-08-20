"""Unit tests for AzureProvider execution layer.

Tests cover:
- Start instance success (state="Running")
- Stop instance success (state="Deallocated")
- ResourceNotFoundError handling
- ClientAuthenticationError with subscription_id in error message
- HttpResponseError handling

Requirements: 4.1, 4.2, 4.6, 5.1, 5.2, 5.5, 5.6, 6.1, 6.2, 6.5, 6.6
"""

import pytest
from unittest.mock import MagicMock

from backend.execution.azure_provider import AzureProvider


@pytest.fixture
def mock_compute_client():
    """Create a mocked Azure ComputeManagementClient."""
    client = MagicMock()
    client.virtual_machines = MagicMock()
    return client


@pytest.fixture
def azure_provider(mock_compute_client):
    """Create an AzureProvider with the mocked compute client."""
    return AzureProvider(compute_client=mock_compute_client)


@pytest.fixture
def valid_params():
    """Common valid Azure parameters."""
    return {
        "subscription_id": "sub-12345-abcde",
        "resource_group": "my-resource-group",
        "vm_name": "my-vm-01",
    }


class ResourceNotFoundError(Exception):
    """Simulates azure.core.exceptions.ResourceNotFoundError."""

    pass


class ClientAuthenticationError(Exception):
    """Simulates azure.identity.ClientAuthenticationError."""

    pass


class HttpResponseError(Exception):
    """Simulates azure.core.exceptions.HttpResponseError."""

    def __init__(self, message="", error_code=None):
        super().__init__(message)
        self.error_code = error_code
        self.message = message


# Set the class names to match what the provider checks via type(error).__name__
ResourceNotFoundError.__name__ = "ResourceNotFoundError"
ClientAuthenticationError.__name__ = "ClientAuthenticationError"
HttpResponseError.__name__ = "HttpResponseError"


class TestAzureStartInstance:
    """Tests for AzureProvider.start_instance."""

    @pytest.mark.asyncio
    async def test_start_success(self, azure_provider, mock_compute_client, valid_params):
        """Start VM returns success with state='Running'."""
        mock_poller = MagicMock()
        mock_poller.result.return_value = None
        mock_compute_client.virtual_machines.begin_start.return_value = mock_poller

        result = await azure_provider.start_instance(valid_params)

        assert result["success"] is True
        assert result["provider"] == "Azure"
        assert result["resource_id"] == "my-vm-01"
        assert result["action"] == "start_instance"
        assert result["state"] == "Running"
        assert result["error_code"] is None
        assert result["error_message"] is None
        assert result["metadata"]["subscription_id"] == "sub-12345-abcde"
        assert result["metadata"]["resource_group"] == "my-resource-group"

        mock_compute_client.virtual_machines.begin_start.assert_called_once_with(
            "my-resource-group", "my-vm-01"
        )

    @pytest.mark.asyncio
    async def test_start_resource_not_found(self, azure_provider, mock_compute_client, valid_params):
        """Start VM with non-existent resource returns ResourceNotFound error."""
        mock_compute_client.virtual_machines.begin_start.side_effect = ResourceNotFoundError(
            "VM not found"
        )

        result = await azure_provider.start_instance(valid_params)

        assert result["success"] is False
        assert result["provider"] == "Azure"
        assert result["resource_id"] == "my-vm-01"
        assert result["action"] == "start_instance"
        assert result["state"] is None
        assert result["error_code"] == "ResourceNotFound"
        assert "my-vm-01" in result["error_message"]
        assert "my-resource-group" in result["error_message"]

    @pytest.mark.asyncio
    async def test_start_authentication_error(self, azure_provider, mock_compute_client, valid_params):
        """Start VM with auth failure includes subscription_id in error."""
        mock_compute_client.virtual_machines.begin_start.side_effect = ClientAuthenticationError(
            "Invalid credentials"
        )

        result = await azure_provider.start_instance(valid_params)

        assert result["success"] is False
        assert result["provider"] == "Azure"
        assert result["error_code"] == "AuthenticationFailure"
        assert "sub-12345-abcde" in result["error_message"]
        assert result["metadata"]["subscription_id"] == "sub-12345-abcde"

    @pytest.mark.asyncio
    async def test_start_http_response_error(self, azure_provider, mock_compute_client, valid_params):
        """Start VM with HTTP error returns structured error."""
        error = HttpResponseError(
            message="VM is already deallocating", error_code="ConflictError"
        )
        mock_compute_client.virtual_machines.begin_start.side_effect = error

        result = await azure_provider.start_instance(valid_params)

        assert result["success"] is False
        assert result["provider"] == "Azure"
        assert result["error_code"] == "ConflictError"
        assert "deallocating" in result["error_message"]

    @pytest.mark.asyncio
    async def test_start_missing_params(self, azure_provider):
        """Start VM with missing required params returns validation error."""
        result = await azure_provider.start_instance({"vm_name": "my-vm"})

        assert result["success"] is False
        assert result["error_code"] == "InvalidParameter"
        assert "subscription_id" in result["error_message"]
        assert "resource_group" in result["error_message"]


class TestAzureStopInstance:
    """Tests for AzureProvider.stop_instance."""

    @pytest.mark.asyncio
    async def test_stop_success(self, azure_provider, mock_compute_client, valid_params):
        """Stop (deallocate) VM returns success with state='Deallocated'."""
        mock_poller = MagicMock()
        mock_poller.result.return_value = None
        mock_compute_client.virtual_machines.begin_deallocate.return_value = mock_poller

        result = await azure_provider.stop_instance(valid_params)

        assert result["success"] is True
        assert result["provider"] == "Azure"
        assert result["resource_id"] == "my-vm-01"
        assert result["action"] == "stop_instance"
        assert result["state"] == "Deallocated"
        assert result["error_code"] is None
        assert result["error_message"] is None
        assert result["metadata"]["subscription_id"] == "sub-12345-abcde"
        assert result["metadata"]["resource_group"] == "my-resource-group"

        mock_compute_client.virtual_machines.begin_deallocate.assert_called_once_with(
            "my-resource-group", "my-vm-01"
        )

    @pytest.mark.asyncio
    async def test_stop_resource_not_found(self, azure_provider, mock_compute_client, valid_params):
        """Stop VM with non-existent resource returns ResourceNotFound error."""
        mock_compute_client.virtual_machines.begin_deallocate.side_effect = ResourceNotFoundError(
            "VM not found"
        )

        result = await azure_provider.stop_instance(valid_params)

        assert result["success"] is False
        assert result["provider"] == "Azure"
        assert result["resource_id"] == "my-vm-01"
        assert result["action"] == "stop_instance"
        assert result["state"] is None
        assert result["error_code"] == "ResourceNotFound"
        assert "my-vm-01" in result["error_message"]

    @pytest.mark.asyncio
    async def test_stop_authentication_error(self, azure_provider, mock_compute_client, valid_params):
        """Stop VM with auth failure includes subscription_id in error."""
        mock_compute_client.virtual_machines.begin_deallocate.side_effect = ClientAuthenticationError(
            "Expired token"
        )

        result = await azure_provider.stop_instance(valid_params)

        assert result["success"] is False
        assert result["provider"] == "Azure"
        assert result["error_code"] == "AuthenticationFailure"
        assert "sub-12345-abcde" in result["error_message"]
        assert result["metadata"]["subscription_id"] == "sub-12345-abcde"

    @pytest.mark.asyncio
    async def test_stop_http_response_error(self, azure_provider, mock_compute_client, valid_params):
        """Stop VM with HTTP error returns structured error."""
        error = HttpResponseError(
            message="Operation not allowed", error_code="OperationNotAllowed"
        )
        mock_compute_client.virtual_machines.begin_deallocate.side_effect = error

        result = await azure_provider.stop_instance(valid_params)

        assert result["success"] is False
        assert result["provider"] == "Azure"
        assert result["error_code"] == "OperationNotAllowed"

    @pytest.mark.asyncio
    async def test_stop_missing_params(self, azure_provider):
        """Stop VM with missing required params returns validation error."""
        result = await azure_provider.stop_instance({"subscription_id": "sub-123"})

        assert result["success"] is False
        assert result["error_code"] == "InvalidParameter"
        assert "resource_group" in result["error_message"]
        assert "vm_name" in result["error_message"]
