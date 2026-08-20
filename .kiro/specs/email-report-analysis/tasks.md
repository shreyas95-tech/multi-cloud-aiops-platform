# Implementation Plan: Email Report Analysis

## Overview

This plan breaks the email report analysis feature into incremental coding tasks. The system is built in Python (FastAPI backend, Celery workers) with a React frontend. Tasks progress from foundational setup through each pipeline component, wiring everything together at the end.

## Tasks

- [x] 1. Set up project structure, database models, and core interfaces
  - [x] 1.1 Create project directory structure and configuration files
    - Create backend directory structure: `backend/app/{api,services,models,workers,tests}`
    - Create frontend directory structure: `frontend/src/{components,pages,services,hooks}`
    - Set up `pyproject.toml` with dependencies: FastAPI, SQLAlchemy, Celery, Redis, pdfplumber, openpyxl, scikit-learn, statsmodels, scipy, PyOD, hypothesis, bcrypt, PyJWT, imapclient, whatsapp-python
    - Set up `package.json` with React, Chart.js, and WebSocket dependencies
    - Create `.env.example` with required environment variables (IMAP, WhatsApp API, DB, Redis)
    - _Requirements: All_

  - [x] 1.2 Define SQLAlchemy data models and TimescaleDB schema
    - Create `backend/app/models/` with User, Report, DataPoint, TrendResult, DeviationRecord, PhoneNumber, NotificationLog models
    - Define relationships, indexes (composite on report_id + metric_name + data_timestamp), and constraints
    - Create Alembic migration for initial schema with TimescaleDB hypertable on `data_point`
    - _Requirements: 1.4, 2.5, 3.1, 4.4, 5.5, 6.6, 8.1_

  - [x] 1.3 Define core data classes, enums, and interfaces
    - Create `backend/app/models/schemas.py` with Pydantic models: DataTable, TrendResult, DeviationRecord, ParseResult, IngestionResult, AuthResult, NotificationResult
    - Create enums: TrendDirection, DeviationSeverity, PhoneNumberStatus
    - Define constants: MAX_ATTACHMENT_SIZE_MB, SUPPORTED_EXTENSIONS, SEVERITY_THRESHOLDS
    - _Requirements: 2.5, 3.1, 4.3, 4.4, 5.2_

  - [x] 1.4 Set up Celery worker configuration and Redis connection
    - Create `backend/app/workers/celery_app.py` with Celery configuration
    - Define task chains: ingest → parse → analyze → detect → notify
    - Configure Redis as broker and result backend
    - _Requirements: 1.1, 3.4_

- [x] 2. Implement Authentication Service
  - [x] 2.1 Implement password hashing, validation, and user registration
    - Create `backend/app/services/auth_service.py` with bcrypt hashing (cost factor 12)
    - Implement password strength validation: 8-128 chars, uppercase, lowercase, digit, special character
    - Implement user registration endpoint
    - _Requirements: 6.6, 6.7_

  - [ ]* 2.2 Write property test for password validation rules
    - **Property 14: Password Validation Rules**
    - **Validates: Requirements 6.7**

  - [x] 2.3 Implement login, JWT session creation, and rate limiting
    - Implement login endpoint with generic error messages (no field-specific hints)
    - Create JWT token with 30-minute expiry
    - Implement failed attempt tracking with Redis (5 attempts / 15-minute window → lockout)
    - _Requirements: 6.1, 6.2, 6.3_

  - [ ]* 2.4 Write property test for account lockout after failed attempts
    - **Property 15: Account Lockout After Failed Attempts**
    - **Validates: Requirements 6.3**

  - [x] 2.5 Implement session validation and inactivity expiry
    - Create `get_current_user` dependency that validates JWT and checks last activity
    - Expire sessions after 30 minutes of inactivity
    - Redirect unauthenticated users to login page preserving original URL
    - _Requirements: 6.4, 6.5, 6.8_

  - [ ]* 2.6 Write property test for session expiry on inactivity
    - **Property 16: Session Expiry on Inactivity**
    - **Validates: Requirements 6.5**

