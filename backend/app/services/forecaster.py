"""Predictive forecasting service.

Uses trained trend models to predict the next 7 days of values for each metric.
"""

import numpy as np
import structlog
from sklearn.linear_model import LinearRegression

logger = structlog.get_logger(__name__)


def forecast_metric(values: list[float], days_ahead: int = 7) -> dict:
    """Forecast future values for a metric based on historical data.

    Uses linear regression for trend projection with confidence intervals.

    Args:
        values: Historical values (time-ordered).
        days_ahead: Number of future points to predict (default 7).

    Returns:
        Dict with predictions, confidence bounds, and metadata.
    """
    n = len(values)
    if n < 3:
        return {"error": "Need at least 3 data points for forecasting.", "predictions": []}

    arr = np.array(values, dtype=float)
    X = np.arange(n).reshape(-1, 1)

    # Fit linear model
    model = LinearRegression()
    model.fit(X, arr)

    # Predict future values
    future_X = np.arange(n, n + days_ahead).reshape(-1, 1)
    predictions = model.predict(future_X)

    # Calculate confidence interval based on residual std
    residuals = arr - model.predict(X)
    std_residual = np.std(residuals)

    # 95% confidence interval
    upper_bound = predictions + 1.96 * std_residual
    lower_bound = predictions - 1.96 * std_residual

    # Trend direction
    slope = float(model.coef_[0])
    if abs(slope) < 0.01:
        trend = "stable"
    elif slope > 0:
        trend = "increasing"
    else:
        trend = "decreasing"

    return {
        "predictions": [round(float(p), 2) for p in predictions],
        "upper_bound": [round(float(u), 2) for u in upper_bound],
        "lower_bound": [round(float(l), 2) for l in lower_bound],
        "days_ahead": days_ahead,
        "trend": trend,
        "slope_per_day": round(slope, 4),
        "confidence": 0.95,
        "data_points_used": n,
    }


async def forecast_report(db, report_id: str, days_ahead: int = 7) -> list[dict]:
    """Generate forecasts for all metrics in a report.

    Args:
        db: Async database session.
        report_id: UUID of the report.
        days_ahead: Days to forecast.

    Returns:
        List of forecast dicts per metric.
    """
    from sqlalchemy import select
    from app.models.data_point import DataPoint
    from app.models.report import Report

    # Fetch report
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        return []

    # Fetch all data points for this report, ordered by timestamp
    stmt = (
        select(DataPoint)
        .where(DataPoint.report_id == report.id)
        .order_by(DataPoint.data_timestamp.asc())
    )
    dp_result = await db.execute(stmt)
    all_points = dp_result.scalars().all()

    # Group by metric
    metrics: dict[str, list[float]] = {}
    for dp in all_points:
        metrics.setdefault(dp.metric_name, []).append(dp.value)

    # Forecast each metric
    forecasts = []
    for metric_name, values in metrics.items():
        forecast = forecast_metric(values, days_ahead)
        forecast["metric_name"] = metric_name
        forecast["last_value"] = values[-1] if values else None
        forecasts.append(forecast)

    return forecasts
