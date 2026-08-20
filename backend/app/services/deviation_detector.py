"""Deviation detection service: z-score and IQR outlier detection with severity classification.

Evaluates each metric independently against its historical data,
classifies deviations by severity, and records complete DeviationRecords.
"""

from datetime import datetime, timezone
from typing import Optional

import numpy as np
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_point import DataPoint
from app.models.deviation_record import DeviationRecord as DeviationRecordModel
from app.models.report import Report
from app.models.schemas import DeviationSeverity, SEVERITY_THRESHOLDS

logger = structlog.get_logger(__name__)

# --- Constants ---

MIN_HISTORICAL_POINTS = 5
"""Minimum historical data points required before deviation analysis (Req 4.6)."""

DEFAULT_THRESHOLD = 2.0
"""Default z-score threshold for flagging deviations (Req 4.2)."""

IQR_MULTIPLIER = 1.5
"""IQR multiplier for outlier detection (Req 4.5)."""


# --- Statistical Methods ---


def compute_zscore(value: float, values: list[float]) -> float:
    """Compute the z-score of a value relative to the distribution of values.

    Args:
        value: The data point to evaluate.
        values: Historical data point values.

    Returns:
        The z-score (absolute value of standard deviations from mean).
    """
    arr = np.array(values, dtype=float)
    mean = np.mean(arr)
    std = np.std(arr, ddof=1)  # Sample standard deviation

    if std < 1e-10:
        # All values are essentially identical
        if abs(value - mean) < 1e-10:
            return 0.0
        # Any difference from a constant series is infinite deviation
        return float("inf")

    return abs((value - mean) / std)


def compute_iqr_outlier(value: float, values: list[float]) -> tuple[bool, float]:
    """Determine if a value is an outlier using the IQR method (1.5x multiplier).

    Args:
        value: The data point to evaluate.
        values: Historical data point values.

    Returns:
        Tuple of (is_outlier: bool, distance_from_bound: float).
        distance_from_bound is 0 if not an outlier.
    """
    arr = np.array(values, dtype=float)
    q1 = np.percentile(arr, 25)
    q3 = np.percentile(arr, 75)
    iqr = q3 - q1

    lower_bound = q1 - (IQR_MULTIPLIER * iqr)
    upper_bound = q3 + (IQR_MULTIPLIER * iqr)

    if value < lower_bound:
        return True, abs(value - lower_bound)
    elif value > upper_bound:
        return True, abs(value - upper_bound)
    else:
        return False, 0.0


def classify_severity(zscore: float) -> Optional[DeviationSeverity]:
    """Classify deviation severity based on z-score magnitude.

    Thresholds (Req 4.3):
    - low: 2.0 to 2.5 standard deviations
    - medium: 2.5 to 3.5 standard deviations
    - high: greater than 3.5 standard deviations

    Args:
        zscore: Absolute z-score value.

    Returns:
        DeviationSeverity or None if below threshold.
    """
    for severity_name, (lower, upper) in SEVERITY_THRESHOLDS.items():
        if lower <= zscore < upper:
            return DeviationSeverity(severity_name)

    # Below minimum threshold
    if zscore < SEVERITY_THRESHOLDS["low"][0]:
        return None

    # Should not reach here, but default to high for extreme values
    return DeviationSeverity.HIGH


# --- Multi-Metric Detection ---


async def detect(
    db: AsyncSession,
    report_id: str,
    correlation_id: str = "",
) -> list[dict]:
    """Detect deviations across all metrics for a report.

    Evaluates each metric independently (Req 4.7). Skips metrics with
    fewer than 5 historical points (Req 4.6). Records a complete
    DeviationRecord per deviating metric (Req 4.4).

    Args:
        db: Async database session.
        report_id: UUID of the report to evaluate.
        correlation_id: For log tracing.

    Returns:
        List of deviation result dicts (one per deviating metric).
    """
    log = logger.bind(
        operation="detect_deviations",
        report_id=report_id,
        correlation_id=correlation_id,
    )

    # Fetch report
    report_result = await db.execute(
        select(Report).where(Report.id == report_id)
    )
    report = report_result.scalar_one_or_none()
    if report is None:
        log.error("report_not_found")
        return []

    # Fetch all historical data points for same report name + user
    stmt = (
        select(DataPoint)
        .join(Report, DataPoint.report_id == Report.id)
        .where(Report.user_id == report.user_id)
        .where(Report.name == report.name)
        .order_by(DataPoint.data_timestamp.asc())
    )
    dp_result = await db.execute(stmt)
    all_data_points = dp_result.scalars().all()

    if not all_data_points:
        log.info("no_data_points")
        return []

    # Group by metric name
    metrics: dict[str, list[DataPoint]] = {}
    for dp in all_data_points:
        metrics.setdefault(dp.metric_name, []).append(dp)

    deviations = []

    for metric_name, points in metrics.items():
        # Req 4.6: Skip if fewer than 5 historical points
        if len(points) < MIN_HISTORICAL_POINTS:
            log.info(
                "insufficient_data_for_deviation",
                metric=metric_name,
                count=len(points),
            )
            continue

        # Get the latest data point as the one to evaluate
        latest_point = points[-1]
        # Historical values excluding the latest for comparison
        historical_values = [dp.value for dp in points[:-1]]

        # Need at least MIN_HISTORICAL_POINTS of historical data
        if len(historical_values) < MIN_HISTORICAL_POINTS - 1:
            continue

        # Compute z-score
        zscore = compute_zscore(latest_point.value, historical_values)

        # Also check IQR (Req 4.5)
        is_iqr_outlier, iqr_distance = compute_iqr_outlier(
            latest_point.value, historical_values
        )

        # Classify severity
        severity = classify_severity(zscore)

        # Only record if deviation crosses threshold
        if severity is None:
            continue

        # Compute expected value (mean of historical)
        expected_value = float(np.mean(historical_values))

        # Record complete DeviationRecord (Req 4.4)
        deviation_record = DeviationRecordModel(
            report_id=report.id,
            metric_name=metric_name,
            expected_value=expected_value,
            actual_value=latest_point.value,
            deviation_score=zscore,
            severity=severity.value,
            threshold_used=DEFAULT_THRESHOLD,
        )
        db.add(deviation_record)
        await db.flush()

        deviation_info = {
            "deviation_id": str(deviation_record.id),
            "report_name": report.name,
            "metric_name": metric_name,
            "expected_value": expected_value,
            "actual_value": latest_point.value,
            "deviation_score": zscore,
            "severity": severity.value,
            "is_iqr_outlier": is_iqr_outlier,
            "iqr_distance": iqr_distance,
        }
        deviations.append(deviation_info)

        log.info(
            "deviation_detected",
            metric=metric_name,
            severity=severity.value,
            zscore=round(zscore, 3),
            expected=round(expected_value, 4),
            actual=latest_point.value,
        )

    log.info(
        "deviation_detection_complete",
        metrics_evaluated=len(metrics),
        deviations_found=len(deviations),
    )

    return deviations
