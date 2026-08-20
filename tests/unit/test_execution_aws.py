"""Unit tests for AWSProvider execution layer.

Tests cover:
- Start instance success with state transition
- Stop instance success with state transition
- ClientError handling (e.g., instance not found)
- Invalid instance ID format rejection
- Already-running (start) and already-stopped (stop) scenarios

Requirements: 4.1, 4.2, 4.6, 5.1, 5.2, 5.5, 5.6, 6.1, 6.2, 6.5, 6.6
"""

import pytest
from unittest.mock import MagicMock
from botocore.exceptions import ClientError

from backend.execution.aws_provider import AWSProvider


@pytest.fixture
def mock_ec2_client():
    """Create a mocked boto3 EC2 client."""
    return MagicMock()


@pytest.fixture
def aws_provider(mock_ec2_client):
    """Create an AWSProvider with the mocked EC2 client."""
    return AWSProvider(ec2_client=mock_ec2_client)


class TestAWSStartInstance:
    """Tests for AWSProvider.start_instance."""

    @pytest.mark.asyncio
    async def test_start_success(self, aws_provider, mock_ec2_client):
        """Start instance returns success with new state."""
        mock_ec2_client.start_instances.return_value = {
            "StartingInstances": [
                {
                    "InstanceId": "i-1234567890abcdef0",
                    "CurrentState": {"Code": 0, "Name": "pending"},
                    "PreviousState": {"Code": 80, "Name": "stopped"},
                }
            ]
        }

        result = await aws_provider.start_instance({"instance_id": "i-1234567890abcdef0"})

        assert result["success"] is True
        assert result["provider"] == "AWS"
        assert result["resource_id"] == "i-1234567890abcdef0"
        assert result["action"] == "start_instance"
        assert result["state"] == "pending"
        assert result["error_code"] is None
        assert result["error_message"] is None
        assert result["metadata"]["previous_state"] == "stopped"
        assert result["metadata"]["already_in_desired_state"] is False

        mock_ec2_client.start_instances.assert_called_once_with(
            InstanceIds=["i-1234567890abcdef0"]
        )

    @pytest.mark.asyncio
    async def test_start_already_running(self, aws_provider, mock_ec2_client):
        """Start instance when already running returns success with already_in_desired_state."""
        mock_ec2_client.start_instances.return_value = {
            "StartingInstances": [
                {
                    "InstanceId": "i-abc123",
                    "CurrentState": {"Code": 16, "Name": "running"},
                    "PreviousState": {"Code": 16, "Name": "running"},
                }
            ]
        }

        result = await aws_provider.start_instance({"instance_id": "i-abc123"})

        assert result["success"] is True
        assert result["state"] == "running"
        assert result["metadata"]["previous_state"] == "running"
        assert result["metadata"]["already_in_desired_state"] is True

    @pytest.mark.asyncio
    async def test_start_already_pending(self, aws_provider, mock_ec2_client):
        """Start instance when already pending returns success with already_in_desired_state."""
        mock_ec2_client.start_instances.return_value = {
            "StartingInstances": [
                {
                    "InstanceId": "i-abc123",
                    "CurrentState": {"Code": 0, "Name": "pending"},
                    "PreviousState": {"Code": 0, "Name": "pending"},
                }
            ]
        }

        result = await aws_provider.start_instance({"instance_id": "i-abc123"})

        assert result["success"] is True
        assert result["metadata"]["already_in_desired_state"] is True

    @pytest.mark.asyncio
    async def test_start_client_error(self, aws_provider, mock_ec2_client):
        """Start instance with ClientError returns structured error."""
        mock_ec2_client.start_instances.side_effect = ClientError(
            error_response={
                "Error": {
                    "Code": "InvalidInstanceID.NotFound",
                    "Message": "The instance ID 'i-abc123' does not exist",
                },
                "ResponseMetadata": {"RequestId": "req-12345"},
            },
            operation_name="StartInstances",
        )

        result = await aws_provider.start_instance({"instance_id": "i-abc123"})

        assert result["success"] is False
        assert result["provider"] == "AWS"
        assert result["resource_id"] == "i-abc123"
        assert result["action"] == "start_instance"
        assert result["state"] is None
        assert result["error_code"] == "InvalidInstanceID.NotFound"
        assert "does not exist" in result["error_message"]
        assert result["metadata"]["aws_request_id"] == "req-12345"

    @pytest.mark.asyncio
    async def test_start_invalid_instance_id_format(self, aws_provider, mock_ec2_client):
        """Start instance with invalid ID format rejects without API call."""
        result = await aws_provider.start_instance({"instance_id": "invalid-id"})

        assert result["success"] is False
        assert result["error_code"] == "InvalidInstanceID.Malformed"
        assert "Invalid instance ID format" in result["error_message"]
        mock_ec2_client.start_instances.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_missing_instance_id(self, aws_provider, mock_ec2_client):
        """Start instance with missing instance_id rejects without API call."""
        result = await aws_provider.start_instance({})

        assert result["success"] is False
        assert result["error_code"] == "InvalidParameterValue"
        assert "Missing required parameter" in result["error_message"]
        mock_ec2_client.start_instances.assert_not_called()


