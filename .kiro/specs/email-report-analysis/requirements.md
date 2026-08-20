# Requirements Document

## Introduction

This document defines the requirements for an AI-powered agentic website that receives reports as email attachments (PDF, Excel, CSV), analyzes trends using open-source LLMs and ML algorithms, highlights deviations, and sends WhatsApp alerts when anomalies are detected. The system includes user authentication and a dashboard for viewing trends by report name.

## Glossary

- **System**: The AI-powered email report analysis web application
- **Email_Ingestion_Service**: The component responsible for receiving and processing incoming emails with report attachments
- **Report_Parser**: The component that extracts structured data from PDF, Excel, and CSV file attachments
- **Trend_Analyzer**: The component that uses open-source LLMs and ML algorithms to analyze trends in report data over time
- **Deviation_Detector**: The component that identifies statistically significant deviations from established trends
- **WhatsApp_Notifier**: The component that sends WhatsApp messages to configured recipients when deviations are detected
- **Authentication_Service**: The component that manages user login, session management, and access control
- **Dashboard**: The web interface where users view trends and deviations for their reports
- **Report**: A file attachment (PDF, Excel, or CSV) received via email containing data to be analyzed
- **Trend**: A pattern or direction identified in report data over multiple data points across time
- **Deviation**: A data point or pattern that differs significantly from the established trend
- **User**: An authenticated person who interacts with the Dashboard to view trends and manage alerts

## Requirements

### Requirement 1: Email Ingestion

**User Story:** As a user, I want the system to receive reports sent as email attachments, so that I can submit data for analysis without manual uploads.

#### Acceptance Criteria

1. WHEN an email with attachments is received, THE Email_Ingestion_Service SHALL extract all attachments that have a file extension of .pdf, .xlsx, .xls, or .csv, and are no larger than 25 MB each
2. WHEN an email contains attachments in unsupported formats, THE Email_Ingestion_Service SHALL ignore unsupported attachments and process only PDF, Excel, and CSV files
3. WHEN an email with no attachments is received, THE Email_Ingestion_Service SHALL discard the email and log the event
4. WHEN an attachment is successfully extracted, THE Email_Ingestion_Service SHALL associate the attachment with the sender's user account based on the sender email address
5. IF the sender email address does not match any registered user, THEN THE Email_Ingestion_Service SHALL discard the email and log a warning
6. IF a supported attachment exceeds 25 MB or cannot be extracted, THEN THE Email_Ingestion_Service SHALL skip that attachment, log the failure, and continue processing remaining attachments in the same email

### Requirement 2: Report Parsing

**User Story:** As a user, I want the system to extract structured data from my report files, so that the data can be analyzed for trends.

#### Acceptance Criteria

1. WHEN a PDF attachment is received, THE Report_Parser SHALL extract tabular data and text content from the PDF and produce a structured data output containing rows and columns for each table detected, within 120 seconds of receiving the file
2. WHEN an Excel attachment is received, THE Report_Parser SHALL extract cell values (resolved, not formulas) from all sheets in the workbook, preserving sheet names and row/column structure
3. WHEN a CSV attachment is received, THE Report_Parser SHALL parse all rows and columns using comma as the primary delimiter and supporting semicolon and tab as alternative delimiters based on auto-detection
4. IF a file is corrupted or cannot be parsed, THEN THE Report_Parser SHALL log the error including file name, sender, and failure reason, and notify the user via the Dashboard within 60 seconds of the failure
5. THE Report_Parser SHALL produce an equivalent data structure when valid Report data is parsed, serialized, and parsed again, where equivalence means identical row count, column count, and cell values
6. IF an attachment exceeds 50 MB in size, THEN THE Report_Parser SHALL reject the file and notify the user via the Dashboard with a message indicating the file size limit was exceeded
7. IF an attachment is password-protected or encrypted, THEN THE Report_Parser SHALL reject the file and notify the user via the Dashboard with a message indicating the file cannot be accessed
8. IF a file contains no extractable data rows, THEN THE Report_Parser SHALL log the event and notify the user via the Dashboard with a message indicating no data was found in the file

