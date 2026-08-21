"""Real GCP monitoring client using google-cloud-compute and google-cloud-monitoring."""

import asyncio
import json
import os
from datetime import datetime, timedelta

from google.oauth2 import service_account
from google.cloud import compute_v1
from google.cloud import monitoring_v3


class GCPLiveMonitoringClient:
    """GCP client for listing instances and fetching CPU metrics."""

    def __init__(self):
        """Initialize with GCP credentials from environment variable."""
        credentials_json = os.environ.get("GCP_CREDENTIALS_JSON", "")
        self._project_id = os.environ.get("GCP_PROJECT_ID", "")

        if not credentials_json or not self._project_id:
            raise RuntimeError("GCP credentials not configured")

        credentials_info = json.loads(credentials_json)
        credentials = service_account.Credentials.from_service_account_info(credentials_info)

        self._instances_client = compute_v1.InstancesClient(credentials=credentials)
        self._monitoring_client = monitoring_v3.MetricServiceClient(credentials=credentials)
        self._project_id = credentials_info.get("project_id", self._project_id)

    async def list_instances(self) -> dict:
        """Fetch all GCP Compute Engine instances with CPU utilization."""

        def _call():
            instances = []
            try:
                request = compute_v1.AggregatedListInstancesRequest(
                    project=self._project_id,
                )
                agg_list = self._instances_client.aggregated_list(request=request)

                for zone, response in agg_list:
                    if response.instances:
                        for instance in response.instances:
                            # Get CPU for this instance
                            cpu = self._get_cpu_utilization(instance.name, zone)

                            instances.append({
                                "name": instance.name,
                                "status": instance.status,
                                "cpu": cpu,
                                "machine_type": instance.machine_type.split("/")[-1] if instance.machine_type else "unknown",
                                "zone": zone.split("/")[-1] if "/" in zone else zone,
                            })
            except Exception:
                pass

            return {"instances": instances}

        return await asyncio.to_thread(_call)

    def _get_cpu_utilization(self, instance_name: str, zone: str) -> float | None:
        """Fetch CPU utilization for a specific instance from Cloud Monitoring."""
        try:
            now = datetime.utcnow()
            start_time = now - timedelta(minutes=10)

            interval = monitoring_v3.TimeInterval(
                start_time=start_time,
                end_time=now,
            )

            # Build the filter for CPU utilization
            instance_filter = (
                f'metric.type = "compute.googleapis.com/instance/cpu/utilization" '
                f'AND resource.labels.instance_id != "" '
                f'AND metric.labels.instance_name = "{instance_name}"'
            )

            results = self._monitoring_client.list_time_series(
                request={
                    "name": f"projects/{self._project_id}",
                    "filter": instance_filter,
                    "interval": interval,
                    "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                }
            )

            for ts in results:
                for point in reversed(ts.points):
                    # CPU utilization is returned as a fraction (0.0 to 1.0)
                    cpu_value = point.value.double_value * 100.0
                    return round(cpu_value, 1)

            return None
        except Exception:
            return None
