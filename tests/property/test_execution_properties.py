"""Property-based tests for Execution Layer.

Validates: Requirements 4.3, 4.4, 4.5, 4.7, 5.3, 5.4, 5.7, 6.3, 6.4, 6.7
"""

import re
from unittest.mock import AsyncMock, MagicMock, patch

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from backend.execution.aws_provider import AWSProvider
from backend.execution.azure_provider import AzureProvider
from backend.execution.gcp_provider import GCPProvider

# --- Strategies ---

# Strategy for error codes (non-empty strings representing provider error codes)
error_code_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
    min_size=1,
    max_size=50,
)

# Strategy for human-readable error messages
error_message_strategy = st.text(min_size=1, max_size=200).filter(
    lambda s: s.strip() != ""
)

# Strategy for resource IDs (non-empty strings)
resource_id_strategy = st.text(min_size=1, max_size=50).filter(
    lambda s: s.strip() != ""
)

# Strategy for providers
provider_strategy = st.sampled_from(["AWS", "Azure", "GCP"])

# Strategy for actions
action_strategy = st.sampled_from(["start_instance", "stop_instance"])

# AWS success states for start
aws_start_states = st.sampled_from(["pending", "running"])
# AWS success states for stop
aws_stop_states = st.sampled_from(["stopping", "stopped"])
# Azure states
azure_states = st.sampled_from(["Running", "Deallocated"])
# GCP states
gcp_states = st.sampled_from(["RUNNING", "TERMINATED"])

# Valid AWS instance IDs for success testing
valid_aws_instance_id_strategy = st.from_regex(r"i-[0-9a-f]{1,17}", fullmatch=True)

# Strategy for strings that do NOT match `i-[0-9a-f]{1,17}`
INSTANCE_ID_PATTERN = re.compile(r"^i-[0-9a-f]{1,17}$")

invalid_aws_instance_id_strategy = st.text(min_size=1, max_size=50).filter(
    lambda s: not INSTANCE_ID_PATTERN.match(s)
)


# --- Property 10: Execution error response structure (cross-provider) ---


class TestProperty10ExecutionErrorResponseStructure:
    """Property 10: Execution error response structure (cross-provider).

    For any cloud API failure across AWS, Azure, or GCP, the Execution Layer
    SHALL return a structured error response containing the provider-specific
    error code, a human-readable error message, and the resource identifier
    that was targeted.

    **Validates: Requirements 4.3, 5.3, 6.3**
    """

    @settings(max_examples=100)
    @given(
        error_code=error_code_strategy,
        error_message=error_message_strategy,
        instance_id=valid_aws_instance_id_strategy,
    )
    @pytest.mark.asyncio
    async def test_aws_error_response_structure(
        self, error_code: str, error_message: str, instance_id: str
    ) -> None:
        """AWS error responses contain error_code, error_message, and resource_id."""
        # Mock EC2 client to raise a ClientError
        mock_ec2 = MagicMock()
        mock_ec2.start_instances.side_effect = _make_boto3_client_error(
            error_code, error_message
        )

        provider = AWSProvider(ec2_client=mock_ec2)
        result = await provider.start_instance({"instance_id": instance_id})

        # Verify structured error response
        assert result["success"] is False
        assert result["error_code"] is not None
        assert result["error_code"] == error_code
        assert result["error_message"] is not None
        assert result["error_message"] == error_message
        assert result["resource_id"] == instance_id

    @settings(max_examples=100)
    @given(
        error_message=error_message_strategy,
        vm_name=resource_id_strategy,
        subscription_id=resource_id_strategy,
        resource_group=resource_id_strategy,
    )
    @pytest.mark.asyncio
    async def test_azure_error_response_structure(
        self,
        error_message: str,
        vm_name: str,
        subscription_id: str,
        resource_group: str,
    ) -> None:
        """Azure error responses contain error_code, error_message, and resource_id."""
        # Create a custom exception class that mimics Azure's HttpResponseError
        mock_error = _AzureHttpResponseError(error_message)

        mock_client = MagicMock()
        mock_client.virtual_machines.begin_start.side_effect = mock_error

        provider = AzureProvider(compute_client=mock_client)
        result = await provider.start_instance({
            "subscription_id": subscription_id,
            "resource_group": resource_group,
            "vm_name": vm_name,
        })

        # Verify structured error response
        assert result["success"] is False
        assert result["error_code"] is not None
        assert result["error_message"] is not None
        assert result["resource_id"] == vm_name

    @settings(max_examples=100)
    @given(
        error_message=error_message_strategy,
        instance_name=resource_id_strategy,
        project_id=resource_id_strategy,
        zone=resource_id_strategy,
    )
    @pytest.mark.asyncio
    async def test_gcp_error_response_structure(
        self,
        error_message: str,
        instance_name: str,
        project_id: str,
        zone: str,
    ) -> None:
        """GCP error responses contain error_code, error_message, and resource_id."""
        from google.api_core.exceptions import GoogleAPICallError

        mock_client = MagicMock()
        gcp_error = GoogleAPICallError(error_message)
        gcp_error.grpc_status_code = None
        mock_client.start.side_effect = gcp_error

        provider = GCPProvider(instances_client=mock_client)
        result = await provider.start_instance({
            "project_id": project_id,
            "zone": zone,
            "instance_name": instance_name,
        })

        # Verify structured error response
        assert result["success"] is False
        assert result["error_code"] is not None
        assert result["error_message"] is not None
        assert result["resource_id"] == instance_name


