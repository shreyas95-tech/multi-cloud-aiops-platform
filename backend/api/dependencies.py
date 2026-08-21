"""Dependency configuration for the Multi-Cloud AIOps Platform.

Instantiates and wires all service components:
- AILayer (intent parsing and recommendations)
- Orchestrator (provider registry and intent routing)
- MonitoringLayer (cost and status monitoring)
- Cloud Providers (AWS, Azure, GCP)

Registers all (provider, action) pairs in the Orchestrator's provider registry.
Exports configured instances for use by route handlers.
"""

import os

from backend.ai_layer.parser import AILayer
from backend.execution.aws_provider import AWSProvider
from backend.execution.azure_provider import AzureProvider
from backend.execution.gcp_provider import GCPProvider
from backend.monitoring.monitoring import MonitoringLayer
from backend.orchestrator.orchestrator import Orchestrator

# --- AWS live client configuration ---
# Uses env vars (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY) or instance profile for credentials.
_aws_region = os.environ.get("AWS_DEFAULT_REGION", "ap-south-1")

try:
    from backend.monitoring.aws_live_client import AWSLiveMonitoringClient
    from backend.monitoring.aws_live_cost_client import AWSLiveCostClient

    _aws_ec2_client = AWSLiveMonitoringClient(region_name=_aws_region)
    _aws_cost_client = AWSLiveCostClient(region_name=_aws_region)
except Exception:
    _aws_ec2_client = None
    _aws_cost_client = None

# --- Azure live client configuration ---
# Uses env vars (AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_SUBSCRIPTION_ID).
try:
    from backend.monitoring.azure_live_client import AzureLiveMonitoringClient

    _azure_monitor_client = AzureLiveMonitoringClient()
except Exception:
    _azure_monitor_client = None

# --- GCP live client configuration ---
# Uses env vars (GCP_CREDENTIALS_JSON, GCP_PROJECT_ID).
try:
    from backend.monitoring.gcp_live_client import GCPLiveMonitoringClient

    _gcp_monitoring_client = GCPLiveMonitoringClient()
except Exception:
    _gcp_monitoring_client = None

# --- Instantiate services ---

ai_layer = AILayer()
orchestrator = Orchestrator()
monitoring_layer = MonitoringLayer(
    aws_ec2_client=_aws_ec2_client,
    aws_cost_client=_aws_cost_client,
    azure_monitor_client=_azure_monitor_client,
    gcp_monitoring_client=_gcp_monitoring_client,
)

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


# --- Status and cost handlers ---

async def _aws_check_status(params: dict) -> dict:
    """Handler for AWS check_status — returns instance statuses with instance type."""
    try:
        statuses = await monitoring_layer.get_resource_status("AWS")

        # Also get instance types from the EC2 client
        instance_types = {}
        if monitoring_layer._aws_ec2_client:
            raw_response = await monitoring_layer._aws_ec2_client.describe_instances()
            for reservation in raw_response.get("Reservations", []):
                for inst in reservation.get("Instances", []):
                    instance_types[inst.get("InstanceId", "")] = inst.get("InstanceType", "unknown")

        status_list = []
        for s in statuses:
            inst_type = instance_types.get(s.resource_id, "unknown")
            free_tier = inst_type in ("t2.micro", "t3.micro")
            status_list.append({
                "resource_id": s.resource_id,
                "state": s.state,
                "cpu": s.cpu_utilization,
                "instance_type": inst_type,
                "free_tier": free_tier,
            })

        return {
            "success": True,
            "provider": "AWS",
            "resource_id": "all",
            "action": "check_status",
            "state": f"{len(status_list)} instances found",
            "error_code": None,
            "error_message": None,
            "metadata": {"instances": status_list},
        }
    except Exception as e:
        return {
            "success": False, "provider": "AWS", "resource_id": "all",
            "action": "check_status", "state": None,
            "error_code": "StatusCheckFailed", "error_message": str(e), "metadata": {},
        }


async def _azure_check_status(params: dict) -> dict:
    """Handler for Azure check_status."""
    try:
        statuses = await monitoring_layer.get_resource_status("Azure")
        status_list = [{"resource_id": s.resource_id, "state": s.state, "cpu": s.cpu_utilization} for s in statuses]
        return {
            "success": True, "provider": "Azure", "resource_id": "all",
            "action": "check_status", "state": f"{len(status_list)} instances found",
            "error_code": None, "error_message": None, "metadata": {"instances": status_list},
        }
    except Exception as e:
        return {
            "success": False, "provider": "Azure", "resource_id": "all",
            "action": "check_status", "state": None,
            "error_code": "StatusCheckFailed", "error_message": str(e), "metadata": {},
        }