class TestAWSStopInstance:
    """Tests for AWSProvider.stop_instance."""

    @pytest.mark.asyncio
    async def test_stop_success(self, aws_provider, mock_ec2_client):
        """Stop instance returns success with new state."""
        mock_ec2_client.stop_instances.return_value = {
            "StoppingInstances": [
                {
                    "InstanceId": "i-1234567890abcdef0",
                    "CurrentState": {"Code": 64, "Name": "stopping"},
                    "PreviousState": {"Code": 16, "Name": "running"},
                }
            ]
        }

        result = await aws_provider.stop_instance({"instance_id": "i-1234567890abcdef0"})

        assert result["success"] is True
        assert result["provider"] == "AWS"
        assert result["resource_id"] == "i-1234567890abcdef0"
        assert result["action"] == "stop_instance"
        assert result["state"] == "stopping"
        assert result["error_code"] is None
        assert result["error_message"] is None
        assert result["metadata"]["previous_state"] == "running"
        assert result["metadata"]["already_in_desired_state"] is False

        mock_ec2_client.stop_instances.assert_called_once_with(
            InstanceIds=["i-1234567890abcdef0"]
        )

    @pytest.mark.asyncio
    async def test_stop_already_stopped(self, aws_provider, mock_ec2_client):
        """Stop instance when already stopped returns success with already_in_desired_state."""
        mock_ec2_client.stop_instances.return_value = {
            "StoppingInstances": [
                {
                    "InstanceId": "i-abc123",
                    "CurrentState": {"Code": 80, "Name": "stopped"},
                    "PreviousState": {"Code": 80, "Name": "stopped"},
                }
            ]
        }

        result = await aws_provider.stop_instance({"instance_id": "i-abc123"})

        assert result["success"] is True
        assert result["state"] == "stopped"
        assert result["metadata"]["previous_state"] == "stopped"
        assert result["metadata"]["already_in_desired_state"] is True

    @pytest.mark.asyncio
    async def test_stop_already_stopping(self, aws_provider, mock_ec2_client):
        """Stop instance when already stopping returns success with already_in_desired_state."""
        mock_ec2_client.stop_instances.return_value = {
            "StoppingInstances": [
                {
                    "InstanceId": "i-abc123",
                    "CurrentState": {"Code": 64, "Name": "stopping"},
                    "PreviousState": {"Code": 64, "Name": "stopping"},
                }
            ]
        }

        result = await aws_provider.stop_instance({"instance_id": "i-abc123"})

        assert result["success"] is True
        assert result["metadata"]["already_in_desired_state"] is True

    @pytest.mark.asyncio
    async def test_stop_client_error(self, aws_provider, mock_ec2_client):
        """Stop instance with ClientError returns structured error."""
        mock_ec2_client.stop_instances.side_effect = ClientError(
            error_response={
                "Error": {
                    "Code": "IncorrectInstanceState",
                    "Message": "Instance is in terminated state",
                },
                "ResponseMetadata": {"RequestId": "req-67890"},
            },
            operation_name="StopInstances",
        )

        result = await aws_provider.stop_instance({"instance_id": "i-abc123"})

        assert result["success"] is False
        assert result["provider"] == "AWS"
        assert result["resource_id"] == "i-abc123"
        assert result["action"] == "stop_instance"
        assert result["state"] is None
        assert result["error_code"] == "IncorrectInstanceState"
        assert "terminated" in result["error_message"]
        assert result["metadata"]["aws_request_id"] == "req-67890"

    @pytest.mark.asyncio
    async def test_stop_invalid_instance_id_format(self, aws_provider, mock_ec2_client):
        """Stop instance with invalid ID format rejects without API call."""
        result = await aws_provider.stop_instance({"instance_id": "vm-12345"})

        assert result["success"] is False
        assert result["error_code"] == "InvalidInstanceID.Malformed"
        assert "Invalid instance ID format" in result["error_message"]
        mock_ec2_client.stop_instances.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_missing_instance_id(self, aws_provider, mock_ec2_client):
        """Stop instance with missing instance_id rejects without API call."""
        result = await aws_provider.stop_instance({"instance_id": ""})

        assert result["success"] is False
        assert result["error_code"] == "InvalidParameterValue"
        mock_ec2_client.stop_instances.assert_not_called()
