"""Real Azure monitoring client using azure-mgmt-compute and azure-monitor."""

import asyncio
import os
from datetime import datetime, timedelta

from azure.identity import ClientSecretCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.monitor import MonitorManagementClient


class AzureLiveMonitoringClient:
    """Azure SDK-based client for VM status and CPU metrics."""

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
        self._monitor_client = MonitorManagementClient(credential, self._subscription_id)

    async def list_vms(self) -> dict:
        """Fetch all VMs with power state and CPU utilization."""

        def _call():
            vms = []
            try:
                for vm in self._compute_client.virtual_machines.list_all():
                    parts = vm.id.split("/")
                    rg_idx = parts.index("resourceGroups") if "resourceGroups" in parts else -1
                    resource_group = parts[rg_idx + 1] if rg_idx >= 0 else "unknown"

                    # Get power state
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

                    # Get CPU utilization from Azure Monitor
                    cpu = None
                    try:
                        end_time = datetime.utcnow()
                        start_time = end_time - timedelta(minutes=10)
                        metrics_data = self._monitor_client.metrics.list(
                            resource_uri=vm.id,
                            timespan=f"{start_time.isoformat()}Z/{end_time.isoformat()}Z",
                            metricnames="Percentage CPU",
                            aggregation="Average",
                            interval="PT5M",
                        )
                        for metric in metrics_data.value:
                            for ts in reversed(metric.timeseries):
                                for data_point in reversed(ts.data):
                                    if data_point.average is not None:
                                        cpu = round(data_point.average, 1)
                                        break
                                if cpu is not None:
                                    break
                            if cpu is not None:
                                break
                    except Exception:
                        pass

                    vms.append({
                        "name": vm.name,
                        "power_state": power_state,
                        "cpu": cpu,
                        "vm_size": vm.hardware_profile.vm_size if vm.hardware_profile else "unknown",
                        "resource_group": resource_group,
                    })
            except Exception:
                pass

            return {"vms": vms}

        return await asyncio.to_thread(_call)