### Requirement 3: Trend Analysis

**User Story:** As a user, I want the system to analyze trends in my report data over time, so that I can understand patterns in my business metrics.

#### Acceptance Criteria

1. WHEN a new report is successfully parsed, THE Trend_Analyzer SHALL compare the extracted data against all previously stored data points for the same report name and produce a trend result containing the trend direction (increasing, decreasing, or stable), the percentage rate of change, and the list of data points used in the computation
2. THE Trend_Analyzer SHALL use open-source ML algorithms to identify trends across sequential report submissions, applying at least one of: linear regression, moving averages with a configurable window size between 3 and 12 data points, or seasonal decomposition based on the number of available data points
3. WHEN fewer than two data points exist for a report name, THE Trend_Analyzer SHALL store the data without generating trend analysis
4. WHEN a trend is successfully computed, THE Trend_Analyzer SHALL store the trend result and make it available on the Dashboard within 60 seconds of report ingestion
5. THE Trend_Analyzer SHALL support time-series trend detection including linear regression for 2 or more data points, moving averages for 3 or more data points, and seasonal decomposition for 12 or more data points
6. IF trend computation fails due to insufficient data quality or a processing error, THEN THE Trend_Analyzer SHALL store the raw data point, log the failure reason, and display a notification on the Dashboard indicating that trend analysis could not be completed for the affected report

### Requirement 4: Deviation Detection

**User Story:** As a user, I want the system to highlight deviations from trends, so that I can quickly identify anomalies that require attention.

#### Acceptance Criteria

1. WHEN a new trend analysis is completed, THE Deviation_Detector SHALL evaluate the latest data point against the established trend and produce a deviation score representing the magnitude of difference
2. WHEN a data point deviates from the trend by more than a configurable threshold (default: 2 standard deviations, configurable between 1.0 and 5.0 standard deviations), THE Deviation_Detector SHALL flag the data point as a deviation
3. THE Deviation_Detector SHALL classify deviations by severity: low (threshold to 2.5 standard deviations), medium (2.5 to 3.5 standard deviations), and high (greater than 3.5 standard deviations) based on the magnitude of deviation from the trend
4. WHEN a deviation is detected, THE Deviation_Detector SHALL record the deviation with timestamp, report name, metric name, expected value, actual value, deviation score, and severity level
5. THE Deviation_Detector SHALL use statistical methods including z-score analysis and interquartile range (using a 1.5× IQR multiplier) to identify outliers
6. IF fewer than 5 historical data points exist for a metric, THEN THE Deviation_Detector SHALL skip deviation analysis for that metric and log that insufficient data is available
7. WHEN multiple metrics in a single report deviate simultaneously, THE Deviation_Detector SHALL flag and record each metric deviation independently

### Requirement 5: WhatsApp Notification

**User Story:** As a user, I want to receive WhatsApp messages when deviations are detected, so that I am alerted immediately and can take action.

#### Acceptance Criteria

1. WHEN a deviation of medium or high severity is detected, THE WhatsApp_Notifier SHALL send a WhatsApp message to all verified phone numbers configured by the user within 30 seconds of deviation detection
2. THE WhatsApp_Notifier SHALL include the report name, metric name, deviation severity, expected value, and actual value in the message, with a maximum message length of 4096 characters
3. IF the WhatsApp message fails to send, THEN THE WhatsApp_Notifier SHALL retry delivery up to 3 times with exponential backoff starting at 5 seconds and doubling each subsequent retry
4. IF all retries are exhausted, THEN THE WhatsApp_Notifier SHALL log the failure and display a notification failure alert on the Dashboard
5. WHEN a user configures a new phone number, THE WhatsApp_Notifier SHALL validate that the number conforms to E.164 international format (country code prefix followed by 8 to 15 digits) before saving
6. IF a phone number fails format validation, THEN THE WhatsApp_Notifier SHALL reject the entry, not save the number, and display an error message indicating the expected format
7. IF a deviation of medium or high severity is detected and the user has no verified phone numbers configured, THEN THE WhatsApp_Notifier SHALL log the event and display a notification on the Dashboard indicating that no recipients are configured

