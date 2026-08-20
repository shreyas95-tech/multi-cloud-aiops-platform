"""Azure cloud provider implementation using azure-mgmt-compute SDK.

This module provides the AzureProvider class that implements the CloudProvider
interface for Azure Virtual Machine management. It supports starting and
deallocating VMs with proper validation, error handling, and authentication
failure detection.
"""

from typing import Optional

from backend.execution.base import CloudProvider


class AzureProvider(CloudProvider):
    """Azure VM cloud provider implementation.

    Implements start_instance and stop_instance operations via the
    azure-mgmt-compute SDK's ComputeManagementClient. Validates required
    parameters before making API calls and handles authentication failures
    and resource-not-found scenarios with structured error responses.

    Args:
        compute_client: Optional pre-configured ComputeManagementClient
            for dependency injection and testability. If not provided,
            a new client is created using the supplied credential.
        credential: Optional Azure credential object used when creating
            a new ComputeManagementClient. Ignored if compute_client is provided.
    """

    def __init__(self, compute_client=None, credential=None):
        self._compute_client = compute_client
        self._credential = credential

    def _get_client(self, subscription_id: str):
        """Get or create a ComputeManagementClient.

        Args:
            subscription_id: The Azure subscription ID for client creation.

        Returns:
            A ComputeManagementClient instance.
        """
        if self._compute_client is not None:
            return self._compute_client

        from azure.identity import DefaultAzureCredential
        from azure.mgmt.compute import ComputeManagementClient

        credential = self._credential or DefaultAzureCredential()
        self._compute_client = ComputeManagementClient(credential, subscription_id)
        return self._compute_client

    def _validate_params(self, params: dict, action: str) -> Optional[dict]:
        """Validate required Azure parameters.

        Args:
            params: The parameters dict to validate.
            action: The action name for error reporting.

        Returns:
            An error dict if validation fails, None if all params are present.
        """
        required = ["subscription_id", "resource_group", "vm_name"]
        missing = [key for key in required if not params.get(key)]

        if missing:
            return {
                "success": False,
                "provider": "Azure",
                "resource_id": params.get("vm_name", ""),
                "action": action,
                "state": None,
                "error_code": "InvalidParameter",
                "error_message": (
                    f"Missing required parameter(s): {', '.join(missing)}"
                ),
                "metadata": {},
            }

        return None

    async def start_instance(self, params: dict) -> dict:
        """Start an Azure Virtual Machine.

        Args:
            params: Dict with "subscription_id", "resource_group", and "vm_name"
                keys identifying the target VM.

        Returns:
            Dict conforming to ExecutionResult fields with operation outcome.
        """
        action = "start_instance"

        # Validate required parameters
        validation_error = self._validate_params(params, action)
        if validation_error is not None:
            return validation_error

        subscription_id = params["subscription_id"]
        resource_group = params["resource_group"]
        vm_name = params["vm_name"]

        try:
            client = self._get_client(subscription_id)
            poller = client.virtual_machines.begin_start(resource_group, vm_name)
            poller.result()

            return {
                "success": True,
                "provider": "Azure",
                "resource_id": vm_name,
                "action": action,
                "state": "Running",
                "error_code": None,
                "error_message": None,
                "metadata": {
                    "subscription_id": subscription_id,
                    "resource_group": resource_group,
                },
            }

        except Exception as e:
            return self._handle_error(e, vm_name, action, subscription_id, resource_group)

    async def stop_instance(self, params: dict) -> dict:
        """Stop (deallocate) an Azure Virtual Machine.

        Args:
            params: Dict with "subscription_id", "resource_group", and "vm_name"
                keys identifying the target VM.

        Returns:
            Dict conforming to ExecutionResult fields with operation outcome.
        """
        action = "stop_instance"

        # Validate required parameters
        validation_error = self._validate_params(params, action)
        if validation_error is not None:
            return validation_error

        subscription_id = params["subscription_id"]
        resource_group = params["resource_group"]
        vm_name = params["vm_name"]

        try:
            client = self._get_client(subscription_id)
            poller = client.virtual_machines.begin_deallocate(resource_group, vm_name)
            poller.result()

            return {
                "success": True,
                "provider": "Azure",
                "resource_id": vm_name,
                "action": action,
                "state": "Deallocated",
                "error_code": None,
                "error_message": None,
                "metadata": {
                    "subscription_id": subscription_id,
                    "resource_group": resource_group,
                },
            }

        except Exception as e:
            return self._handle_error(e, vm_name, action, subscription_id, resource_group)

    def _handle_error(
        self,
        error: Exception,
        vm_name: str,
        action: str,
        subscription_id: str,
        resource_group: str,
    ) -> dict:
        """Handle Azure SDK errors and return structured error dict.

        Args:
            error: The exception raised during the operation.
            vm_name: The target VM name.
            action: The action that was attempted.
            subscription_id: The Azure subscription ID.
            resource_group: The Azure resource group.

        Returns:
            A dict conforming to ExecutionResult fields with error details.
        """
        error_code = "UnknownError"
        error_message = str(error)

        # Check for Azure-specific exception types by class name
        # to avoid hard import dependency on azure SDK at module level
        error_type = type(error).__name__

        if error_type == "ResourceNotFoundError":
            error_code = "ResourceNotFound"
            error_message = (
                f"VM '{vm_name}' not found in resource group '{resource_group}'"
            )
        elif error_type == "ClientAuthenticationError":
            error_code = "AuthenticationFailure"
            error_message = (
                f"Authentication failed for subscription '{subscription_id}': "
                f"{str(error)}"
            )
        elif error_type == "HttpResponseError":
            error_code = getattr(error, "error_code", None) or "AzureHttpError"
            error_message = getattr(error, "message", str(error))

        return {
            "success": False,
            "provider": "Azure",
            "resource_id": vm_name,
            "action": action,
            "state": None,
            "error_code": error_code,
            "error_message": error_message,
            "metadata": {
                "subscription_id": subscription_id,
                "resource_group": resource_group,
            },
        }