# --- Property 11: Execution success response structure (cross-provider) ---


class TestProperty11ExecutionSuccessResponseStructure:
    """Property 11: Execution success response structure (cross-provider).

    For any successful cloud operation across AWS, Azure, or GCP, the Execution Layer
    SHALL return a confirmation response containing the resource identifier and the
    new resource state, conforming to the common ExecutionResult interface.

    **Validates: Requirements 4.4, 4.7, 5.4, 5.7, 6.4, 6.7**
    """

    @settings(max_examples=100)
    @given(
        instance_id=valid_aws_instance_id_strategy,
        state=aws_start_states,
    )
    @pytest.mark.asyncio
    async def test_aws_success_response_structure(
        self, instance_id: str, state: str
    ) -> None:
        """AWS success responses contain resource_id and new state."""
        mock_ec2 = MagicMock()
        mock_ec2.start_instances.return_value = {
            "StartingInstances": [
                {
                    "CurrentState": {"Name": state},
                    "PreviousState": {"Name": "stopped"},
                }
            ]
        }

        provider = AWSProvider(ec2_client=mock_ec2)
        result = await provider.start_instance({"instance_id": instance_id})

        # Verify success response structure
        assert result["success"] is True
        assert result["resource_id"] == instance_id
        assert result["resource_id"] != ""
        assert result["state"] is not None
        assert result["state"] == state
        assert result["provider"] == "AWS"
        assert result["error_code"] is None
        assert result["error_message"] is None

    @settings(max_examples=100)
    @given(
        vm_name=resource_id_strategy,
        subscription_id=resource_id_strategy,
        resource_group=resource_id_strategy,
    )
    @pytest.mark.asyncio
    async def test_azure_success_response_structure(
        self, vm_name: str, subscription_id: str, resource_group: str
    ) -> None:
        """Azure success responses contain resource_id and new state."""
        mock_client = MagicMock()
        mock_poller = MagicMock()
        mock_poller.result.return_value = None
        mock_client.virtual_machines.begin_start.return_value = mock_poller

        provider = AzureProvider(compute_client=mock_client)
        result = await provider.start_instance({
            "subscription_id": subscription_id,
            "resource_group": resource_group,
            "vm_name": vm_name,
        })

        # Verify success response structure
        assert result["success"] is True
        assert result["resource_id"] == vm_name
        assert result["resource_id"] != ""
        assert result["state"] is not None
        assert result["state"] == "Running"
        assert result["provider"] == "Azure"
        assert result["error_code"] is None
        assert result["error_message"] is None

    @settings(max_examples=100)
    @given(
        instance_name=resource_id_strategy,
        project_id=resource_id_strategy,
        zone=resource_id_strategy,
    )
    @pytest.mark.asyncio
    async def test_gcp_success_response_structure(
        self, instance_name: str, project_id: str, zone: str
    ) -> None:
        """GCP success responses contain resource_id and new state."""
        mock_client = MagicMock()
        mock_operation = MagicMock()
        mock_operation.result.return_value = None
        mock_client.start.return_value = mock_operation

        provider = GCPProvider(instances_client=mock_client)
        result = await provider.start_instance({
            "project_id": project_id,
            "zone": zone,
            "instance_name": instance_name,
        })

        # Verify success response structure
        assert result["success"] is True
        assert result["resource_id"] == instance_name
        assert result["resource_id"] != ""
        assert result["state"] is not None
        assert result["state"] == "RUNNING"
        assert result["provider"] == "GCP"
        assert result["error_code"] is None
        assert result["error_message"] is None


