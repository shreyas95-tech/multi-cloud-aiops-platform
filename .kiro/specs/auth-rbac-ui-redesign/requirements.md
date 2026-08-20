# Requirements Document

## Introduction

This feature adds authentication, role-based access control (RBAC), and a UI redesign to the Multi-Cloud AIOps Platform. Currently the platform has no authentication system — all endpoints are publicly accessible. This feature introduces secure login with JWT-based sessions, two user roles (Admin and L1), a knowledge base (KB) document system, and a refreshed visual design for the login page and operations dashboard.

## Glossary

- **Platform**: The Multi-Cloud AIOps Platform web application (FastAPI backend + HTML/CSS/JS frontend)
- **Auth_Service**: The backend authentication module responsible for login, logout, token management, and password operations
- **RBAC_Service**: The backend authorization module that enforces role-based permissions on protected endpoints
- **User_Management_Service**: The backend module responsible for creating, listing, and managing user accounts
- **KB_Service**: The backend module responsible for knowledge base document upload, storage, and retrieval
- **Admin**: A user role with full platform access including query submission, KB upload, and user management
- **L1_User**: A user role with read-only access limited to viewing KB articles
- **JWT**: JSON Web Token used as the session credential for authenticated requests
- **Login_Page**: The frontend page where users enter credentials to authenticate
- **Ops_Dashboard**: The main frontend page displaying platform functionality after authentication
- **First_Time_Flag**: A boolean attribute on a user account indicating the user has not yet changed their initial password

## Requirements

### Requirement 1: User Authentication - Login

**User Story:** As a platform user, I want to log in with my credentials, so that I can securely access the platform features assigned to my role.

#### Acceptance Criteria

1. WHEN a user submits valid credentials (username and password), THE Auth_Service SHALL return a JWT access token and the user's role
2. WHEN a user submits invalid credentials, THE Auth_Service SHALL return a 401 Unauthorized response with an error message "Invalid username or password"
3. THE Auth_Service SHALL hash all stored passwords using bcrypt with a minimum work factor of 12
4. WHEN more than 5 failed login attempts occur for a single username within a 15-minute window, THE Auth_Service SHALL reject subsequent login attempts for that username for 15 minutes with a 429 Too Many Requests response
5. THE Auth_Service SHALL issue JWT tokens with an expiry time of 60 minutes

### Requirement 2: User Authentication - Logout

**User Story:** As a platform user, I want to log out of the platform, so that my session is terminated and unauthorized access is prevented.

#### Acceptance Criteria

1. WHEN an authenticated user submits a logout request, THE Auth_Service SHALL invalidate the current JWT token
2. WHEN a request is made with an invalidated token, THE Auth_Service SHALL return a 401 Unauthorized response

### Requirement 3: Password Reset

**User Story:** As a platform user, I want to reset my password when I forget it, so that I can regain access to my account.

#### Acceptance Criteria

1. WHEN a user requests a password reset with a valid username, THE Auth_Service SHALL generate a one-time reset token with a 30-minute expiry
2. WHEN a user submits a valid reset token and a new password, THE Auth_Service SHALL update the stored password hash and invalidate the reset token
3. WHEN a user submits an expired or invalid reset token, THE Auth_Service SHALL return a 400 Bad Request response with the message "Reset token is invalid or expired"
4. THE Auth_Service SHALL enforce that new passwords contain a minimum of 8 characters, at least one uppercase letter, one lowercase letter, one digit, and one special character

### Requirement 4: First-Time Login Password Change

**User Story:** As a new platform user, I want to be required to change my initial password on first login, so that my account is secured with a password only I know.

#### Acceptance Criteria

1. WHEN a user with the First_Time_Flag set to true successfully authenticates, THE Auth_Service SHALL return a response indicating a password change is required before granting full access
2. WHEN a first-time user submits a new password that meets the password policy, THE Auth_Service SHALL update the password, set First_Time_Flag to false, and issue a standard JWT token
3. WHILE a user's First_Time_Flag is true, THE RBAC_Service SHALL restrict the user to only the password-change endpoint

### Requirement 5: Role-Based Access Control

**User Story:** As a platform administrator, I want to restrict features based on user roles, so that L1 users cannot perform privileged operations.

#### Acceptance Criteria