- [ ] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement Email Ingestion Service
  - [x] 4.1 Implement IMAP polling and email processing
    - Create `backend/app/services/email_ingestion.py` with IMAP connection via `imapclient`
    - Implement `poll_mailbox()` to fetch unread emails
    - Implement `process_email()` to validate sender against registered users
    - Implement `filter_attachments()` to accept only .pdf/.xlsx/.xls/.csv ≤ 25 MB
    - Associate valid attachments with sender's user account
    - Discard emails from unregistered senders with warning log
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [ ]* 4.2 Write property test for attachment filtering correctness
    - **Property 1: Attachment Filtering Correctness**
    - **Validates: Requirements 1.1, 1.2, 1.6**

  - [ ]* 4.3 Write property test for sender-user association
    - **Property 2: Sender-User Association**
    - **Validates: Requirements 1.4, 1.5**

  - [x] 4.4 Create Celery task for periodic email polling
    - Create `backend/app/workers/email_tasks.py` with periodic IMAP poll task
    - On successful extraction, queue report parsing task with attachment metadata
    - Implement structured JSON logging with correlation IDs
    - _Requirements: 1.1, 1.4_

- [x] 5. Implement Report Parser
  - [x] 5.1 Implement PDF parser using pdfplumber
    - Create `backend/app/services/report_parser.py`
    - Implement `parse_pdf()` using pdfplumber to extract tables
    - Handle corrupted files, encrypted files, and files with no data rows
    - Enforce 120-second timeout and 50 MB size limit
    - _Requirements: 2.1, 2.4, 2.6, 2.7, 2.8_

  - [x] 5.2 Implement Excel parser using openpyxl
    - Implement `parse_excel()` to extract resolved cell values from all sheets
    - Preserve sheet names and row/column structure
    - Handle password-protected workbooks and corrupted files
    - _Requirements: 2.2, 2.4, 2.7_

  - [x] 5.3 Implement CSV parser with auto-delimiter detection
    - Implement `parse_csv()` with support for comma, semicolon, and tab delimiters
    - Implement `detect_delimiter()` using file sample analysis
    - Handle empty files and malformed CSV
    - _Requirements: 2.3, 2.8_

  - [ ]* 5.4 Write property test for CSV delimiter detection
    - **Property 4: CSV Delimiter Detection**
    - **Validates: Requirements 2.3**

  - [ ]* 5.5 Write property test for report parsing round-trip
    - **Property 3: Report Parsing Round-Trip**
    - **Validates: Requirements 2.5**

  - [x] 5.6 Create Celery task for report parsing pipeline
    - Create `backend/app/workers/parse_tasks.py` that routes to correct parser
    - Store parsed DataTable to database
    - Queue trend analysis on success; notify user on failure via Dashboard
    - _Requirements: 2.1, 2.4, 3.4_

- [ ] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement Trend Analyzer
  - [x] 7.1 Implement trend analysis algorithms
    - Create `backend/app/services/trend_analyzer.py`
    - Implement `linear_regression()` using scikit-learn LinearRegression (N ≥ 2)
    - Implement `moving_average()` with configurable window size 3–12 (N ≥ 3)
    - Implement `seasonal_decomposition()` using statsmodels (N ≥ 12)
    - Implement `select_algorithm()` to pick applicable algorithms based on data point count
    - _Requirements: 3.2, 3.5_

  - [ ]* 7.2 Write property test for algorithm selection by data point count
    - **Property 5: Algorithm Selection by Data Point Count**
    - **Validates: Requirements 3.2, 3.3, 3.5**

  - [x] 7.3 Implement trend computation orchestration
    - Implement `analyze()` method: fetch historical data, apply algorithms, produce TrendResult
    - Return None when fewer than 2 data points exist
    - Store TrendResult with direction, rate_of_change_pct, algorithm_used, data_points_used
    - Handle computation failures gracefully (store raw data, log, notify user)
    - _Requirements: 3.1, 3.3, 3.4, 3.6_

  - [ ]* 7.4 Write property test for trend result completeness
    - **Property 6: Trend Result Completeness**
    - **Validates: Requirements 3.1**

  - [x] 7.5 Create Celery task for trend analysis
    - Create `backend/app/workers/trend_tasks.py` that triggers analysis after parsing
    - Queue deviation detection on successful trend computation
    - _Requirements: 3.4_