# --- Property 12: AWS instance ID format validation ---


class TestProperty12AWSInstanceIDFormatValidation:
    """Property 12: AWS instance ID format validation.

    For any string that does not match the pattern `i-[0-9a-f]{1,17}`, the AWS
    Execution Layer SHALL reject it with a structured error indicating invalid
    instance ID format, without making any API call to AWS.

    **Validates: Requirements 4.5**
    """

    @settings(max_examples=100)
    @given(invalid_id=invalid_aws_instance_id_strategy)
    @pytest.mark.asyncio
    async def test_invalid_ids_rejected_on_start(self, invalid_id: str) -> None:
        """Invalid instance IDs are rejected by start_instance without API call."""
        mock_ec2 = MagicMock()

        provider = AWSProvider(ec2_client=mock_ec2)
        result = await provider.start_instance({"instance_id": invalid_id})

        # Verify rejection with structured error
        assert result["success"] is False
        assert result["error_code"] is not None
        assert "Invalid" in result["error_code"] or "invalid" in result["error_message"].lower()
        assert result["resource_id"] == invalid_id

        # Verify NO API call was made
        mock_ec2.start_instances.assert_not_called()
        mock_ec2.stop_instances.assert_not_called()

    @settings(max_examples=100)
    @given(invalid_id=invalid_aws_instance_id_strategy)
    @pytest.mark.asyncio
    async def test_invalid_ids_rejected_on_stop(self, invalid_id: str) -> None:
        """Invalid instance IDs are rejected by stop_instance without API call."""
        mock_ec2 = MagicMock()

        provider = AWSProvider(ec2_client=mock_ec2)
        result = await provider.stop_instance({"instance_id": invalid_id})

        # Verify rejection with structured error
        assert result["success"] is False
        assert result["error_code"] is not None
        assert "Invalid" in result["error_code"] or "invalid" in result["error_message"].lower()
        assert result["resource_id"] == invalid_id

        # Verify NO API call was made
        mock_ec2.start_instances.assert_not_called()
        mock_ec2.stop_instances.assert_not_called()


# --- Helpers ---


class _AzureHttpResponseError(Exception):
    """Mock Azure HttpResponseError for testing.

    Named 'HttpResponseError' to trigger the Azure provider's error handling
    logic which checks type(error).__name__.
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.error_code = "AzureHttpError"
        self.message = message


# Rename to match what Azure provider checks via type(error).__name__
_AzureHttpResponseError.__name__ = "HttpResponseError"


def _make_boto3_client_error(error_code: str, error_message: str):
    """Create a botocore ClientError for testing."""
    from botocore.exceptions import ClientError

    error_response = {
        "Error": {
            "Code": error_code,
            "Message": error_message,
        },
        "ResponseMetadata": {
            "RequestId": "test-request-id-12345",
        },
    }
    return ClientError(error_response, "StartInstances")
