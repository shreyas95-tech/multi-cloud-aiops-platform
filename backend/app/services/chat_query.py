"""Natural language query service.

Allows users to ask questions about their data in plain English.
Uses LLM to interpret the question and generate SQL/analysis.
"""

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_point import DataPoint
from app.models.report import Report
from app.models.deviation_record import DeviationRecord
from app.models.trend_result import TrendResult as TrendResultModel
from app.services.llm_provider import get_llm

logger = structlog.get_logger(__name__)

CHAT_SYSTEM_PROMPT = """You are a data analyst assistant for a report monitoring system. 
You have access to the following data that will be provided to you:
- Report metrics with historical values
- Trend analysis results (direction, rate of change)
- Detected deviations (expected vs actual values, severity)

Answer the user's question based ONLY on the data provided. Be concise and specific.
If the data doesn't contain enough information to answer, say so.
Format numbers clearly and use bullet points for lists."""


async def query_data(
    db: AsyncSession,
    question: str,
    user_id: str,
    group_id: str = None,
) -> dict:
    """Answer a natural language question about the user's data.

    Args:
        db: Database session.
        question: User's question in plain English.
        user_id: Current user's ID.
        group_id: User's group ID for filtering.

    Returns:
        Dict with 'answer' and 'context_used'.
    """
    llm = get_llm()

    # Gather relevant data context
    context = await _gather_context(db, user_id, group_id)

    if not context:
        return {
            "answer": "No data available yet. Upload some reports first.",
            "context_used": "none",
        }

    prompt = f"""Based on the following data from our monitoring system:

{context}

User's question: {question}

Provide a clear, concise answer based on the data above."""

    try:
        answer = llm.generate(prompt, system_prompt=CHAT_SYSTEM_PROMPT, max_tokens=800)
        return {
            "answer": answer,
            "context_used": "reports, trends, deviations",
        }
    except Exception as e:
        logger.error("chat_query_error", error=str(e))
        return {
            "answer": f"Sorry, I couldn't process your question. Error: {e}",
            "context_used": "none",
        }


async def _gather_context(db: AsyncSession, user_id: str, group_id: str = None) -> str:
    """Gather relevant data context for the LLM to answer questions."""
    parts = []

    # Get reports visible to user
    if group_id:
        report_stmt = select(Report).where(Report.group_id == group_id)
    else:
        report_stmt = select(Report).where(Report.user_id == user_id)

    report_result = await db.execute(report_stmt)
    reports = report_result.scalars().all()

    if not reports:
        return ""

    parts.append(f"**Reports ({len(reports)}):**")
    for r in reports[:10]:  # Limit to 10 reports
        parts.append(f"- {r.name} ({r.file_type}, status: {r.status})")

    # Get recent data points (last 20 per report)
    parts.append("\n**Recent Metrics:**")
    for r in reports[:5]:
        dp_stmt = (
            select(DataPoint)
            .where(DataPoint.report_id == r.id)
            .order_by(DataPoint.data_timestamp.desc())
            .limit(20)
        )
        dp_result = await db.execute(dp_stmt)
        points = dp_result.scalars().all()

        if points:
            # Group by metric for summary
            metrics: dict[str, list[float]] = {}
            for dp in points:
                metrics.setdefault(dp.metric_name, []).append(dp.value)

            for metric, values in metrics.items():
                avg = sum(values) / len(values)
                latest = values[0]
                parts.append(f"- {r.name} / {metric}: latest={latest:.1f}, avg={avg:.1f}, points={len(values)}")

    # Get trend results
    parts.append("\n**Trends:**")
    for r in reports[:5]:
        trend_stmt = (
            select(TrendResultModel)
            .where(TrendResultModel.report_id == r.id)
            .order_by(TrendResultModel.computed_at.desc())
            .limit(5)
        )
        trend_result = await db.execute(trend_stmt)
        trends = trend_result.scalars().all()
        for t in trends:
            parts.append(f"- {r.name} / {t.metric_name}: {t.direction} ({t.rate_of_change_pct:+.1f}%), algorithm: {t.algorithm_used}")

    # Get recent deviations
    parts.append("\n**Recent Deviations:**")
    for r in reports[:5]:
        dev_stmt = (
            select(DeviationRecord)
            .where(DeviationRecord.report_id == r.id)
            .order_by(DeviationRecord.detected_at.desc())
            .limit(5)
        )
        dev_result = await db.execute(dev_stmt)
        devs = dev_result.scalars().all()
        for d in devs:
            parts.append(
                f"- {r.name} / {d.metric_name}: {d.severity} severity, "
                f"expected={d.expected_value:.1f}, actual={d.actual_value:.1f}, "
                f"score={d.deviation_score:.1f}σ"
            )

    return "\n".join(parts)
