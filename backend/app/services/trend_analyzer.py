"""Trend analysis service: algorithms and orchestration for time-series trend detection.

Implements linear regression, moving averages, and seasonal decomposition
using scikit-learn and statsmodels. Selects appropriate algorithm based on
data point count.
"""

from datetime import datetime, timezone
from typing import Optional

import numpy as np
import structlog
from sklearn.linear_model import LinearRegression
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_point import DataPoint
from app.models.report import Report
from app.models.trend_result import TrendResult as TrendResultModel
from app.models.schemas import TrendDirection, TrendResult

logger = structlog.get_logger(__name__)

# --- Constants ---

MIN_DATA_POINTS_LINEAR = 2
MIN_DATA_POINTS_MOVING_AVG = 3
MIN_DATA_POINTS_SEASONAL = 12
DEFAULT_MOVING_AVG_WINDOW = 3
MAX_MOVING_AVG_WINDOW = 12


# --- Algorithm Selection ---


def select_algorithm(n_points: int) -> list[str]:
    """Select applicable algorithms based on data point count.

    Rules (Req 3.2, 3.5):
    - Linear regression: N >= 2
    - Moving averages: N >= 3
    - Seasonal decomposition: N >= 12

    Args:
        n_points: Number of available data points.

    Returns:
        List of applicable algorithm names.
    """
    algorithms = []

    if n_points >= MIN_DATA_POINTS_LINEAR:
        algorithms.append("linear_regression")
    if n_points >= MIN_DATA_POINTS_MOVING_AVG:
        algorithms.append("moving_average")
    if n_points >= MIN_DATA_POINTS_SEASONAL:
        algorithms.append("seasonal_decomposition")

    return algorithms


# --- Algorithms ---


def linear_regression(values: list[float]) -> dict:
    """Perform linear regression on sequential data points.

    Args:
        values: Sequential numeric values (time-ordered).

    Returns:
        Dict with slope, intercept, direction, rate_of_change_pct, r_squared.
    """
    n = len(values)
    if n < MIN_DATA_POINTS_LINEAR:
        return {"error": "Insufficient data points for linear regression."}

    X = np.arange(n).reshape(-1, 1)
    y = np.array(values)

    model = LinearRegression()
    model.fit(X, y)

    slope = float(model.coef_[0])
    intercept = float(model.intercept_)
    r_squared = float(model.score(X, y))

    # Determine direction
    if abs(slope) < 1e-10:
        direction = TrendDirection.STABLE
    elif slope > 0:
        direction = TrendDirection.INCREASING
    else:
        direction = TrendDirection.DECREASING

    # Rate of change as percentage relative to the mean
    mean_val = np.mean(y)
    if abs(mean_val) < 1e-10:
        rate_of_change_pct = 0.0
    else:
        # Rate per data point as percentage
        rate_of_change_pct = (slope / abs(mean_val)) * 100

    return {
        "algorithm": "linear_regression",
        "slope": slope,
        "intercept": intercept,
        "direction": direction,
        "rate_of_change_pct": round(rate_of_change_pct, 4),
        "r_squared": round(r_squared, 4),
    }


def moving_average(values: list[float], window: int = DEFAULT_MOVING_AVG_WINDOW) -> dict:
    """Compute moving average with configurable window size.

    Args:
        values: Sequential numeric values.
        window: Window size (3-12, Req 3.2).

    Returns:
        Dict with smoothed values, direction, rate_of_change_pct.
    """
    n = len(values)
    if n < MIN_DATA_POINTS_MOVING_AVG:
        return {"error": "Insufficient data points for moving average."}

    # Clamp window size
    window = max(DEFAULT_MOVING_AVG_WINDOW, min(window, MAX_MOVING_AVG_WINDOW, n))

    arr = np.array(values)
    # Compute moving average
    ma = np.convolve(arr, np.ones(window) / window, mode="valid")

    if len(ma) < 2:
        direction = TrendDirection.STABLE
        rate_of_change_pct = 0.0
    else:
        # Direction from first to last moving average value
        diff = ma[-1] - ma[0]
        if abs(diff) < 1e-10:
            direction = TrendDirection.STABLE
        elif diff > 0:
            direction = TrendDirection.INCREASING
        else:
            direction = TrendDirection.DECREASING

        # Rate of change
        mean_ma = np.mean(ma)
        if abs(mean_ma) < 1e-10:
            rate_of_change_pct = 0.0
        else:
            rate_of_change_pct = (diff / abs(mean_ma)) * 100

    return {
        "algorithm": "moving_average",
        "window_size": window,
        "smoothed_values": ma.tolist(),
        "direction": direction,
        "rate_of_change_pct": round(float(rate_of_change_pct), 4),
    }