- [x] 8. Implement Deviation Detector
  - [x] 8.1 Implement z-score and IQR deviation detection
    - Create `backend/app/services/deviation_detector.py`
    - Implement `compute_zscore()` for z-score analysis
    - Implement `compute_iqr_outlier()` with 1.5× IQR multiplier
    - Implement `classify_severity()`: low (2.0–2.5σ), medium (2.5–3.5σ), high (>3.5σ)
    - Skip detection when fewer than 5 historical points exist
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 4.6_

  - [ ]* 8.2 Write property test for deviation severity classification
    - **Property 7: Deviation Severity Classification**
    - **Validates: Requirements 4.2, 4.3**

  - [ ]* 8.3 Write property test for minimum data point guard
    - **Property 9: Minimum Data Point Guard**
    - **Validates: Requirements 4.6**

  - [x] 8.4 Implement multi-metric deviation detection and recording
    - Implement `detect()` to evaluate each metric independently
    - Record complete DeviationRecord per deviating metric (timestamp, report name, metric, expected, actual, score, severity)
    - Queue WhatsApp notification for medium/high severity
    - _Requirements: 4.4, 4.7_

  - [ ]* 8.5 Write property test for deviation record completeness
    - **Property 8: Deviation Record Completeness**
    - **Validates: Requirements 4.4**

  - [ ]* 8.6 Write property test for independent multi-metric deviation detection
    - **Property 10: Independent Multi-Metric Deviation Detection**
    - **Validates: Requirements 4.7**

  - [x] 8.7 Create Celery task for deviation detection
    - Create `backend/app/workers/deviation_tasks.py` triggered after trend analysis
    - Push deviation updates via WebSocket to connected Dashboard clients
    - _Requirements: 4.1, 7.4_

- [ ] 9. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implement WhatsApp Notifier
  - [x] 10.1 Implement WhatsApp message formatting and sending
    - Create `backend/app/services/whatsapp_notifier.py`
    - Implement `format_message()` with report name, metric, severity, expected/actual values (max 4096 chars)
    - Implement `send_with_retry()` with exponential backoff (5s, 10s, 20s), max 3 retries
    - Only send for medium/high severity to verified phone numbers
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.7_

  - [ ]* 10.2 Write property test for WhatsApp message content completeness
    - **Property 11: WhatsApp Message Content Completeness**
    - **Validates: Requirements 5.2**

  - [ ]* 10.3 Write property test for notification recipient filtering
    - **Property 13: Notification Recipient Filtering**
    - **Validates: Requirements 5.1, 8.6**

  - [x] 10.4 Implement E.164 phone number validation
    - Implement `validate_e164()` to accept only valid E.164 format (country code + 8–15 digits)
    - Reject invalid numbers with descriptive error message
    - _Requirements: 5.5, 5.6_

  - [ ]* 10.5 Write property test for E.164 phone number validation
    - **Property 12: E.164 Phone Number Validation**
    - **Validates: Requirements 5.5, 5.6**

  - [x] 10.6 Create Celery task for WhatsApp notifications
    - Create `backend/app/workers/notification_tasks.py` triggered by deviation detection
    - Log failures and surface notification errors on Dashboard
    - _Requirements: 5.3, 5.4_

- [x] 11. Implement WhatsApp Number Management
  - [x] 11.1 Implement phone number CRUD and verification flow
    - Create `backend/app/api/phone_numbers.py` with endpoints: add, remove, verify
    - Enforce maximum 10 numbers per user
    - Enforce uniqueness within user configuration
    - Implement verification code generation and sending
    - Store new numbers as "pending_verification"; mark "verified" on correct code
    - Remove unverified numbers after 24-hour expiry
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [ ]* 11.2 Write property test for phone number uniqueness and limit enforcement
    - **Property 18: Phone Number Uniqueness and Limit Enforcement**
    - **Validates: Requirements 8.3, 8.7**

  - [ ]* 11.3 Write property test for verification lifecycle
    - **Property 19: Verification Lifecycle**
    - **Validates: Requirements 8.1, 8.4, 8.5**

