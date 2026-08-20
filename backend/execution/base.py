"""Abstract base class for cloud provider implementations.

This module defines the common interface that all cloud provider implementations
(AWS, Azure, GCP) must conform to. The CloudProvider ABC ensures uniform
input/output contracts across providers, enabling the Orchestrator to route
actions to any provider without knowledge of provider-specific details.

The provider registry pattern depends on this interface: each provider registers
its methods under (provider_name, action) tuples, and the Orchestrator invokes
them through this common contract.
"""

from abc import ABC, abstractmethod


class CloudProvider(ABC):
    """Abstract base class for cloud provider execution functions.

    All cloud provider implementations must inherit from this class and
    implement the start_instance and stop_instance methods. Each method
    accepts a params dict with provider-specific parameters and returns
    a dict conforming to the ExecutionResult fields.

    Provider-specific params:
        AWS: {"instance_id": "i-0123456789abcdef0"}
        Azure: {"subscription_id": "...", "resource_group": "...", "vm_name": "..."}
        GCP: {"project_id": "...", "zone": "...", "instance_name": "..."}

    Return dict maps to ExecutionResult fields:
        {
            "success": bool,
            "provider": str,        # "AWS", "Azure", or "GCP"
            "resource_id": str,     # Provider-specific resource identifier
            "action": str,          # "start_instance" or "stop_instance"
            "state": str | None,    # New state after action (e.g., "running", "stopped")
            "error_code": str | None,       # Provider error code if failed
            "error_message": str | None,    # Human-readable error description
            "metadata": dict        # Additional provider-specific details
        }
    """

    @abstractmethod
    async def start_instance(self, params: dict) -> dict:
        """Start a cloud instance.

        Args:
            params: Provider-specific parameters identifying the instance.
                - AWS: requires "instance_id"
                - Azure: requires "subscription_id", "resource_group", "vm_name"
                - GCP: requires "project_id", "zone", "instance_name"

        Returns:
            A dict conforming to ExecutionResult fields with:
                - success: True if the instance was started or is already running
                - provider: The cloud provider name
                - resource_id: The provider-specific resource identifier
                - action: "start_instance"
                - state: The new instance state (e.g., "running", "pending")
                - error_code: Provider error code on failure, None on success
                - error_message: Human-readable error on failure, None on success
                - metadata: Additional provider-specific details
        """
        ...

    @abstractmethod
    async def stop_instance(self, params: dict) -> dict:
        """Stop a cloud instance.

        Args:
            params: Provider-specific parameters identifying the instance.
                - AWS: requires "instance_id"
                - Azure: requires "subscription_id", "resource_group", "vm_name"
                - GCP: requires "project_id", "zone", "instance_name"

        Returns:
            A dict conforming to ExecutionResult fields with:
                - success: True if the instance was stopped or is already stopped
                - provider: The cloud provider name
                - resource_id: The provider-specific resource identifier
                - action: "stop_instance"
                - state: The new instance state (e.g., "stopped", "stopping")
                - error_code: Provider error code on failure, None on success
                - error_message: Human-readable error on failure, None on success
                - metadata: Additional provider-specific details
        """
        ...
