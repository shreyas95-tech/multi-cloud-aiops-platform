"""AI Layer service for intent parsing and recommendation generation.

The AI Layer receives natural language queries and outputs structured Intent_JSON.
It has no access to cloud APIs or execution capabilities (LLM-as-parser-only pattern).

For development and testing, this module uses a simple pattern-matching implementation
that can parse basic queries like "start my AWS instance i-abc123" or "stop Azure VM myvm".
"""

import asyncio
import re
from datetime import datetime, timezone

from backend.ai_layer.exceptions import (
    InsufficientDataError,
    ParseError,
    QueryTooLongError,
    UnsupportedProviderError,
)
from backend.models.intent import IntentJSON
from backend.models.monitoring import MonitoringData
from backend.models.recommendation import Recommendation

# Maximum query length in characters
MAX_QUERY_LENGTH = 500

# Supported cloud providers
SUPPORTED_PROVIDERS = {"AWS", "Azure", "GCP"}

# Timeout for parsing operations in seconds
PARSE_TIMEOUT_SECONDS = 10

# Maximum characters per recommendation action
MAX_RECOMMENDATION_LENGTH = 500

# Maximum number of recommendations to return
MAX_RECOMMENDATIONS = 50


class AILayer:
    """AI Layer service for parsing natural language into structured intents.

    The AILayer parses natural language queries into IntentJSON objects and
    generates cost optimization recommendations from monitoring data.
    """

    async def parse_intent(self, query: str) -> IntentJSON:
        """Parse a natural language query into structured intent.

        Validation order:
        1. Check query length > 500 chars -> raise QueryTooLongError
        2. Parse the query using pattern matching (mock LLM)
        3. Check if detected provider not in {AWS, Azure, GCP} -> raise UnsupportedProviderError
        4. If parsing fails entirely -> raise ParseError

        Args:
            query: The natural language query to parse.

        Returns:
            IntentJSON with parsed intent, cloud provider, action, and conditions.

        Raises:
            QueryTooLongError: If query exceeds 500 characters.
            UnsupportedProviderError: If detected provider not in {AWS, Azure, GCP}.
            ParseError: If intent cannot be determined from the query.
        """
        # Step 1: Validate query length
        if len(query) > MAX_QUERY_LENGTH:
            raise QueryTooLongError(length=len(query))

        # Step 2: Parse with timeout
        try:
            intent = await asyncio.wait_for(
                self._parse_query(query),
                timeout=PARSE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            raise ParseError("Intent parsing timed out after 10 seconds")

        # Step 3: Validate provider (already done inside _parse_query for detected provider)
        # If we reach here, the intent has a valid provider.
        return intent

    async def generate_recommendations(
        self, monitoring_data: MonitoringData
    ) -> list[Recommendation]:
        """Generate cost optimization recommendations from monitoring data.

        Analyzes monitoring data (cost entries and resource statuses) to produce
        actionable cost optimization recommendations.

        Validates:
        - At least 24 hours of monitoring data (via TimePeriod or presence of data)
        - Output count: 1-50 recommendations
        - Each recommendation action: max 500 characters (truncated if longer)
        - Each recommendation has ISO 8601 UTC timestamp

        Args:
            monitoring_data: Aggregated monitoring data covering cost and status info.

        Returns:
            A list of Recommendation objects (1 to 50 items).

        Raises:
            InsufficientDataError: If monitoring data is insufficient (no data or
                less than 24 hours of coverage).
        """
        # Validate: must have at least some data to work with
        if not monitoring_data.cost_entries and not monitoring_data.resource_statuses:
            raise InsufficientDataError(
                "No cost entries or resource statuses available. "
                "Cannot generate recommendations without monitoring data."
            )

        # Validate: monitoring period must cover at least 24 hours
        if not self._has_minimum_24h_coverage(monitoring_data):
            raise InsufficientDataError(
                "Monitoring data must cover at least 24 hours of resource usage. "
                "Current data period is insufficient for generating reliable recommendations."
            )

        recommendations: list[Recommendation] = []
        now = datetime.now(timezone.utc).isoformat()

        # Analyze resource statuses for idle resources
        for status in monitoring_data.resource_statuses:
            if (
                status.state == "running"
                and status.cpu_available
                and status.cpu_utilization is not None
                and status.cpu_utilization < 10.0
            ):
                action_text = (
                    f"Consider stopping or downsizing resource "
                    f"'{status.resource_id}' on {status.provider} - "
                    f"CPU utilization is only {status.cpu_utilization}%"
                )
                recommendations.append(
                    Recommendation(
                        action=action_text[:MAX_RECOMMENDATION_LENGTH],
                        resource_id=status.resource_id,
                        provider=status.provider,
                        estimated_saving=50.0,
                        generated_at=now,
                    )
                )

        # Analyze cost entries for high-cost resources
        for entry in monitoring_data.cost_entries:
            if entry.cost_amount > 100.0:
                action_text = (
                    f"Review high-cost resource of type '{entry.resource_type}' "
                    f"on {entry.provider} costing ${entry.cost_amount:.2f}/period"
                )
                recommendations.append(
                    Recommendation(
                        action=action_text[:MAX_RECOMMENDATION_LENGTH],
                        resource_id=f"{entry.provider}-{entry.resource_type}",
                        provider=entry.provider,
                        estimated_saving=entry.cost_amount * 0.2,
                        generated_at=now,
                    )
                )

        # Ensure at least 1 recommendation
        if not recommendations:
            recommendations.append(
                Recommendation(
                    action="No specific optimization opportunities detected. Resources appear well-utilized.",
                    resource_id="general",
                    provider=monitoring_data.cost_entries[0].provider
                    if monitoring_data.cost_entries
                    else (
                        monitoring_data.resource_statuses[0].provider
                        if monitoring_data.resource_statuses
                        else "AWS"
                    ),
                    estimated_saving=0.0,
                    generated_at=now,
                )
            )

        # Enforce max 50 recommendations
        return recommendations[:MAX_RECOMMENDATIONS]

    def _has_minimum_24h_coverage(self, monitoring_data: MonitoringData) -> bool:
        """Check if the monitoring data covers at least 24 hours.

        Validates via the TimePeriod on the monitoring data. If period_start
        and period_end are parseable ISO 8601 strings, checks that the
        difference is at least 24 hours.

        Falls back to True if the period has data but timestamps can't be parsed
        (allows graceful handling of edge cases in data formats).
        """
        try:
            period = monitoring_data.period
            start = datetime.fromisoformat(period.start)
            end = datetime.fromisoformat(period.end)
            duration = end - start
            return duration.total_seconds() >= 24 * 3600
        except (ValueError, TypeError, AttributeError):
            # If we can't parse the period but have data, fall back to checking
            # whether any data exists (already validated above)
            return bool(
                monitoring_data.cost_entries or monitoring_data.resource_statuses
            )

    async def _parse_query(self, query: str) -> IntentJSON:
        """Internal pattern-matching parser (mock LLM implementation).

        Uses regex patterns to extract intent, provider, action, and conditions
        from natural language queries.

        Args:
            query: The query string to parse.

        Returns:
            IntentJSON with extracted fields.

        Raises:
            UnsupportedProviderError: If a provider is detected but not supported.
            ParseError: If no intent can be determined.
        """
        query_lower = query.lower()

        # Detect cloud provider
        provider = self._detect_provider(query)

        # If a provider-like word was detected but it's not supported, raise error
        if provider and provider not in SUPPORTED_PROVIDERS:
            raise UnsupportedProviderError(provider=provider)

        # If no provider detected at all, try to see if there's an unsupported one mentioned
        if not provider:
            unsupported = self._detect_unsupported_provider(query)
            if unsupported:
                raise UnsupportedProviderError(provider=unsupported)

        # Detect action
        action = self._detect_action(query_lower)

        # If we couldn't detect either provider or action, raise ParseError
        if not provider or not action:
            raise ParseError(
                f"Unable to parse intent from query: could not determine "
                f"{'provider' if not provider else 'action'}"
            )

        # Extract conditions (resource identifiers, etc.)
        conditions = self._extract_conditions(query, provider)

        # Build intent description
        intent = f"{action} on {provider}"
        if conditions:
            intent = f"{action} {conditions} on {provider}"

        return IntentJSON(
            intent=intent,
            cloud=provider,
            action=action,
            conditions=conditions,
        )

    def _detect_provider(self, query: str) -> str | None:
        """Detect a supported cloud provider from the query text."""
        query_upper = query.upper()

        if "AWS" in query_upper or "AMAZON" in query_upper or "EC2" in query_upper:
            return "AWS"
        if "AZURE" in query_upper or "MICROSOFT" in query_upper:
            return "Azure"
        if "GCP" in query_upper or "GOOGLE" in query_upper or "GCLOUD" in query_upper:
            return "GCP"

        return None

    def _detect_unsupported_provider(self, query: str) -> str | None:
        """Detect mentions of unsupported cloud providers."""
        query_lower = query.lower()

        unsupported_patterns = {
            "digitalocean": "DigitalOcean",
            "linode": "Linode",
            "oracle cloud": "OracleCloud",
            "ibm cloud": "IBMCloud",
            "alibaba": "Alibaba",
            "heroku": "Heroku",
        }

        for pattern, name in unsupported_patterns.items():
            if pattern in query_lower:
                return name

        return None

    def _detect_action(self, query_lower: str) -> str | None:
        """Detect the action/operation from the query text."""
        action_patterns = {
            "start": "start_instance",
            "launch": "start_instance",
            "boot": "start_instance",
            "run": "start_instance",
            "stop": "stop_instance",
            "halt": "stop_instance",
            "shutdown": "stop_instance",
            "shut down": "stop_instance",
            "terminate": "stop_instance",
        }

        for keyword, action in action_patterns.items():
            if keyword in query_lower:
                return action

        return None

    def _extract_conditions(self, query: str, provider: str) -> str:
        """Extract resource identifiers and conditions from the query."""
        conditions_parts: list[str] = []

        # AWS instance IDs (i-xxx)
        aws_id_match = re.search(r"i-[0-9a-f]+", query)
        if aws_id_match:
            conditions_parts.append(f"instance_id={aws_id_match.group()}")

        # Generic resource names (quoted strings or specific patterns)
        quoted_match = re.findall(r"['\"]([^'\"]+)['\"]", query)
        for match in quoted_match:
            conditions_parts.append(f"resource_name={match}")

        # VM names (common patterns like "myvm", "web-server-1", etc.)
        vm_name_match = re.search(
            r"\b(?:vm|instance|server)\s+(\S+)", query, re.IGNORECASE
        )
        if vm_name_match and not aws_id_match:
            name = vm_name_match.group(1).strip(".,;")
            if name.lower() not in {"on", "in", "the", "my", "a"}:
                conditions_parts.append(f"resource_name={name}")

        return ", ".join(conditions_parts)
