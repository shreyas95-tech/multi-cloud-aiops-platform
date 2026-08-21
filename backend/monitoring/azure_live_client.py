"""Real Azure monitoring client using azure-mgmt-compute and azure-identity."""

import asyncio
import os

from azure.identity import ClientSecretCredential
from azure.mgmt.compute import ComputeManagementClient


class AzureLiveMonitoringClient:
    """Azure SDK-based client that implements the async interface expected by MonitoringLayer.

    Provides:
        - list_vms() -> dict with VM data including power state and CPU
    """

    def __init__(self):
        """Initialize with Azure credentials from environment variables."""
        tenant_id = os.environ.get("AZURE_TENANT_ID", "")
        client_id = os.environ.get("AZURE_CLIENT_ID", "")
        client_secret = os.environ.get("AZURE_CLIENT_SECRET", "")
        self._subscription_id = os.environ.get("AZURE_SUBSCRIPTION_ID", "")

        if not all([tenant_id, client_id, client_secret, self._subscription_id]):
            raise RuntimeError("Azure credentials not configured")

        credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )
        self._compute_client = ComputeManagementClient(credential, self._subscription_id)

    async def list_vms(self) -> dict:
        """Fetch all VMs across all resource groups with their power state."""

        def _call():
            vms = []
            try:
                for vm in self._compute_client.virtual_machines.list_all():
                    # Get the resource group from the VM ID
                    # VM ID format: /subscriptions/.../resourceGroups/RG_NAME/providers/...
                    parts = vm.id.split("/")
                    rg_idx = parts.index("resourceGroups") if "resourceGroups" in parts else -1
                    resource_group = parts[rg_idx + 1] if rg_idx >= 0 else "unknown"

                    # Get instance view for power state
                    power_state = "unknown"
                    try:
                        instance_view = self._compute_client.virtual_machines.instance_view(
                            resource_group, vm.name
                        )
                        for status in instance_view.statuses:
                            if status.code.startswith("PowerState/"):
                                power_state = "VM " + status.code.split("/")[1]
                                break
                    except Exception:
                        pass

                    vms.append({
                        "name": vm.name,
                        "power_state": power_state,
                        "cpu": None,  # CPU requires Azure Monitor metrics (separate API)
                        "vm_size": vm.hardware_profile.vm_size if vm.hardware_profile else "unknown",
                        "resource_group": resource_group,
                    })
            except Exception:
                # If no VMs exist or permissions issue, return empty list
                pass

            return {"vms": vms}

        return await asyncio.to_thread(_call)