### Requirement 6: User Authentication

**User Story:** As a user, I want to log in with a username and password, so that my data is secure and only I can access my reports.

#### Acceptance Criteria

1. WHEN a user submits valid credentials, THE Authentication_Service SHALL create a session and redirect the user to the Dashboard within 3 seconds
2. WHEN a user submits invalid credentials, THE Authentication_Service SHALL display a generic error message indicating that the credentials are incorrect without revealing whether the username or the password was wrong
3. IF a user submits invalid credentials 5 times consecutively within a 15-minute window, THEN THE Authentication_Service SHALL lock the account for 15 minutes and display a message indicating the account is temporarily locked
4. WHILE a user session is active, THE Authentication_Service SHALL allow access to protected resources associated with that user's account
5. WHEN a session has been inactive for more than 30 minutes, THE Authentication_Service SHALL expire the session and require re-authentication
6. THE Authentication_Service SHALL store passwords using bcrypt hashing with a minimum cost factor of 12
7. THE Authentication_Service SHALL require passwords to be between 8 and 128 characters in length and contain at least one uppercase letter, one lowercase letter, one digit, and one special character
8. IF a user attempts to access a protected resource without authentication, THEN THE Authentication_Service SHALL redirect the user to the login page and preserve the originally requested URL so that the user is redirected there after successful authentication

### Requirement 7: Trend Dashboard

**User Story:** As a user, I want to view trends for different reports by selecting the report name, so that I can monitor multiple data sources.

#### Acceptance Criteria

1. WHEN a user navigates to the Dashboard, THE Dashboard SHALL display a list of all report names associated with the user's account within 3 seconds of page load
2. WHEN a user selects a report name, THE Dashboard SHALL display the trend visualization for that report including historical data points and the computed trend line within 5 seconds of selection
3. THE Dashboard SHALL highlight deviation data points visually using a unique color for each severity level (low, medium, high) such that each severity is distinguishable from the others and from non-deviation data points
4. WHEN new trend data is available, THE Dashboard SHALL update the displayed visualization without requiring a page refresh within 30 seconds of the data becoming available
5. THE Dashboard SHALL allow the user to filter trend data by date range with a default view of the last 30 days and a maximum selectable range of 365 days
6. WHEN no reports exist for a user, THE Dashboard SHALL display a message instructing the user how to submit reports via email
7. IF the Dashboard fails to load trend data for a selected report, THEN THE Dashboard SHALL display an error message indicating the data could not be retrieved and provide an option to retry

### Requirement 8: WhatsApp Number Management

**User Story:** As a user, I want to manage the phone numbers that receive deviation alerts, so that I can control who gets notified.

#### Acceptance Criteria

1. WHEN a user adds a phone number in E.164 international format (country code followed by subscriber number, 8 to 15 digits total), THE System SHALL store the number associated with the user's account with a status of "pending verification"
2. WHEN a user removes a phone number, THE System SHALL stop sending notifications to that number for future deviations and remove it from the user's configuration
3. IF a user attempts to add a phone number that would exceed the maximum of 10 configured numbers, THEN THE System SHALL reject the addition and display a message indicating the limit has been reached
4. WHEN a user adds a phone number, THE System SHALL send a verification message containing a unique code to that number, and the number SHALL be marked as "verified" only after the user submits the correct code via the Dashboard
5. IF the verification code is not submitted within 24 hours of sending, THEN THE System SHALL remove the unverified number from the user's configuration
6. WHILE a phone number has a status of "pending verification", THE System SHALL NOT send deviation alert notifications to that number
7. IF a user attempts to add a phone number that already exists in their configuration, THEN THE System SHALL reject the addition and display a message indicating the number is already configured
