"""Monitoring Layer - Cost tracking and comparison across cloud providers."""

import asyncio
from datetime import date, datetime
from typing import Optional

from backend.models.monitoring import CostComparison, CostEntry, ResourceStatus, TimePeriod


# Simple exchange rate dictionary for normalizing currencies to USD
EXCHANGE_RATES_TO_USD: dict[str, float] = {
    "USD": 1.0,
    "EUR": 1.08,
    "GBP": 1.27,
    "JPY": 0.0067,
    "CAD": 0.74,
    "AUD": 0.65,
    "CHF": 1.13,
    "INR": 0.012,
    "CNY": 0.14,
    "BRL": 0.20,
}


class MonitoringLayer:
    """Monitors costs and resource status across AWS, Azure, and GCP providers.

    Retrieves cost data from cloud billing APIs, normalizes currencies to USD,
    and supports cost comparisons across providers. Also monitors resource status
    including instance state and CPU utilization.

    Args:
        aws_cost_client: Optional AWS Cost Explorer client (for testability).
        azure_cost_client: Optional Azure Cost Management client (for testability).
        gcp_billing_client: Optional GCP Billing client (for testability).
        aws_ec2_client: Optional AWS EC2/CloudWatch client for status monitoring.
        azure_monitor_client: Optional Azure Monitor client for status monitoring.
        gcp_monitoring_client: Optional GCP Monitoring client for status monitoring.
    """

    def __init__(
        self,
        aws_cost_client=None,
        azure_cost_client=None,
        gcp_billing_client=None,
        aws_ec2_client=None,
        azure_monitor_client=None,
        gcp_monitoring_client=None,
    ):
        self._aws_cost_client = aws_cost_client
        self._azure_cost_client = azure_cost_client
        self._gcp_billing_client = gcp_billing_client
        self._aws_ec2_client = aws_ec2_client
        self._azure_monitor_client = azure_monitor_client
        self._gcp_monitoring_client = gcp_monitoring_client
        self._last_errors: list[dict] = []

    def get_last_errors(self) -> list[dict]:
        """Return errors from the last operation for callers to check which providers failed."""
        return list(self._last_errors)

    def _default_time_period(self) -> TimePeriod:
        """Return current calendar month (1st to today) as the default time period."""
        today = date.today()
        first_of_month = today.replace(day=1)
        return TimePeriod(
            start=first_of_month.isoformat(),
            end=today.isoformat(),
        )

    def _normalize_to_usd(self, amount: float, currency: str) -> float:
        """Convert a cost amount from the given currency to USD."""
        if currency == "USD":
            return amount
        rate = EXCHANGE_RATES_TO_USD.get(currency)
        if rate is None:
            # Unknown currency — treat as 1:1 with a warning
            return amount
        return round(amount * rate, 6)

    async def _fetch_aws_costs(self, time_period: TimePeriod) -> list[CostEntry]:
        """Fetch cost data from AWS Cost Explorer."""
        if self._aws_cost_client is None:
            raise RuntimeError("AWS Cost Explorer client not configured")

        response = await self._aws_cost_client.get_cost_and_usage(
            time_period={"Start": time_period.start, "End": time_period.end}
        )

        entries: list[CostEntry] = []
        for item in response.get("ResultsByTime", []):
            for group in item.get("Groups", []):
                resource_type = group.get("Keys", ["unknown"])[0]
                metrics = group.get("Metrics", {})
                cost_info = metrics.get("BlendedCost", {})
                amount = float(cost_info.get("Amount", 0.0))
                currency = cost_info.get("Unit", "USD")
                normalized_amount = self._normalize_to_usd(amount, currency)

                entries.append(
                    CostEntry(
                        provider="AWS",
                        resource_type=resource_type,
                        cost_amount=normalized_amount,
                        currency="USD",
                        period_start=item.get("TimePeriod", {}).get(
                            "Start", time_period.start
                        ),
                        period_end=item.get("TimePeriod", {}).get(
                            "End", time_period.end
                        ),
                    )
                )
        return entries

    async def _fetch_azure_costs(self, time_period: TimePeriod) -> list[CostEntry]:
        """Fetch cost data from Azure Cost Management."""
        if self._azure_cost_client is None:
            raise RuntimeError("Azure Cost Management client not configured")

        response = await self._azure_cost_client.query(
            time_period={"from": time_period.start, "to": time_period.end}
        )

        entries: list[CostEntry] = []
        for row in response.get("rows", []):
            # Expected row format: [cost_amount, currency, resource_type, date]
            if len(row) < 4:
                continue
            amount = float(row[0])
            currency = row[1]
            resource_type = row[2]
            normalized_amount = self._normalize_to_usd(amount, currency)

            entries.append(
                CostEntry(
                    provider="Azure",
                    resource_type=resource_type,
                    cost_amount=normalized_amount,
                    currency="USD",
                    period_start=time_period.start,
                    period_end=time_period.end,
                )
            )
        return entries

    async def _fetch_gcp_costs(self, time_period: TimePeriod) -> list[CostEntry]:
        """Fetch cost data from GCP Billing."""
        if self._gcp_billing_client is None:
            raise RuntimeError("GCP Billing client not configured")

        response = await self._gcp_billing_client.query(
            time_period={"startDate": time_period.start, "endDate": time_period.end}
        )

        entries: list[CostEntry] = []
        for item in response.get("costs", []):
            amount = float(item.get("amount", 0.0))
            currency = item.get("currency", "USD")
            resource_type = item.get("resource_type", "unknown")
            normalized_amount = self._normalize_to_usd(amount, currency)

            entries.append(
                CostEntry(
                    provider="GCP",
                    resource_type=resource_type,
                    cost_amount=normalized_amount,
                    currency="USD",
                    period_start=time_period.start,
                    period_end=time_period.end,
                )
            )
        return entries

    async def get_costs(
        self, time_period: Optional[TimePeriod] = None
    ) -> list[CostEntry]:
        """Retrieve and normalize cost data from all providers.

        If time_period is None, defaults to current calendar month (1st to today).
        Handles partial failures: if one provider fails, still returns data from others.
        Errors are stored in self._last_errors for callers to inspect.

        Args:
            time_period: Optional time period filter. Defaults to current month.

        Returns:
            List of CostEntry objects with all costs normalized to USD.
        """
        if time_period is None:
            time_period = self._default_time_period()

        self._last_errors = []
        all_entries: list[CostEntry] = []

        # Fetch from each provider concurrently, handling partial failures
        providers = [
            ("AWS", self._fetch_aws_costs),
            ("Azure", self._fetch_azure_costs),
            ("GCP", self._fetch_gcp_costs),
        ]

        tasks = [fetch_fn(time_period) for _, fetch_fn in providers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for (provider_name, _), result in zip(providers, results):
            if isinstance(result, Exception):
                self._last_errors.append(
                    {
                        "provider": provider_name,
                        "error": str(result),
                        "error_type": type(result).__name__,
                    }
                )
            else:
                all_entries.extend(result)

        return all_entries

    async def compare_costs(
        self, resource_type: str, time_period: TimePeriod
    ) -> CostComparison:
        """Compare costs across providers for a resource type.

        Gets costs filtered by resource_type and time_period, sums costs per provider,
        and identifies the cheapest provider(s) — handling ties (equal amounts).

        Args:
            resource_type: The resource type to compare across providers.
            time_period: The time period to compare over.

        Returns:
            CostComparison with cheapest_providers list and cost breakdown.
        """
        all_costs = await self.get_costs(time_period)

        # Filter by resource type
        filtered = [
            entry for entry in all_costs if entry.resource_type == resource_type
        ]

        # Sum costs per provider
        provider_totals: dict[str, float] = {}
        for entry in filtered:
            provider_totals[entry.provider] = (
                provider_totals.get(entry.provider, 0.0) + entry.cost_amount
            )

        # Identify cheapest provider(s), handle ties
        cheapest_providers: list[str] = []
        if provider_totals:
            min_cost = min(provider_totals.values())
            cheapest_providers = [
                provider
                for provider, total in provider_totals.items()
                if total == min_cost
            ]

        return CostComparison(
            resource_type=resource_type,
            period=time_period,
            cheapest_providers=sorted(cheapest_providers),
            breakdown=filtered,
        )

    # -------------------------------------------------------------------------
    # Resource Status Monitoring
    # -------------------------------------------------------------------------

    _AWS_STATE_MAP: dict[str, str] = {
        "running": "running",
        "pending": "running",
        "stopped": "stopped",
        "stopping": "stopped",
        "terminated": "terminated",
        "shutting-down": "terminated",
    }

    _AZURE_STATE_MAP: dict[str, str] = {
        "VM running": "running",
        "VM deallocated": "stopped",
        "VM stopped": "stopped",
        "VM deallocating": "stopped",
        "VM starting": "running",
        "VM deleted": "terminated",
    }

    _GCP_STATE_MAP: dict[str, str] = {
        "RUNNING": "running",
        "STAGING": "running",
        "STOPPED": "stopped",
        "SUSPENDED": "stopped",
        "TERMINATED": "terminated",
    }

    def _normalize_cpu(self, value: Optional[float]) -> tuple[Optional[float], bool]:
        """Normalize CPU utilization to 0.0-100.0 rounded to 1 decimal place.

        Returns:
            Tuple of (normalized_cpu, cpu_available). If value is None or cannot
            be parsed, returns (None, False).
        """
        if value is None:
            return None, False
        try:
            clamped = max(0.0, min(100.0, float(value)))
            return round(clamped, 1), True
        except (TypeError, ValueError):
            return None, False

    async def _fetch_aws_status(self) -> list[ResourceStatus]:
        """Fetch resource status from AWS EC2.

        Expected client interface:
            client.describe_instances() -> {"Reservations": [{"Instances": [...]}]}
            Each instance: {"InstanceId": str, "State": {"Name": str}}
            client.get_cpu_utilization(instance_id) -> {"cpu": float|None}
        """
        if self._aws_ec2_client is None:
            raise RuntimeError("AWS EC2 client not configured")

        response = await self._aws_ec2_client.describe_instances()

        statuses: list[ResourceStatus] = []
        for reservation in response.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                instance_id = instance.get("InstanceId", "")
                raw_state = instance.get("State", {}).get("Name", "unknown")
                state = self._AWS_STATE_MAP.get(raw_state, "terminated")

                # Attempt to get CPU utilization
                cpu_value: Optional[float] = None
                cpu_available = False
                try:
                    cpu_response = await self._aws_ec2_client.get_cpu_utilization(
                        instance_id
                    )
                    raw_cpu = cpu_response.get("cpu")
                    cpu_value, cpu_available = self._normalize_cpu(raw_cpu)
                except Exception:
                    cpu_value = None
                    cpu_available = False

                statuses.append(
                    ResourceStatus(
                        resource_id=instance_id,
                        provider="AWS",
                        state=state,
                        cpu_utilization=cpu_value,
                        cpu_available=cpu_available,
                    )
                )
        return statuses

    async def _fetch_azure_status(self) -> list[ResourceStatus]:
        """Fetch resource status from Azure Monitor.

        Expected client interface:
            client.list_vms() -> {"vms": [{"name": str, "power_state": str, "cpu": float|None}]}
        """
        if self._azure_monitor_client is None:
            raise RuntimeError("Azure Monitor client not configured")

        response = await self._azure_monitor_client.list_vms()

        statuses: list[ResourceStatus] = []
        for vm in response.get("vms", []):
            vm_name = vm.get("name", "")
            raw_state = vm.get("power_state", "unknown")
            state = self._AZURE_STATE_MAP.get(raw_state, "terminated")

            raw_cpu = vm.get("cpu")
            cpu_value, cpu_available = self._normalize_cpu(raw_cpu)

            statuses.append(
                ResourceStatus(
                    resource_id=vm_name,
                    provider="Azure",
                    state=state,
                    cpu_utilization=cpu_value,
                    cpu_available=cpu_available,
                )
            )
        return statuses

    async def _fetch_gcp_status(self) -> list[ResourceStatus]:
        """Fetch resource status from GCP Monitoring.

        Expected client interface:
            client.list_instances() -> {"instances": [{"name": str, "status": str, "cpu": float|None}]}
        """
        if self._gcp_monitoring_client is None:
            raise RuntimeError("GCP Monitoring client not configured")

        response = await self._gcp_monitoring_client.list_instances()

        statuses: list[ResourceStatus] = []
        for instance in response.get("instances", []):
            instance_name = instance.get("name", "")
            raw_state = instance.get("status", "TERMINATED")
            state = self._GCP_STATE_MAP.get(raw_state, "terminated")

            raw_cpu = instance.get("cpu")
            cpu_value, cpu_available = self._normalize_cpu(raw_cpu)

            statuses.append(
                ResourceStatus(
                    resource_id=instance_name,
                    provider="GCP",
                    state=state,
                    cpu_utilization=cpu_value,
                    cpu_available=cpu_available,
                )
            )
        return statuses

    async def get_resource_status(
        self, provider: Optional[str] = None
    ) -> list[ResourceStatus]:
        """Retrieve current resource status from target provider(s).

        If provider is specified, only query that provider. Otherwise query all three.
        Handles partial provider failures: returns results from successful providers
        and stores errors in self._last_errors.

        Args:
            provider: Optional provider filter ("AWS", "Azure", or "GCP").
                If None, queries all providers.

        Returns:
            List of ResourceStatus objects with normalized states and CPU metrics.
        """
        self._last_errors = []

        all_providers = [
            ("AWS", self._fetch_aws_status),
            ("Azure", self._fetch_azure_status),
            ("GCP", self._fetch_gcp_status),
        ]

        # Filter to specific provider if requested
        if provider is not None:
            all_providers = [
                (name, fn) for name, fn in all_providers if name == provider
            ]

        if not all_providers:
            return []

        # Fetch concurrently with partial failure handling
        tasks = [fetch_fn() for _, fetch_fn in all_providers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_statuses: list[ResourceStatus] = []
        for (provider_name, _), result in zip(all_providers, results):
            if isinstance(result, Exception):
                self._last_errors.append(
                    {
                        "provider": provider_name,
                        "error": str(result),
                        "error_type": type(result).__name__,
                    }
                )
            else:
                all_statuses.extend(result)

        return all_statuses
