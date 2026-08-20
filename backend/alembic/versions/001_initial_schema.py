"""Initial schema with TimescaleDB hypertable on data_point.

Revision ID: 001
Revises: None
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable TimescaleDB extension
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")

    # Create user table
    op.create_table(
        "user",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(150), unique=True, nullable=False),
        sa.Column("email", sa.String(320), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(128), nullable=False),
        sa.Column("failed_login_attempts", sa.Integer, default=0),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_active", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_user_username", "user", ["username"])
    op.create_index("ix_user_email", "user", ["email"])

    # Create report table
    op.create_table(
        "report",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("source_email", sa.String(320), nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("file_type", sa.String(10), nullable=False),
        sa.Column("file_size_bytes", sa.Integer, nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="received"),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_report_user_id", "report", ["user_id"])
    op.create_index("ix_report_name", "report", ["name"])

    # Create data_point table
    op.create_table(
        "data_point",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "report_id",
            UUID(as_uuid=True),
            sa.ForeignKey("report.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("metric_name", sa.String(255), nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("data_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    # Composite index for efficient trend lookups
    op.create_index(
        "ix_data_point_report_metric_timestamp",
        "data_point",
        ["report_id", "metric_name", "data_timestamp"],
    )

    # Convert data_point to TimescaleDB hypertable
    op.execute(
        "SELECT create_hypertable('data_point', 'data_timestamp', "
        "migrate_data => true, if_not_exists => true)"
    )

    # Create trend_result table
    op.create_table(
        "trend_result",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "report_id",
            UUID(as_uuid=True),
            sa.ForeignKey("report.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("metric_name", sa.String(255), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("rate_of_change_pct", sa.Float, nullable=False),
        sa.Column("algorithm_used", sa.String(50), nullable=False),
        sa.Column("data_points_count", sa.Integer, nullable=False),
        sa.Column("trend_data", JSONB, nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_trend_result_report_id", "trend_result", ["report_id"])

    # Create deviation_record table
    op.create_table(
        "deviation_record",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "report_id",
            UUID(as_uuid=True),
            sa.ForeignKey("report.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("metric_name", sa.String(255), nullable=False),
        sa.Column("expected_value", sa.Float, nullable=False),
        sa.Column("actual_value", sa.Float, nullable=False),
        sa.Column("deviation_score", sa.Float, nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("threshold_used", sa.Float, nullable=False),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_deviation_record_report_id", "deviation_record", ["report_id"])

    # Create phone_number table
    op.create_table(
        "phone_number",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.String(20), nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="pending_verification",
        ),
        sa.Column("verification_code", sa.String(10), nullable=True),
        sa.Column("verification_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_phone_number_user_id", "phone_number", ["user_id"])

    # Create notification_log table
    op.create_table(
        "notification_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "deviation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("deviation_record.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("phone_number", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("retry_count", sa.Integer, default=0),
        sa.Column("error_message", sa.String(1000), nullable=True),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_notification_log_user_id", "notification_log", ["user_id"])
    op.create_index(
        "ix_notification_log_deviation_id", "notification_log", ["deviation_id"]
    )


def downgrade() -> None:
    op.drop_table("notification_log")
    op.drop_table("phone_number")
    op.drop_table("deviation_record")
    op.drop_table("trend_result")
    op.drop_table("data_point")
    op.drop_table("report")
    op.drop_table("user")
    op.execute("DROP EXTENSION IF EXISTS timescaledb CASCADE")
