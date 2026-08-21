"""Real GCP monitoring client using google-cloud-compute."""

import asyncio
import json
import os

from google.oauth2 import service_account
from google.cloud import compute_v1


class GCPLiveMonitoringClient:
    """GCP Compute Engine client for listing instances and their status.

    Provides:
        - list_instances() -> dict with instance data
    """

    def __init__(self):
        """Initialize with GCP credentials from environment variable."""
        credentials_json = os.environ.get("GCP_CREDENTIALS_JSON", "")
        self._project_id = os.environ.get("GCP_PROJECT_ID", "")

        if not credentials_json or not self._project_id:
            raise RuntimeError("GCP credentials not configured")

        # Parse the JSON credentials
        credentials_info = json.loads(credentials_json)
        credentials = service_account.Credentials.from_service_account_info(credentials_info)

        self._instances_client = compute_v1.InstancesClient(credentials=credentials)
        self._project_id = credentials_info.get("project_id", self._project_id)

    async def list_instances(self) -> dict:
        """Fetch all GCP Compute Engine instances across all zones."""

        def _call():
            instances = []
            try:
                # List instances across all zones using aggregated list
                request = compute_v1.AggregatedListInstancesRequest(
                    project=self._project_id,
                )
                agg_list = self._instances_client.aggregated_list(request=request)

                for zone, response in agg_list:
                    if response.instances:
                        for instance in response.instances:
                            instances.append({
                                "name": instance.name,
                                "status": instance.status,  # RUNNING, STOPPED, TERMINATED, etc.
                                "cpu": None,  # GCP CPU requires Cloud Monitoring API
                                "machine_type": instance.machine_type.split("/")[-1] if instance.machine_type else "unknown",
                                "zone": zone.split("/")[-1] if "/" in zone else zone,
                            })
            except Exception:
                pass

            return {"instances": instances}

        return await asyncio.to_thread(_call)
