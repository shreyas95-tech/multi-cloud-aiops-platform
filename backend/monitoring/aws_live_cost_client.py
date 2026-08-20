"""Real AWS cost client using boto3 Cost Explorer."""

import asyncio

import boto3


class AWSLiveCostClient:
    """Boto3-based client for AWS Cost Explorer data.

    Provides:
        - get_cost_and_usage(time_period) -> dict with cost breakdown
    """

    def __init__(self, region_name: str = None):
        """Initialize Cost Explorer client. CE is only available in us-east-1."""
        # Cost Explorer API endpoint is only in us-east-1
        self._ce = boto3.client("ce", region_name="us-east-1")

    async def get_cost_and_usage(self, time_period: dict) -> dict:
        """Fetch cost data from AWS Cost Explorer.

        Args:
            time_period: Dict with "Start" and "End" ISO date strings.

        Returns:
            Cost Explorer response dict with ResultsByTime key.
        """

        def _call():
            try:
                response = self._ce.get_cost_and_usage(
                    TimePeriod={
                        "Start": time_period["Start"],
                        "End": time_period["End"],
                    },
                    Granularity="MONTHLY",
                    Metrics=["BlendedCost"],
                    GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
                )
                return response
            except Exception:
                # Cost Explorer might not be enabled or no data yet
                return {"ResultsByTime": []}

        return await asyncio.to_thread(_call)
