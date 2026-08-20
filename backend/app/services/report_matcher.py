"""Report matching service.

Determines which report an incoming email attachment should be appended to.

Priority:
1. Admin-defined ingestion rules (explicit mappings)
2. Subject line pattern matching (convention: "Report: <report_name>")
3. No match → create a new report
"""

import re
from pathlib import Path
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ingestion_rule import IngestionRule
from app.models.report import Report

logger = structlog.get_logger(__name__)

# Subject line patterns to extract report name
# Supports: "Report: Sales Data", "Daily Report - Tickets", "[Report] Cloud Infra"
SUBJECT_PATTERNS = [
    r"(?:report|daily report|weekly report)\s*[:\-\|]\s*(.+)",  # "Report: Name" or "Daily Report - Name"
    r"\[report\]\s*(.+)",  # "[Report] Name"
    r"(.+?)\s*(?:report|data|update)\s*$",  # "Tickets Report" or "Sales Data"
]


async def match_email_to_report(
    db: AsyncSession,
    subject: str,
    filename: str,
    sender: str,
    user_id: str,
    group_id: str = None,
) -> Optional[dict]:
    """Match an incoming email to an existing report.

    Returns:
        Dict with 'report_name' and 'match_type' if matched, None if no match.
        match_type: 'rule', 'subject', or None (create new)
    """
    log = logger.bind(operation="match_email", subject=subject, filename=filename, sender=sender)

    # --- Priority 1: Admin-defined rules ---
    rules_result = await db.execute(
        select(IngestionRule)
        .where(IngestionRule.is_active == True)
        .order_by(IngestionRule.priority.asc())
    )
    rules = rules_result.scalars().all()

    for rule in rules:
        if rule.matches(subject, filename, sender):
            log.info("matched_by_rule", rule_name=rule.name, target=rule.target_report_name)
            return {
                "report_name": rule.target_report_name,
                "match_type": "rule",
                "rule_name": rule.name,
            }

    # --- Priority 2: Subject line pattern ---
    report_name = _extract_report_name_from_subject(subject)
    if report_name:
        # Verify this report exists for the user/group
        if group_id:
            existing = await db.execute(
                select(Report).where(Report.name == report_name, Report.group_id == group_id)
            )
        else:
            existing = await db.execute(
                select(Report).where(Report.name == report_name, Report.user_id == user_id)
            )

        if existing.scalar_one_or_none() is not None:
            log.info("matched_by_subject", report_name=report_name)
            return {
                "report_name": report_name,
                "match_type": "subject",
            }

    # --- Priority 3: Filename stem matches existing report name ---
    filename_stem = Path(filename).stem if filename else ""
    if filename_stem:
        if group_id:
            existing = await db.execute(
                select(Report).where(Report.name == filename_stem, Report.group_id == group_id)
            )
        else:
            existing = await db.execute(
                select(Report).where(Report.name == filename_stem, Report.user_id == user_id)
            )
        if existing.scalar_one_or_none() is not None:
            log.info("matched_by_filename_stem", report_name=filename_stem)
            return {
                "report_name": filename_stem,
                "match_type": "filename",
            }

    # --- Priority 4: Fuzzy match - filename contains existing report name or vice versa ---
    if group_id:
        all_reports = await db.execute(select(Report).where(Report.group_id == group_id))
    else:
        all_reports = await db.execute(select(Report).where(Report.user_id == user_id))
    
    for report in all_reports.scalars().all():
        report_name_lower = report.name.lower()
        filename_lower = filename.lower() if filename else ""
        subject_lower = subject.lower()
        
        # Check if report name appears in filename or subject
        if report_name_lower in filename_lower or report_name_lower in subject_lower:
            log.info("matched_by_fuzzy", report_name=report.name)
            return {
                "report_name": report.name,
                "match_type": "fuzzy",
            }

    # --- No match ---
    log.info("no_match_found")
    return None


def _extract_report_name_from_subject(subject: str) -> Optional[str]:
    """Extract a report name from an email subject line.

    Supports patterns like:
    - "Report: Tesco Tickets"
    - "Daily Report - Cloud Infra"
    - "[Report] Inventory Count"
    - "Tesco Tickets Report"
    """
    subject_clean = subject.strip()

    for pattern in SUBJECT_PATTERNS:
        match = re.search(pattern, subject_clean, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            # Clean up common suffixes/prefixes
            name = re.sub(r"\s*[-_]\s*\d{4}[-/]\d{2}[-/]\d{2}.*$", "", name)  # Remove dates
            name = re.sub(r"\s*[-_]\s*\d{2}[-/]\d{2}[-/]\d{4}.*$", "", name)
            name = name.strip(" -_|[]")
            if len(name) > 2:
                return name

    return None
