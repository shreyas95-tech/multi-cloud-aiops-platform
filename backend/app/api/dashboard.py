"""Dashboard API endpoints: report listing, trend data, and deviation records.

Provides endpoints for the React frontend to fetch reports, trend visualizations,
and deviation alerts for authenticated users.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.models.report import Report
from app.models.trend_result import TrendResult
from app.models.deviation_record import DeviationRecord
from app.models.data_point import DataPoint

router = APIRouter(prefix="/reports", tags=["dashboard"])

# --- Constants ---

DEFAULT_DATE_RANGE_DAYS = 30
MAX_DATE_RANGE_DAYS = 365


# --- Response Schemas ---


class ReportSummary(BaseModel):
    """Summary of a report for listing."""
    id: str
    name: str
    file_type: str
    status: str
    received_at: str
    parsed_at: str | None = None
    group_id: str | None = None
    group_name: str | None = None


class ReportListResponse(BaseModel):
    """List of reports response."""
    reports: list[ReportSummary]
    count: int


class TrendDataPoint(BaseModel):
    """A single data point in the trend visualization."""
    value: float
    timestamp: str
    metric_name: str


class TrendResultResponse(BaseModel):
    """Trend analysis result for a metric."""
    id: str
    metric_name: str
    direction: str
    rate_of_change_pct: float
    algorithm_used: str
    data_points_count: int
    computed_at: str


class TrendVisualizationResponse(BaseModel):
    """Complete trend visualization data for a report."""
    report_name: str
    trends: list[TrendResultResponse]
    data_points: list[TrendDataPoint]


class DeviationResponse(BaseModel):
    """Deviation record response."""
    id: str
    metric_name: str
    expected_value: float
    actual_value: float
    deviation_score: float
    severity: str
    detected_at: str


class DeviationListResponse(BaseModel):
    """List of deviations response."""
    report_name: str
    deviations: list[DeviationResponse]
    count: int


# --- Endpoints ---


@router.get("", response_model=ReportListResponse)
async def list_reports(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReportListResponse:
    """List all report names visible to the authenticated user (Req 7.1).

    Users see reports belonging to their group. Admins see all reports.
    """
    if current_user.is_admin:
        stmt = select(Report).order_by(Report.received_at.desc())
    elif current_user.group_id:
        stmt = select(Report).where(
            Report.group_id == current_user.group_id
        ).order_by(Report.received_at.desc())
    else:
        # User with no group sees only their own reports
        stmt = select(Report).where(
            Report.user_id == current_user.id
        ).order_by(Report.received_at.desc())

    result = await db.execute(stmt)
    reports = result.scalars().all()

    # Get group names
    from app.models.group import Group
    group_cache = {}
    for r in reports:
        if r.group_id and r.group_id not in group_cache:
            g_result = await db.execute(select(Group).where(Group.id == r.group_id))
            g = g_result.scalar_one_or_none()
            group_cache[r.group_id] = g.name if g else None

    return ReportListResponse(
        reports=[
            ReportSummary(
                id=str(r.id),
                name=r.name,
                file_type=r.file_type,
                status=r.status,
                received_at=r.received_at.isoformat(),
                parsed_at=r.parsed_at.isoformat() if r.parsed_at else None,
                group_id=str(r.group_id) if r.group_id else None,
                group_name=group_cache.get(r.group_id),
            )
            for r in reports
        ],
        count=len(reports),
    )


@router.get("/{report_name}/trends", response_model=TrendVisualizationResponse)
async def get_report_trends(
    report_name: str,
    days: int = Query(default=DEFAULT_DATE_RANGE_DAYS, ge=1, le=MAX_DATE_RANGE_DAYS),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TrendVisualizationResponse:
    """Get trend visualization for a report including data points and trend line (Req 7.2, 7.5).

    Supports date range filter with default 30 days, max 365 days.
    """
    # Verify user has access to this report (owner, same group, or admin)
    if current_user.is_admin:
        report_check = await db.execute(
            select(Report).where(Report.name == report_name).limit(1)
        )
    elif current_user.group_id:
        report_check = await db.execute(
            select(Report).where(
                Report.name == report_name,
                Report.group_id == current_user.group_id,
            ).limit(1)
        )
    else:
        report_check = await db.execute(
            select(Report).where(
                Report.user_id == current_user.id,
                Report.name == report_name,
            ).limit(1)
        )
    if report_check.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No reports found with name '{report_name}'.",
        )

    # Calculate date range
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    # Fetch trend results for this report name (respecting access)
    if current_user.is_admin:
        trend_stmt = (
            select(TrendResult)
            .join(Report, TrendResult.report_id == Report.id)
            .where(
                Report.name == report_name,
                TrendResult.computed_at >= start_date,
            )
            .order_by(TrendResult.computed_at.desc())
        )
    elif current_user.group_id:
        trend_stmt = (
            select(TrendResult)
            .join(Report, TrendResult.report_id == Report.id)
            .where(
                Report.name == report_name,
                Report.group_id == current_user.group_id,
                TrendResult.computed_at >= start_date,
            )
            .order_by(TrendResult.computed_at.desc())
        )
    else:
        trend_stmt = (
            select(TrendResult)
            .join(Report, TrendResult.report_id == Report.id)
            .where(
                Report.user_id == current_user.id,
                Report.name == report_name,
                TrendResult.computed_at >= start_date,
            )
            .order_by(TrendResult.computed_at.desc())
        )
    trend_result = await db.execute(trend_stmt)
    trends = trend_result.scalars().all()

    # Fetch data points for visualization
    if current_user.is_admin:
        dp_stmt = (
            select(DataPoint)
            .join(Report, DataPoint.report_id == Report.id)
            .where(
                Report.name == report_name,
                DataPoint.data_timestamp >= start_date,
            )
            .order_by(DataPoint.data_timestamp.asc())
        )
    elif current_user.group_id:
        dp_stmt = (
            select(DataPoint)
            .join(Report, DataPoint.report_id == Report.id)
            .where(
                Report.group_id == current_user.group_id,
                Report.name == report_name,
                DataPoint.data_timestamp >= start_date,
            )
            .order_by(DataPoint.data_timestamp.asc())
        )
    else:
        dp_stmt = (
            select(DataPoint)
            .join(Report, DataPoint.report_id == Report.id)
            .where(
                Report.user_id == current_user.id,
                Report.name == report_name,
                DataPoint.data_timestamp >= start_date,
            )
            .order_by(DataPoint.data_timestamp.asc())
        )
    dp_result = await db.execute(dp_stmt)
    data_points = dp_result.scalars().all()

    return TrendVisualizationResponse(
        report_name=report_name,
        trends=[
            TrendResultResponse(
                id=str(t.id),
                metric_name=t.metric_name,
                direction=t.direction,
                rate_of_change_pct=t.rate_of_change_pct,
                algorithm_used=t.algorithm_used,
                data_points_count=t.data_points_count,
                computed_at=t.computed_at.isoformat(),
            )
            for t in trends
        ],
        data_points=[
            TrendDataPoint(
                value=dp.value,
                timestamp=dp.data_timestamp.isoformat(),
                metric_name=dp.metric_name,
            )
            for dp in data_points
        ],
    )


@router.get("/{report_name}/deviations", response_model=DeviationListResponse)
async def get_report_deviations(
    report_name: str,
    days: int = Query(default=DEFAULT_DATE_RANGE_DAYS, ge=1, le=MAX_DATE_RANGE_DAYS),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DeviationListResponse:
    """Get deviation records for a report (Req 7.3)."""
    # Calculate date range
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    # Fetch deviations (respecting group access)
    if current_user.is_admin:
        stmt = (
            select(DeviationRecord)
            .join(Report, DeviationRecord.report_id == Report.id)
            .where(
                Report.name == report_name,
                DeviationRecord.detected_at >= start_date,
            )
            .order_by(DeviationRecord.detected_at.desc())
        )
    elif current_user.group_id:
        stmt = (
            select(DeviationRecord)
            .join(Report, DeviationRecord.report_id == Report.id)
            .where(
                Report.group_id == current_user.group_id,
                Report.name == report_name,
                DeviationRecord.detected_at >= start_date,
            )
            .order_by(DeviationRecord.detected_at.desc())
        )
    else:
        stmt = (
            select(DeviationRecord)
            .join(Report, DeviationRecord.report_id == Report.id)
            .where(
                Report.user_id == current_user.id,
                Report.name == report_name,
                DeviationRecord.detected_at >= start_date,
            )
            .order_by(DeviationRecord.detected_at.desc())
        )
    result = await db.execute(stmt)
    deviations = result.scalars().all()

    return DeviationListResponse(
        report_name=report_name,
        deviations=[
            DeviationResponse(
                id=str(d.id),
                metric_name=d.metric_name,
                expected_value=d.expected_value,
                actual_value=d.actual_value,
                deviation_score=d.deviation_score,
                severity=d.severity,
                detected_at=d.detected_at.isoformat(),
            )
            for d in deviations
        ],
        count=len(deviations),
    )


# --- Notification Status Endpoint ---


class NotificationLogResponse(BaseModel):
    """Notification log entry for the Dashboard."""
    id: str
    phone_number: str
    status: str
    retry_count: int
    error_message: str | None = None
    sent_at: str


class NotificationListResponse(BaseModel):
    """List of notification logs."""
    notifications: list[NotificationLogResponse]
    count: int


@router.get("/notifications", response_model=NotificationListResponse)
async def get_notification_logs(
    days: int = Query(default=7, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationListResponse:
    """Get recent notification logs for the current user (Req 5.4, 7.7).

    Surfaces notification failures and delivery status on the Dashboard.
    """
    from app.models.notification_log import NotificationLog

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    stmt = (
        select(NotificationLog)
        .where(
            NotificationLog.user_id == current_user.id,
            NotificationLog.sent_at >= start_date,
        )
        .order_by(NotificationLog.sent_at.desc())
        .limit(100)
    )
    result = await db.execute(stmt)
    logs = result.scalars().all()

    return NotificationListResponse(
        notifications=[
            NotificationLogResponse(
                id=str(n.id),
                phone_number=n.phone_number,
                status=n.status,
                retry_count=n.retry_count,
                error_message=n.error_message,
                sent_at=n.sent_at.isoformat(),
            )
            for n in logs
        ],
        count=len(logs),
    )


@router.get("/errors")
async def get_processing_errors(
    days: int = Query(default=7, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get recent processing errors (parse failures, etc.) for the Dashboard (Req 2.4, 7.7)."""
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    # Fetch reports with error statuses
    stmt = (
        select(Report)
        .where(
            Report.user_id == current_user.id,
            Report.status.in_(["parse_failed", "analysis_failed"]),
            Report.received_at >= start_date,
        )
        .order_by(Report.received_at.desc())
        .limit(50)
    )
    result = await db.execute(stmt)
    failed_reports = result.scalars().all()

    return {
        "errors": [
            {
                "id": str(r.id),
                "name": r.name,
                "file_type": r.file_type,
                "status": r.status,
                "received_at": r.received_at.isoformat(),
            }
            for r in failed_reports
        ],
        "count": len(failed_reports),
    }


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a report and all its data (admin only)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can delete reports.")

    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")

    await db.delete(report)
    await db.flush()


@router.put("/{report_id}/group")
async def assign_report_to_group(
    report_id: str,
    group_id: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Assign a report to a group (admin only). Pass group_id=null to unassign."""
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can assign reports to groups.")

    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")

    if group_id:
        from app.models.group import Group
        g_result = await db.execute(select(Group).where(Group.id == group_id))
        if g_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Group not found.")

    report.group_id = group_id
    await db.flush()

    return {"message": "Report group updated.", "report_id": str(report.id), "group_id": group_id}
