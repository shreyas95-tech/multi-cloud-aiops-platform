"""AI Layer service for intent parsing using OpenAI GPT.

Uses OpenAI's chat completion API to parse natural language queries into
structured IntentJSON objects for cloud resource management.
"""

import asyncio
import json
import os
import re
from datetime import datetime

from backend.ai_layer.exceptions import (
    InsufficientDataError,
    ParseError,
    QueryTooLongError,
    UnsupportedProviderError,
)
from backend.models.intent import IntentJSON
from backend.models.monitoring import MonitoringData
from backend.models.recommendation import Recommendation

# Configuration
MAX_QUERY_LENGTH = 500
SUPPORTED_PROVIDERS = {"AWS", "Azure", "GCP"}
PARSE_TIMEOUT_SECONDS = 30
MAX_RECOMMENDATION_LENGTH = 500
MAX_RECOMMENDATIONS = 50

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

# System prompt for intent parsing
SYSTEM_PROMPT = """You are an AI assistant for a Multi-Cloud AIOps Platform that manages resources across AWS, Azure, and GCP.

Your job is to parse natural language queries into structured JSON actions.

Available actions:
- start_instance: Start a cloud instance/VM
- stop_instance: Stop a cloud instance/VM
- check_status: Check the status/CPU of instances
- get_costs: Get cost information

Available providers: AWS, Azure, GCP

For AWS instances, the instance_id looks like: i-0abc123def456
For Azure VMs, you need: subscription_id, resource_group, vm_name
For GCP, you need: project_id, zone, instance_name

You MUST respond with ONLY a JSON object in this exact format:
{
    "intent": "human readable description of what the user wants",
    "cloud": "AWS" or "Azure" or "GCP",
    "action": "start_instance" or "stop_instance" or "check_status" or "get_costs",
    "conditions": "key=value parameters, e.g. instance_id=i-abc123"
}

If the query explicitly mentions a provider (Azure, GCP, AWS), use that provider. Only default to cloud="AWS" if no provider is mentioned at all.
If you cannot determine the action or provider, respond with:
{
    "intent": "unclear",
    "cloud": "",
    "action": "",
    "conditions": ""
}

If the query is ambiguous but clearly about checking something (e.g., "is it running?", "what's the status?"), default to action="check_status" with cloud="AWS".
If the query asks about instance type, instance details, or free tier status, map it to action="check_status" since the status response includes instance type information.

Examples:
- "Start my EC2 instance i-084cc52233ec63085" → {"intent": "start EC2 instance", "cloud": "AWS", "action": "start_instance", "conditions": "instance_id=i-084cc52233ec63085"}
- "Stop Azure VM web-server in resource group prod-rg" → {"intent": "stop Azure VM", "cloud": "Azure", "action": "stop_instance", "conditions": "vm_name=web-server, resource_group=prod-rg"}
- "What's the CPU usage?" → {"intent": "check CPU utilization", "cloud": "AWS", "action": "check_status", "conditions": ""}
- "Show my costs" → {"intent": "get cost overview", "cloud": "AWS", "action": "get_costs", "conditions": ""}
- "Is my server running?" → {"intent": "check instance status", "cloud": "AWS", "action": "check_status", "conditions": ""}
- "Is it running?" → {"intent": "check instance status", "cloud": "AWS", "action": "check_status", "conditions": ""}
- "How much am I spending?" → {"intent": "get cost overview", "cloud": "AWS", "action": "get_costs", "conditions": ""}
- "Create a new instance" → {"intent": "create new EC2 instance", "cloud": "AWS", "action": "create_instance", "conditions": ""}
- "Which instance type is being used?" → {"intent": "check instance status and type", "cloud": "AWS", "action": "check_status", "conditions": ""}
- "What type of EC2 instance is running?" → {"intent": "check instance type", "cloud": "AWS", "action": "check_status", "conditions": ""}
- "Is it a free tier instance?" → {"intent": "check instance status and type", "cloud": "AWS", "action": "check_status", "conditions": ""}
- "Show me my instances" → {"intent": "list all instances", "cloud": "AWS", "action": "check_status", "conditions": ""}
- "What resources do I have?" → {"intent": "check instance status", "cloud": "AWS", "action": "check_status", "conditions": ""}
"""