1. THE RBAC_Service SHALL support exactly two roles: Admin and L1_User
2. WHEN an L1_User attempts to access the query submission endpoint (POST /api/query), THE RBAC_Service SHALL return a 403 Forbidden response
3. WHEN an L1_User attempts to access the KB upload endpoint, THE RBAC_Service SHALL return a 403 Forbidden response
4. WHEN an L1_User attempts to access the user management endpoints, THE RBAC_Service SHALL return a 403 Forbidden response
5. WHEN an Admin user accesses any platform endpoint, THE RBAC_Service SHALL permit the request
6. WHEN an unauthenticated request is made to any protected endpoint, THE RBAC_Service SHALL return a 401 Unauthorized response

### Requirement 6: User Management (Admin Only)

**User Story:** As an Admin user, I want to create new user accounts and assign roles, so that I can onboard team members with appropriate access levels.

#### Acceptance Criteria

1. WHEN an Admin submits a create-user request with a username, temporary password, and role (Admin or L1_User), THE User_Management_Service SHALL create the account with First_Time_Flag set to true
2. WHEN an Admin submits a create-user request with a username that already exists, THE User_Management_Service SHALL return a 409 Conflict response with the message "Username already exists"
3. WHEN an Admin requests the user list, THE User_Management_Service SHALL return all user accounts with their username, role, and creation timestamp
4. THE User_Management_Service SHALL validate that the assigned role is one of the supported roles (Admin, L1_User)

### Requirement 7: Knowledge Base Document Upload (Admin Only)

**User Story:** As an Admin user, I want to upload knowledge base documents, so that L1 users can reference them for operational guidance.

#### Acceptance Criteria

1. WHEN an Admin submits a KB document with a title and file content, THE KB_Service SHALL store the document and return a unique document identifier
2. THE KB_Service SHALL accept documents in PDF, DOCX, and plain text formats with a maximum file size of 10 MB
3. WHEN an Admin uploads a document exceeding 10 MB, THE KB_Service SHALL return a 413 Payload Too Large response
4. THE KB_Service SHALL store the uploading Admin's username and upload timestamp with each document

### Requirement 8: Knowledge Base Document Viewing

**User Story:** As an L1 user, I want to view knowledge base articles uploaded by the Admin, so that I can reference operational procedures and documentation.

#### Acceptance Criteria

1. WHEN an authenticated user requests the KB document list, THE KB_Service SHALL return a list of all documents with title, upload date, and uploader name
2. WHEN an authenticated user requests a specific KB document by identifier, THE KB_Service SHALL return the document content
3. WHEN a user requests a non-existent document identifier, THE KB_Service SHALL return a 404 Not Found response

### Requirement 9: Login Page UI Design

**User Story:** As a platform user, I want a visually appealing login page, so that the platform conveys professionalism and trustworthiness.

#### Acceptance Criteria

1. THE Login_Page SHALL display a centered login form with fields for username and password, and a submit button
2. THE Login_Page SHALL use a color palette based on dark navy (#1e293b) for the background, white (#ffffff) for the card surface, and teal-blue (#0ea5e9) as the primary accent color
3. THE Login_Page SHALL display the platform name "Multi-Cloud AIOps Platform" as a heading above the login form
4. THE Login_Page SHALL display inline validation error messages below the relevant input field when submission fails
5. THE Login_Page SHALL be responsive and render correctly on viewport widths from 320px to 1920px

### Requirement 10: Ops Dashboard UI Redesign

**User Story:** As a platform user, I want an attractive and modern operations dashboard, so that the platform is easy to navigate and visually consistent.

#### Acceptance Criteria

1. THE Ops_Dashboard SHALL use a sidebar navigation layout with the main content area on the right
2. THE Ops_Dashboard SHALL use the same color palette as the Login_Page (dark navy background for sidebar, white content cards, teal-blue accent)
3. THE Ops_Dashboard SHALL display navigation items based on the authenticated user's role — Admin sees: Query, KB Upload, KB Articles, User Management; L1_User sees: KB Articles only
4. THE Ops_Dashboard SHALL display the authenticated user's username and role in the sidebar header
5. THE Ops_Dashboard SHALL include a logout button in the sidebar that triggers the logout flow
6. THE Ops_Dashboard SHALL be responsive, collapsing the sidebar into a hamburger menu on viewport widths below 768px