def seasonal_decomposition(values: list[float], period: int = None) -> dict:
    """Perform seasonal decomposition using statsmodels.

    Requires at least 12 data points (Req 3.5).

    Args:
        values: Sequential numeric values.
        period: Seasonal period. Auto-detected if None (defaults to min(12, n//2)).

    Returns:
        Dict with trend component, direction, rate_of_change_pct.
    """
    n = len(values)
    if n < MIN_DATA_POINTS_SEASONAL:
        return {"error": "Insufficient data points for seasonal decomposition."}

    try:
        from statsmodels.tsa.seasonal import seasonal_decompose

        if period is None:
            period = min(12, n // 2)
            # Ensure period is at least 2
            period = max(2, period)

        arr = np.array(values, dtype=float)
        result = seasonal_decompose(arr, model="additive", period=period)

        # Extract trend component (remove NaN values from edges)
        trend = result.trend
        trend_clean = trend[~np.isnan(trend)]

        if len(trend_clean) < 2:
            return {
                "algorithm": "seasonal_decomposition",
                "direction": TrendDirection.STABLE,
                "rate_of_change_pct": 0.0,
                "period": period,
            }

        # Direction from trend line
        diff = trend_clean[-1] - trend_clean[0]
        if abs(diff) < 1e-10:
            direction = TrendDirection.STABLE
        elif diff > 0:
            direction = TrendDirection.INCREASING
        else:
            direction = TrendDirection.DECREASING

        mean_trend = np.mean(trend_clean)
        if abs(mean_trend) < 1e-10:
            rate_of_change_pct = 0.0
        else:
            rate_of_change_pct = (diff / abs(mean_trend)) * 100

        return {
            "algorithm": "seasonal_decomposition",
            "direction": direction,
            "rate_of_change_pct": round(float(rate_of_change_pct), 4),
            "period": period,
            "trend_values": trend_clean.tolist(),
        }

    except Exception as e:
        logger.warning("seasonal_decomposition_failed", error=str(e))
        return {"error": f"Seasonal decomposition failed: {e}"}


# --- Orchestration ---


async def analyze(
    db: AsyncSession,
    report_id: str,
    correlation_id: str = "",
) -> list[dict]:
    """Analyze trends for all metrics in a report.

    Fetches historical data for the report's name, applies appropriate
    algorithms based on data point count, and stores TrendResult records.

    Returns None/empty when fewer than 2 data points exist (Req 3.3).

    Args:
        db: Async database session.
        report_id: UUID of the report to analyze.
        correlation_id: For log tracing.

    Returns:
        List of trend result dicts per metric, or empty list.
    """
    log = logger.bind(
        operation="analyze_trends",
        report_id=report_id,
        correlation_id=correlation_id,
    )

    # Fetch report to get the report name
    report_result = await db.execute(
        select(Report).where(Report.id == report_id)
    )
    report = report_result.scalar_one_or_none()
    if report is None:
        log.error("report_not_found")
        return []

    # Fetch all data points for reports with the same name and user
    # (historical data across submissions, Req 3.1)
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
        log.info("no_data_points_for_report")
        return []

    # Group data points by metric name
    metrics: dict[str, list[DataPoint]] = {}
    for dp in all_data_points:
        metrics.setdefault(dp.metric_name, []).append(dp)

    results = []

    for metric_name, points in metrics.items():
        values = [dp.value for dp in points]
        n = len(values)

        # Req 3.3: fewer than 2 data points → store without analysis
        if n < MIN_DATA_POINTS_LINEAR:
            log.info("insufficient_data_for_trend", metric=metric_name, count=n)
            continue

        # Select and run the best algorithm
        applicable = select_algorithm(n)
        if not applicable:
            continue

        # Use the most sophisticated applicable algorithm
        # Priority: seasonal_decomposition > moving_average > linear_regression
        best_algorithm = applicable[-1]
        trend_data = _run_algorithm(best_algorithm, values)

        if "error" in trend_data:
            # Fallback to simpler algorithm
            for algo in reversed(applicable[:-1]):
                trend_data = _run_algorithm(algo, values)
                if "error" not in trend_data:
                    break

        if "error" in trend_data:
            log.warning(
                "all_algorithms_failed",
                metric=metric_name,
                error=trend_data["error"],
            )
            continue

        # Store TrendResult in database
        direction = trend_data.get("direction", TrendDirection.STABLE)
        rate = trend_data.get("rate_of_change_pct", 0.0)
        algorithm_used = trend_data.get("algorithm", best_algorithm)

        trend_record = TrendResultModel(
            report_id=report.id,
            metric_name=metric_name,
            direction=direction.value if isinstance(direction, TrendDirection) else direction,
            rate_of_change_pct=rate,
            algorithm_used=algorithm_used,
            data_points_count=n,
            trend_data={
                "values": values[-20:],  # Store last 20 for reference
                "data_points_used": [
                    {"value": dp.value, "timestamp": dp.data_timestamp.isoformat()}
                    for dp in points[-20:]
                ],
                **{k: v for k, v in trend_data.items()
                   if k not in ("direction", "rate_of_change_pct", "algorithm")},
            },
        )
        db.add(trend_record)

        results.append({
            "metric_name": metric_name,
            "direction": direction.value if isinstance(direction, TrendDirection) else direction,
            "rate_of_change_pct": rate,
            "algorithm_used": algorithm_used,
            "data_points_used": n,
        })

    await db.flush()
    log.info("trend_analysis_complete", metrics_analyzed=len(results))

    return results


def _run_algorithm(algorithm: str, values: list[float]) -> dict:
    """Run a specific algorithm on values."""
    if algorithm == "linear_regression":
        return linear_regression(values)
    elif algorithm == "moving_average":
        window = min(len(values), DEFAULT_MOVING_AVG_WINDOW)
        return moving_average(values, window=window)
    elif algorithm == "seasonal_decomposition":
        return seasonal_decomposition(values)
    else:
        return {"error": f"Unknown algorithm: {algorithm}"}