- [x] 12. Implement Dashboard API
  - [x] 12.1 Implement report listing and trend data endpoints
    - Create `backend/app/api/dashboard.py` with FastAPI router
    - Implement `GET /reports` to list all report names for authenticated user
    - Implement `GET /reports/{report_name}/trends` with date range filter (default 30 days, max 365)
    - Implement `GET /reports/{report_name}/deviations` to list deviation records
    - _Requirements: 7.1, 7.2, 7.5_

  - [ ]* 12.2 Write property test for date range filter constraints
    - **Property 17: Date Range Filter Constraints**
    - **Validates: Requirements 7.5**

  - [x] 12.3 Implement WebSocket server for real-time updates
    - Create `backend/app/api/websocket.py` with authenticated WebSocket endpoint
    - Push new trend results and deviation records to connected clients
    - _Requirements: 7.4_

- [ ] 13. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 14. Implement React Frontend Dashboard
  - [x] 14.1 Set up React app with routing and authentication
    - Create React app with React Router
    - Implement login page, auth context, and protected route wrapper
    - Implement session expiry detection and redirect to login
    - _Requirements: 6.1, 6.8, 7.1_

  - [x] 14.2 Implement report list and trend visualization page
    - Create report list component that fetches and displays report names
    - Create trend chart component using Chart.js with historical data points and trend line
    - Highlight deviation points with severity-specific colors (distinct for low/medium/high)
    - Implement date range filter (default 30 days, max 365 days)
    - _Requirements: 7.1, 7.2, 7.3, 7.5, 7.6, 7.7_

  - [x] 14.3 Implement real-time WebSocket updates
    - Create WebSocket hook that connects to `/ws/updates`
    - Update trend visualization without page refresh when new data arrives
    - _Requirements: 7.4_

  - [x] 14.4 Implement phone number management UI
    - Create settings page with phone number list (verified/pending status)
    - Implement add number form with E.164 validation feedback
    - Implement verification code submission form
    - Implement remove number with confirmation
    - Show error messages for limit exceeded and duplicate numbers
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.7_

- [x] 15. Integration and wiring
  - [x] 15.1 Wire the full Celery pipeline end-to-end
    - Connect email ingestion → report parsing → trend analysis → deviation detection → notification
    - Ensure correlation IDs propagate through all pipeline stages
    - Configure structured JSON logging across all workers
    - _Requirements: 1.1, 3.4, 4.1, 5.1_

  - [x] 15.2 Wire frontend to backend API with error handling
    - Connect all React pages to FastAPI endpoints
    - Implement error states: loading, failure with retry, empty states with guidance
    - Ensure Dashboard displays notification failures and parse errors
    - _Requirements: 7.7, 5.4, 2.4_

  - [ ]* 15.3 Write integration tests for end-to-end pipeline
    - Test email → parse → trend → deviation → notification flow
    - Test WebSocket real-time updates
    - Test error propagation (corrupted file, failed notification)
    - _Requirements: All_

- [ ] 16. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The backend uses Python (FastAPI + Celery) and the frontend uses React + Chart.js
- Hypothesis is the PBT library for all property-based tests (Python)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4"] },
    { "id": 2, "tasks": ["2.1", "4.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "4.2", "4.3", "4.4"] },
    { "id": 4, "tasks": ["2.4", "2.5", "5.1", "5.2", "5.3"] },
    { "id": 5, "tasks": ["2.6", "5.4", "5.5", "5.6"] },
    { "id": 6, "tasks": ["7.1"] },
    { "id": 7, "tasks": ["7.2", "7.3"] },
    { "id": 8, "tasks": ["7.4", "7.5", "8.1"] },
    { "id": 9, "tasks": ["8.2", "8.3", "8.4"] },
    { "id": 10, "tasks": ["8.5", "8.6", "8.7"] },
    { "id": 11, "tasks": ["10.1", "10.4", "11.1"] },
    { "id": 12, "tasks": ["10.2", "10.3", "10.5", "10.6", "11.2", "11.3"] },
    { "id": 13, "tasks": ["12.1", "12.3"] },
    { "id": 14, "tasks": ["12.2", "14.1"] },
    { "id": 15, "tasks": ["14.2", "14.3", "14.4"] },
    { "id": 16, "tasks": ["15.1", "15.2"] },
    { "id": 17, "tasks": ["15.3"] }
  ]
}
```
