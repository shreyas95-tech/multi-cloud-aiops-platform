"""Real AWS monitoring client using boto3 for live EC2 and CloudWatch data."""

import asyncio
from datetime import datetime, timedelta

import boto3


class AWSLiveMonitoringClient:
    """Boto3-based client that implements the async interface expected by MonitoringLayer.

    Provides:
        - describe_instances() -> dict with EC2 instance data
        - get_cpu_utilization(instance_id) -> dict with CPU metric
    """

    def __init__(self, region_name: str = None):
        """Initialize with optional region. Uses env vars or instance profile for credentials."""
        self._region = region_name
        self._ec2 = (
            boto3.client("ec2", region_name=region_name)
            if region_name
            else boto3.client("ec2")
        )
        self._cloudwatch = (
            boto3.client("cloudwatch", region_name=region_name)
            if region_name
            else boto3.client("cloudwatch")
        )

    async def describe_instances(self) -> dict:
        """Fetch all EC2 instances and their states."""

        def _call():
            response = self._ec2.describe_instances()
            return response

        return await asyncio.to_thread(_call)

    async def get_cpu_utilization(self, instance_id: str) -> dict:
        """Fetch average CPU utilization for an instance over the last 5 minutes."""

        def _call():
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(minutes=10)

            try:
                response = self._cloudwatch.get_metric_statistics(
                    Namespace="AWS/EC2",
                    MetricName="CPUUtilization",
                    Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=300,  # 5 minutes
                    Statistics=["Average"],
                )
                datapoints = response.get("Datapoints", [])
                if datapoints:
                    # Get the most recent datapoint
                    latest = sorted(datapoints, key=lambda x: x["Timestamp"])[-1]
                    return {"cpu": latest["Average"]}
                return {"cpu": None}
            except Exception:
                return {"cpu": None}

        return await asyncio.to_thread(_call)
