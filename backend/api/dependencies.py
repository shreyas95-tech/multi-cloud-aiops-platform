"""Dependency configuration for the Multi-Cloud AIOps Platform.

Instantiates and wires all service components:
- AILayer (intent parsing and recommendations)
- Orchestrator (provider registry and intent routing)
- MonitoringLayer (cost and status monitoring)
- Cloud Providers (AWS, Azure, GCP)

Registers all (provider, action) pairs in the Orchestrator's provider registry.
Exports configured instances for use by route handlers.
"""

from backend.ai_layer.parser import AILayer
from backend.execution.aws_provider import AWSProvider
from backend.execution.azure_provider import AzureProvider
from backend.execution.gcp_provider import GCPProvider
from backend.monitoring.monitoring import MonitoringLayer
from backend.orchestrator.orchestrator import Orchestrator

# --- Instantiate services ---

ai_layer = AILayer()
orchestrator = Orchestrator()
monitoring_layer = MonitoringLayer()

# --- Instantiate cloud providers ---
# We use a _DEFERRED sentinel to prevent providers from creating real SDK
# clients at import time (which would fail without cloud credentials).
# The providers will lazily create clients on first actual API call.


class _DeferredClient:
    """Sentinel that defers real SDK client creation until first use."""

    def __getattr__(self, name):
        raise RuntimeError(
            "Cloud SDK client not configured. "
            "Set up credentials or inject a mock client."
        )


_DEFERRED = _DeferredClient()

aws_provider = AWSProvider(ec2_client=_DEFERRED)
azure_provider = AzureProvider(compute_client=_DEFERRED)
gcp_provider = GCPProvider(instances_client=_DEFERRED)


# --- Handler wrappers ---
# These extract provider-specific params from the intent conditions string
# and delegate to the appropriate provider method.


async def _aws_start_instance(params: dict) -> dict:
    """Wrapper for AWS start_instance that extracts instance_id from conditions."""
    conditions = params.get("conditions", "")
    instance_params = _parse_aws_conditions(conditions)
    return await aws_provider.start_instance(instance_params)


async def _aws_stop_instance(params: dict) -> dict:
    """Wrapper for AWS stop_instance that extracts instance_id from conditions."""
    conditions = params.get("conditions", "")
    instance_params = _parse_aws_conditions(conditions)
    return await aws_provider.stop_instance(instance_params)


async def _azure_start_instance(params: dict) -> dict:
    """Wrapper for Azure start_instance that extracts VM params from conditions."""
    conditions = params.get("conditions", "")
    vm_params = _parse_azure_conditions(conditions)
    return await azure_provider.start_instance(vm_params)


async def _azure_stop_instance(params: dict) -> dict:
    """Wrapper for Azure stop_instance that extracts VM params from conditions."""
    conditions = params.get("conditions", "")
    vm_params = _parse_azure_conditions(conditions)
    return await azure_provider.stop_instance(vm_params)


async def _gcp_start_instance(params: dict) -> dict:
    """Wrapper for GCP start_instance that extracts instance params from conditions."""
    conditions = params.get("conditions", "")
    instance_params = _parse_gcp_conditions(conditions)
    return await gcp_provider.start_instance(instance_params)


async def _gcp_stop_instance(params: dict) -> dict:
    """Wrapper for GCP stop_instance that extracts instance params from conditions."""
    conditions = params.get("conditions", "")
    instance_params = _parse_gcp_conditions(conditions)
    return await gcp_provider.stop_instance(instance_params)


# --- Condition parsers ---
# These parse the conditions string from IntentJSON into provider-specific params.


def _parse_aws_conditions(conditions: str) -> dict:
    """Extract AWS instance_id from conditions string.

    Looks for patterns like "instance_id=i-abc123" or just "i-abc123".
    """
    import re

    params: dict = {}

    # Try key=value format first
    match = re.search(r"instance_id\s*=\s*(i-[0-9a-f]+)", conditions)
    if match:
        params["instance_id"] = match.group(1)
        return params

    # Try bare instance ID
    match = re.search(r"(i-[0-9a-f]+)", conditions)
    if match:
        params["instance_id"] = match.group(1)
        return params

    # Return conditions as-is if no pattern found
    params["instance_id"] = conditions.strip()
    return params


def _parse_azure_conditions(conditions: str) -> dict:
    """Extract Azure subscription_id, resource_group, and vm_name from conditions.

    Looks for key=value pairs separated by commas or semicolons.
    """
    params: dict = {}

    # Parse key=value pairs
    for part in conditions.replace(";", ",").split(","):
        part = part.strip()
        if "=" in part:
            key, value = part.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key in ("subscription_id", "resource_group", "vm_name"):
                params[key] = value

    # If no key=value pairs found, try positional (vm_name only)
    if not params and conditions.strip():
        params["vm_name"] = conditions.strip()

    return params


def _parse_gcp_conditions(conditions: str) -> dict:
    """Extract GCP project_id, zone, and instance_name from conditions.

    Looks for key=value pairs separated by commas or semicolons.
    """
    params: dict = {}

    # Parse key=value pairs
    for part in conditions.replace(";", ",").split(","):
        part = part.strip()
        if "=" in part:
            key, value = part.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key in ("project_id", "zone", "instance_name"):
                params[key] = value

    # If no key=value pairs found, try positional (instance_name only)
    if not params and conditions.strip():
        params["instance_name"] = conditions.strip()

    return params


# --- Register all (provider, action) pairs in the Orchestrator ---

orchestrator.register("AWS", "start_instance", _aws_start_instance)
orchestrator.register("AWS", "stop_instance", _aws_stop_instance)
orchestrator.register("Azure", "start_instance", _azure_start_instance)
orchestrator.register("Azure", "stop_instance", _azure_stop_instance)
orchestrator.register("GCP", "start_instance", _gcp_start_instance)
orchestrator.register("GCP", "stop_instance", _gcp_stop_instance)