async def _gcp_check_status(params: dict) -> dict:
    """Handler for GCP check_status."""
    try:
        statuses = await monitoring_layer.get_resource_status("GCP")
        status_list = [{"resource_id": s.resource_id, "state": s.state, "cpu": s.cpu_utilization} for s in statuses]
        return {
            "success": True, "provider": "GCP", "resource_id": "all",
            "action": "check_status", "state": f"{len(status_list)} instances found",
            "error_code": None, "error_message": None, "metadata": {"instances": status_list},
        }
    except Exception as e:
        return {
            "success": False, "provider": "GCP", "resource_id": "all",
            "action": "check_status", "state": None,
            "error_code": "StatusCheckFailed", "error_message": str(e), "metadata": {},
        }


async def _aws_get_costs(params: dict) -> dict:
    """Handler for AWS get_costs — returns cost data."""
    try:
        costs = await monitoring_layer.get_costs()
        aws_costs = [c for c in costs if c.provider == "AWS"]
        total = sum(c.cost_amount for c in aws_costs)
        return {
            "success": True, "provider": "AWS", "resource_id": "all",
            "action": "get_costs", "state": f"${total:.2f} total",
            "error_code": None, "error_message": None,
            "metadata": {"total_cost": total, "entries": len(aws_costs)},
        }
    except Exception as e:
        return {
            "success": False, "provider": "AWS", "resource_id": "all",
            "action": "get_costs", "state": None,
            "error_code": "CostCheckFailed", "error_message": str(e), "metadata": {},
        }


async def _azure_get_costs(params: dict) -> dict:
    """Handler for Azure get_costs."""
    try:
        costs = await monitoring_layer.get_costs()
        azure_costs = [c for c in costs if c.provider == "Azure"]
        total = sum(c.cost_amount for c in azure_costs)
        return {
            "success": True, "provider": "Azure", "resource_id": "all",
            "action": "get_costs", "state": f"${total:.2f} total",
            "error_code": None, "error_message": None,
            "metadata": {"total_cost": total, "entries": len(azure_costs)},
        }
    except Exception as e:
        return {
            "success": False, "provider": "Azure", "resource_id": "all",
            "action": "get_costs", "state": None,
            "error_code": "CostCheckFailed", "error_message": str(e), "metadata": {},
        }


async def _gcp_get_costs(params: dict) -> dict:
    """Handler for GCP get_costs."""
    try:
        costs = await monitoring_layer.get_costs()
        gcp_costs = [c for c in costs if c.provider == "GCP"]
        total = sum(c.cost_amount for c in gcp_costs)
        return {
            "success": True, "provider": "GCP", "resource_id": "all",
            "action": "get_costs", "state": f"${total:.2f} total",
            "error_code": None, "error_message": None,
            "metadata": {"total_cost": total, "entries": len(gcp_costs)},
        }
    except Exception as e:
        return {
            "success": False, "provider": "GCP", "resource_id": "all",
            "action": "get_costs", "state": None,
            "error_code": "CostCheckFailed", "error_message": str(e), "metadata": {},
        }


# --- Register all (provider, action) pairs in the Orchestrator ---

orchestrator.register("AWS", "start_instance", _aws_start_instance)
orchestrator.register("AWS", "stop_instance", _aws_stop_instance)
orchestrator.register("AWS", "check_status", _aws_check_status)
orchestrator.register("AWS", "get_costs", _aws_get_costs)
orchestrator.register("Azure", "start_instance", _azure_start_instance)
orchestrator.register("Azure", "stop_instance", _azure_stop_instance)
orchestrator.register("Azure", "check_status", _azure_check_status)
orchestrator.register("Azure", "get_costs", _azure_get_costs)
orchestrator.register("GCP", "start_instance", _gcp_start_instance)
orchestrator.register("GCP", "stop_instance", _gcp_stop_instance)
orchestrator.register("GCP", "check_status", _gcp_check_status)
orchestrator.register("GCP", "get_costs", _gcp_get_costs)
