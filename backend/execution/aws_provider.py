"""AWS cloud provider implementation using boto3 EC2 client.

This module provides the AWSProvider class that implements the CloudProvider
interface for AWS EC2 instance management. It supports starting and stopping
EC2 instances with proper validation, error handling, and already-in-state
detection.
"""

import re
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from backend.execution.base import CloudProvider


# Valid EC2 instance ID pattern: i- followed by 1-17 hex characters
INSTANCE_ID_PATTERN = re.compile(r"^i-[0-9a-f]{1,17}$")


class AWSProvider(CloudProvider):
    """AWS EC2 cloud provider implementation.

    Implements start_instance and stop_instance operations via the boto3
    EC2 client. Validates instance ID format before making API calls and
    handles already-in-state scenarios gracefully.

    Args:
        ec2_client: Optional boto3 EC2 client for dependency injection.
            If not provided, a new client is created with default credentials.
    """

    def __init__(self, ec2_client=None):
        if ec2_client is not None:
            self._ec2_client = ec2_client
        else:
            self._ec2_client = boto3.client("ec2")

    def _validate_instance_id(self, instance_id: Optional[str]) -> Optional[dict]:
        """Validate EC2 instance ID format.

        Args:
            instance_id: The instance ID to validate.

        Returns:
            An error dict if validation fails, None if valid.
        """
        if not instance_id:
            return {
                "success": False,
                "provider": "AWS",
                "resource_id": instance_id or "",
                "action": "",
                "state": None,
                "error_code": "InvalidParameterValue",
                "error_message": "Missing required parameter: instance_id",
                "metadata": {},
            }

        if not INSTANCE_ID_PATTERN.match(instance_id):
            return {
                "success": False,
                "provider": "AWS",
                "resource_id": instance_id,
                "action": "",
                "state": None,
                "error_code": "InvalidInstanceID.Malformed",
                "error_message": (
                    f"Invalid instance ID format: '{instance_id}'. "
                    f"Expected format: i-[0-9a-f]{{1,17}}"
                ),
                "metadata": {},
            }

        return None

    async def start_instance(self, params: dict) -> dict:
        """Start an AWS EC2 instance.

        Args:
            params: Dict with "instance_id" key containing a valid EC2 instance ID.

        Returns:
            Dict conforming to ExecutionResult fields with operation outcome.
        """
        instance_id = params.get("instance_id")
        action = "start_instance"

        # Validate instance ID format
        validation_error = self._validate_instance_id(instance_id)
        if validation_error is not None:
            validation_error["action"] = action
            return validation_error

        try:
            response = self._ec2_client.start_instances(
                InstanceIds=[instance_id]
            )

            # Extract state change info from response
            starting_instances = response.get("StartingInstances", [])
            if starting_instances:
                state_change = starting_instances[0]
                current_state = state_change.get("CurrentState", {}).get("Name", "pending")
                previous_state = state_change.get("PreviousState", {}).get("Name", "unknown")

                # Handle already-in-state scenario
                if previous_state in ("running", "pending"):
                    return {
                        "success": True,
                        "provider": "AWS",
                        "resource_id": instance_id,
                        "action": action,
                        "state": current_state,
                        "error_code": None,
                        "error_message": None,
                        "metadata": {
                            "previous_state": previous_state,
                            "already_in_desired_state": True,
                        },
                    }

                return {
                    "success": True,
                    "provider": "AWS",
                    "resource_id": instance_id,
                    "action": action,
                    "state": current_state,
                    "error_code": None,
                    "error_message": None,
                    "metadata": {
                        "previous_state": previous_state,
                        "already_in_desired_state": False,
                    },
                }

            # Unexpected empty response
            return {
                "success": True,
                "provider": "AWS",
                "resource_id": instance_id,
                "action": action,
                "state": "pending",
                "error_code": None,
                "error_message": None,
                "metadata": {},
            }

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"]["Message"]

            return {
                "success": False,
                "provider": "AWS",
                "resource_id": instance_id,
                "action": action,
                "state": None,
                "error_code": error_code,
                "error_message": error_message,
                "metadata": {
                    "aws_request_id": e.response.get("ResponseMetadata", {}).get(
                        "RequestId", ""
                    ),
                },
            }

    async def stop_instance(self, params: dict) -> dict:
        """Stop an AWS EC2 instance.

        Args:
            params: Dict with "instance_id" key containing a valid EC2 instance ID.

        Returns:
            Dict conforming to ExecutionResult fields with operation outcome.
        """
        instance_id = params.get("instance_id")
        action = "stop_instance"

        # Validate instance ID format
        validation_error = self._validate_instance_id(instance_id)
        if validation_error is not None:
            validation_error["action"] = action
            return validation_error

        try:
            response = self._ec2_client.stop_instances(
                InstanceIds=[instance_id]
            )

            # Extract state change info from response
            stopping_instances = response.get("StoppingInstances", [])
            if stopping_instances:
                state_change = stopping_instances[0]
                current_state = state_change.get("CurrentState", {}).get("Name", "stopping")
                previous_state = state_change.get("PreviousState", {}).get("Name", "unknown")

                # Handle already-in-state scenario
                if previous_state in ("stopped", "stopping"):
                    return {
                        "success": True,
                        "provider": "AWS",
                        "resource_id": instance_id,
                        "action": action,
                        "state": current_state,
                        "error_code": None,
                        "error_message": None,
                        "metadata": {
                            "previous_state": previous_state,
                            "already_in_desired_state": True,
                        },
                    }

                return {
                    "success": True,
                    "provider": "AWS",
                    "resource_id": instance_id,
                    "action": action,
                    "state": current_state,
                    "error_code": None,
                    "error_message": None,
                    "metadata": {
                        "previous_state": previous_state,
                        "already_in_desired_state": False,
                    },
                }

            # Unexpected empty response
            return {
                "success": True,
                "provider": "AWS",
                "resource_id": instance_id,
                "action": action,
                "state": "stopping",
                "error_code": None,
                "error_message": None,
                "metadata": {},
            }

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"]["Message"]

            return {
                "success": False,
                "provider": "AWS",
                "resource_id": instance_id,
                "action": action,
                "state": None,
                "error_code": error_code,
                "error_message": error_message,
                "metadata": {
                    "aws_request_id": e.response.get("ResponseMetadata", {}).get(
                        "RequestId", ""
                    ),
                },
            }
