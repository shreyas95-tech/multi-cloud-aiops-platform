"""GCP cloud provider implementation using google-cloud-compute SDK.

This module provides the GCPProvider class that implements the CloudProvider
interface for GCP Compute Engine instance management. It supports starting
and stopping instances with proper validation, error handling, and
authentication failure reporting.
"""

from google.cloud import compute_v1
from google.api_core.exceptions import NotFound, GoogleAPICallError
from google.auth.exceptions import DefaultCredentialsError, RefreshError

from backend.execution.base import CloudProvider


class GCPProvider(CloudProvider):
    """GCP Compute Engine cloud provider implementation.

    Implements start_instance and stop_instance operations via the
    google-cloud-compute SDK. Validates required parameters before making
    API calls and handles authentication failures and resource-not-found
    scenarios with structured error responses.

    Args:
        instances_client: Optional google.cloud.compute_v1.InstancesClient
            for dependency injection. If not provided, a new client is created
            with default credentials.
    """

    def __init__(self, instances_client=None):
        if instances_client is not None:
            self._instances_client = instances_client
        else:
            self._instances_client = compute_v1.InstancesClient()

    def _validate_params(self, params: dict, action: str) -> dict | None:
        """Validate required GCP parameters are present.

        Args:
            params: The parameters dict to validate.
            action: The action name for error reporting.

        Returns:
            An error dict if validation fails, None if all params are present.
        """
        required_fields = ["project_id", "zone", "instance_name"]
        missing = [f for f in required_fields if not params.get(f)]

        if missing:
            return {
                "success": False,
                "provider": "GCP",
                "resource_id": params.get("instance_name", ""),
                "action": action,
                "state": None,
                "error_code": "InvalidParameterValue",
                "error_message": (
                    f"Missing required parameter(s): {', '.join(missing)}"
                ),
                "metadata": {},
            }

        return None

    async def start_instance(self, params: dict) -> dict:
        """Start a GCP Compute Engine instance.

        Args:
            params: Dict with "project_id", "zone", and "instance_name" keys.

        Returns:
            Dict conforming to ExecutionResult fields with operation outcome.
        """
        action = "start_instance"

        # Validate required parameters
        validation_error = self._validate_params(params, action)
        if validation_error is not None:
            return validation_error

        project_id = params["project_id"]
        zone = params["zone"]
        instance_name = params["instance_name"]

        try:
            operation = self._instances_client.start(
                project=project_id, zone=zone, instance=instance_name
            )
            # Wait for operation to complete
            operation.result()

            return {
                "success": True,
                "provider": "GCP",
                "resource_id": instance_name,
                "action": action,
                "state": "RUNNING",
                "error_code": None,
                "error_message": None,
                "metadata": {
                    "project_id": project_id,
                    "zone": zone,
                },
            }

        except NotFound:
            return {
                "success": False,
                "provider": "GCP",
                "resource_id": instance_name,
                "action": action,
                "state": None,
                "error_code": "ResourceNotFound",
                "error_message": (
                    f"Instance '{instance_name}' not found in project "
                    f"'{project_id}', zone '{zone}'"
                ),
                "metadata": {
                    "project_id": project_id,
                    "zone": zone,
                },
            }

        except (DefaultCredentialsError, RefreshError) as e:
            return {
                "success": False,
                "provider": "GCP",
                "resource_id": instance_name,
                "action": action,
                "state": None,
                "error_code": "AuthenticationFailure",
                "error_message": (
                    f"Authentication failed for project '{project_id}': {str(e)}"
                ),
                "metadata": {
                    "project_id": project_id,
                    "zone": zone,
                },
            }

        except GoogleAPICallError as e:
            return {
                "success": False,
                "provider": "GCP",
                "resource_id": instance_name,
                "action": action,
                "state": None,
                "error_code": e.grpc_status_code.name if e.grpc_status_code else "GoogleAPIError",
                "error_message": str(e),
                "metadata": {
                    "project_id": project_id,
                    "zone": zone,
                },
            }

    async def stop_instance(self, params: dict) -> dict:
        """Stop a GCP Compute Engine instance.

        Args:
            params: Dict with "project_id", "zone", and "instance_name" keys.

        Returns:
            Dict conforming to ExecutionResult fields with operation outcome.
        """
        action = "stop_instance"

        # Validate required parameters
        validation_error = self._validate_params(params, action)
        if validation_error is not None:
            return validation_error

        project_id = params["project_id"]
        zone = params["zone"]
        instance_name = params["instance_name"]

        try:
            operation = self._instances_client.stop(
                project=project_id, zone=zone, instance=instance_name
            )
            # Wait for operation to complete
            operation.result()

            return {
                "success": True,
                "provider": "GCP",
                "resource_id": instance_name,
                "action": action,
                "state": "TERMINATED",
                "error_code": None,
                "error_message": None,
                "metadata": {
                    "project_id": project_id,
                    "zone": zone,
                },
            }

        except NotFound:
            return {
                "success": False,
                "provider": "GCP",
                "resource_id": instance_name,
                "action": action,
                "state": None,
                "error_code": "ResourceNotFound",
                "error_message": (
                    f"Instance '{instance_name}' not found in project "
                    f"'{project_id}', zone '{zone}'"
                ),
                "metadata": {
                    "project_id": project_id,
                    "zone": zone,
                },
            }

        except (DefaultCredentialsError, RefreshError) as e:
            return {
                "success": False,
                "provider": "GCP",
                "resource_id": instance_name,
                "action": action,
                "state": None,
                "error_code": "AuthenticationFailure",
                "error_message": (
                    f"Authentication failed for project '{project_id}': {str(e)}"
                ),
                "metadata": {
                    "project_id": project_id,
                    "zone": zone,
                },
            }

        except GoogleAPICallError as e:
            return {
                "success": False,
                "provider": "GCP",
                "resource_id": instance_name,
                "action": action,
                "state": None,
                "error_code": e.grpc_status_code.name if e.grpc_status_code else "GoogleAPIError",
                "error_message": str(e),
                "metadata": {
                    "project_id": project_id,
                    "zone": zone,
                },
            }
