"""AI-powered deviation summary and analysis using LLM.

Generates human-readable explanations of detected deviations,
including context from historical data and suggested actions.
"""

import structlog

from app.services.llm_provider import get_llm

logger = structlog.get_logger(__name__)

DEVIATION_SUMMARY_SYSTEM = """You are a data analyst assistant. When given information about a statistical deviation in business metrics, provide:
1. A clear, concise explanation of what happened (2-3 sentences)
2. Possible causes (2-3 bullet points)
3. Suggested immediate actions (2-3 bullet points)

Be specific and actionable. Use the metric name and values provided. Keep your response under 300 words."""


def generate_deviation_summary(
    report_name: str,
    metric_name: str,
    severity: str,
    expected_value: float,
    actual_value: float,
    deviation_score: float,
    historical_avg: float = 0,
    historical_std: float = 0,
) -> str:
    """Generate an AI summary explaining a detected deviation.

    Args:
        report_name: Name of the report.
        metric_name: The metric that deviated.
        severity: low/medium/high.
        expected_value: Historical mean.
        actual_value: Today's value.
        deviation_score: Z-score.
        historical_avg: Historical average for context.
        historical_std: Historical standard deviation.

    Returns:
        LLM-generated summary text, or a fallback message if LLM is unavailable.
    """
    llm = get_llm()

    pct_change = ((actual_value - expected_value) / abs(expected_value) * 100) if expected_value != 0 else 0
    direction = "dropped" if actual_value < expected_value else "spiked"

    prompt = f"""Analyze this deviation detected in our monitoring system:

Report: {report_name}
Metric: {metric_name}
Severity: {severity.upper()}
Expected Value: {expected_value:.2f}
Actual Value: {actual_value:.2f}
Change: {direction} by {abs(pct_change):.1f}%
Deviation Score: {deviation_score:.1f} standard deviations from mean
Historical Average: {historical_avg:.2f}
Historical Std Dev: {historical_std:.2f}

Provide a brief analysis explaining what this means, possible causes, and recommended actions."""

    try:
        response = llm.generate(prompt, system_prompt=DEVIATION_SUMMARY_SYSTEM, max_tokens=500)
        if response.startswith("[LLM Error"):
            logger.warning("llm_unavailable_for_summary", error=response)
            return _fallback_summary(metric_name, severity, expected_value, actual_value, pct_change, direction)
        return response
    except Exception as e:
        logger.error("ai_summary_error", error=str(e))
        return _fallback_summary(metric_name, severity, expected_value, actual_value, pct_change, direction)


def _fallback_summary(metric_name, severity, expected, actual, pct_change, direction) -> str:
    """Fallback summary when LLM is unavailable."""
    return (
        f"**{metric_name}** {direction} by {abs(pct_change):.1f}% "
        f"(expected {expected:.2f}, got {actual:.2f}). "
        f"Severity: {severity}. "
        f"Review recent changes and system health to identify the root cause."
    )