class AILayer:
    """AI Layer service for parsing natural language into structured intents using OpenAI."""

    def __init__(self):
        """Initialize the AI Layer with OpenAI client if key is available."""
        self._openai_client = None
        if OPENAI_API_KEY:
            try:
                from openai import AsyncOpenAI
                self._openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
            except ImportError:
                pass

    async def parse_intent(self, query: str) -> IntentJSON:
        """Parse a natural language query into structured intent using OpenAI.

        Falls back to pattern matching if OpenAI is unavailable.
        """
        # Step 1: Validate query length
        if len(query) > MAX_QUERY_LENGTH:
            raise QueryTooLongError(length=len(query))

        # Step 2: Try OpenAI parsing
        try:
            intent = await asyncio.wait_for(
                self._parse_with_openai(query) if self._openai_client else self._parse_with_patterns(query),
                timeout=PARSE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            raise ParseError("Intent parsing timed out")
        except (ParseError, UnsupportedProviderError, QueryTooLongError):
            raise
        except Exception as e:
            # If OpenAI fails, fall back to pattern matching
            try:
                intent = await self._parse_with_patterns(query)
            except Exception:
                raise ParseError(f"Failed to parse intent: {str(e)}")

        return intent

    async def _parse_with_openai(self, query: str) -> IntentJSON:
        """Parse query using OpenAI chat completion."""
        try:
            response = await self._openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": query},
                ],
                temperature=0.1,
                max_tokens=200,
            )

            content = response.choices[0].message.content.strip()

            # Try to extract JSON from the response
            # Handle case where response might have markdown code blocks
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            parsed = json.loads(content)

            intent = parsed.get("intent", "")
            cloud = parsed.get("cloud", "")
            action = parsed.get("action", "")
            conditions = parsed.get("conditions", "")

            # Validate provider
            if cloud and cloud not in SUPPORTED_PROVIDERS:
                raise UnsupportedProviderError(provider=cloud)

            # If OpenAI couldn't determine the intent
            if not cloud or not action or intent == "unclear":
                raise ParseError(f"Could not determine intent from query: {query}")

            return IntentJSON(
                intent=intent,
                cloud=cloud,
                action=action,
                conditions=conditions,
            )

        except (UnsupportedProviderError, ParseError):
            raise
        except json.JSONDecodeError:
            raise ParseError("Failed to parse OpenAI response as JSON")
        except Exception as e:
            raise ParseError(f"OpenAI parsing failed: {str(e)}")

    async def _parse_with_patterns(self, query: str) -> IntentJSON:
        """Fallback: pattern-matching parser (original implementation)."""
        query_lower = query.lower()

        # Detect cloud provider
        provider = self._detect_provider(query)

        if provider and provider not in SUPPORTED_PROVIDERS:
            raise UnsupportedProviderError(provider=provider)

        if not provider:
            unsupported = self._detect_unsupported_provider(query)
            if unsupported:
                raise UnsupportedProviderError(provider=unsupported)

        # Detect action
        action = self._detect_action(query_lower)

        if not provider or not action:
            raise ParseError(f"Unable to parse intent from query: could not determine {'provider' if not provider else 'action'}")

        # Extract conditions
        conditions = self._extract_conditions(query, provider)

        intent = f"{action} on {provider}"
        if conditions:
            intent = f"{action} {conditions} on {provider}"

        return IntentJSON(intent=intent, cloud=provider, action=action, conditions=conditions)

    def _detect_provider(self, query: str) -> str | None:
        query_upper = query.upper()
        if "AWS" in query_upper or "AMAZON" in query_upper or "EC2" in query_upper:
            return "AWS"
        if "AZURE" in query_upper or "MICROSOFT" in query_upper:
            return "Azure"
        if "GCP" in query_upper or "GOOGLE" in query_upper or "GCLOUD" in query_upper:
            return "GCP"
        return None

    def _detect_unsupported_provider(self, query: str) -> str | None:
        query_lower = query.lower()
        unsupported_patterns = {
            "digitalocean": "DigitalOcean", "linode": "Linode",
            "oracle cloud": "OracleCloud", "ibm cloud": "IBMCloud",
            "alibaba": "Alibaba", "heroku": "Heroku",
        }
        for pattern, name in unsupported_patterns.items():
            if pattern in query_lower:
                return name
        return None

    def _detect_action(self, query_lower: str) -> str | None:
        action_patterns = {
            "start": "start_instance", "launch": "start_instance",
            "boot": "start_instance", "run": "start_instance",
            "stop": "stop_instance", "halt": "stop_instance",
            "shutdown": "stop_instance", "shut down": "stop_instance",
            "terminate": "stop_instance",
            "status": "check_status", "cpu": "check_status",
            "cost": "get_costs", "spend": "get_costs", "bill": "get_costs",
        }
        for keyword, action in action_patterns.items():
            if keyword in query_lower:
                return action
        return None

    def _extract_conditions(self, query: str, provider: str) -> str:
        conditions_parts: list[str] = []
        aws_id_match = re.search(r"i-[0-9a-f]+", query)
        if aws_id_match:
            conditions_parts.append(f"instance_id={aws_id_match.group()}")
        quoted_match = re.findall(r"['\"]([^'\"]+)['\"]", query)
        for match in quoted_match:
            conditions_parts.append(f"resource_name={match}")
        vm_name_match = re.search(r"\b(?:vm|instance|server)\s+(\S+)", query, re.IGNORECASE)
        if vm_name_match and not aws_id_match:
            name = vm_name_match.group(1).strip(".,;")
            if name.lower() not in {"on", "in", "the", "my", "a"}:
                conditions_parts.append(f"resource_name={name}")
        return ", ".join(conditions_parts)

    async def generate_recommendations(self, monitoring_data: MonitoringData) -> list[Recommendation]:
        """Generate cost optimization recommendations from monitoring data."""
        if not monitoring_data.cost_entries and not monitoring_data.resource_statuses:
            raise InsufficientDataError(
                "No cost entries or resource statuses available. "
                "Cannot generate recommendations without monitoring data."
            )

        if not self._has_minimum_24h_coverage(monitoring_data):
            raise InsufficientDataError(
                "Monitoring data must cover at least 24 hours of resource usage."
            )

        recommendations: list[Recommendation] = []
        now = datetime.utcnow().isoformat()

        for status in monitoring_data.resource_statuses:
            if (status.state == "running" and status.cpu_available
                    and status.cpu_utilization is not None and status.cpu_utilization < 10.0):
                action_text = (f"Consider stopping or downsizing resource "
                             f"'{status.resource_id}' on {status.provider} - "
                             f"CPU utilization is only {status.cpu_utilization}%")
                recommendations.append(Recommendation(
                    action=action_text[:MAX_RECOMMENDATION_LENGTH],
                    resource_id=status.resource_id, provider=status.provider,
                    estimated_saving=50.0, generated_at=now,
                ))

        for entry in monitoring_data.cost_entries:
            if entry.cost_amount > 100.0:
                action_text = (f"Review high-cost resource of type '{entry.resource_type}' "
                             f"on {entry.provider} costing ${entry.cost_amount:.2f}/period")
                recommendations.append(Recommendation(
                    action=action_text[:MAX_RECOMMENDATION_LENGTH],
                    resource_id=f"{entry.provider}-{entry.resource_type}",
                    provider=entry.provider, estimated_saving=entry.cost_amount * 0.2,
                    generated_at=now,
                ))

        if not recommendations:
            recommendations.append(Recommendation(
                action="No specific optimization opportunities detected. Resources appear well-utilized.",
                resource_id="general",
                provider=monitoring_data.cost_entries[0].provider if monitoring_data.cost_entries
                    else (monitoring_data.resource_statuses[0].provider if monitoring_data.resource_statuses else "AWS"),
                estimated_saving=0.0, generated_at=now,
            ))

        return recommendations[:MAX_RECOMMENDATIONS]

    def _has_minimum_24h_coverage(self, monitoring_data: MonitoringData) -> bool:
        """Check if monitoring data covers at least 24 hours."""
        if hasattr(monitoring_data, 'period') and monitoring_data.period:
            try:
                from datetime import datetime as dt
                start = dt.fromisoformat(monitoring_data.period.start.replace('Z', '+00:00'))
                end = dt.fromisoformat(monitoring_data.period.end.replace('Z', '+00:00'))
                from datetime import timedelta
                return (end - start) >= timedelta(hours=24)
            except (ValueError, AttributeError):
                pass
        return len(monitoring_data.cost_entries) > 0 or len(monitoring_data.resource_statuses) > 0
