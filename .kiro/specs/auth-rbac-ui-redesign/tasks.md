# Implementation Plan: Auth, RBAC & UI Redesign

## Overview

This plan implements JWT-based authentication, role-based access control, knowledge base document management, and a UI overhaul for the Multi-Cloud AIOps Platform. Tasks are ordered to build foundational layers first (database, security utilities), then middleware, then routes, then frontend, and finally integration with existing endpoints. Python (FastAPI) is used for all backend code; vanilla HTML/CSS/JS for the frontend.

## Tasks

- [x] 1. Install dependencies and set up database layer
  - [x] 1.1 Add new dependencies to requirements.txt and create database module
    - Add `python-jose[cryptography]==3.3.0`, `passlib[bcrypt]==1.7.4`, `python-multipart==0.0.9`, `aiosqlite==0.20.0` to `backend/requirements.txt`
    - Create `backend/database.py` with async SQLite connection pool, table initialization (users, reset_tokens, kb_documents, token_blacklist, login_attempts), and a startup function to create tables if not exists
    - Create `uploads/kb/` directory for file storage
    - _Requirements: 1.3, 1.4, 2.1, 3.1, 6.1, 7.1_

  - [x] 1.2 Create Pydantic request/response models
    - Create `backend/models.py` with all request models (LoginRequest, CreateUserRequest, PasswordResetRequest, PasswordResetConfirm, ChangePasswordRequest) and response models (LoginResponse, UserResponse, KBDocumentMeta)
    - Include field validation constraints as specified in the design (min_length, max_length, pattern, Literal for roles)
    - _Requirements: 1.1, 3.4, 6.1, 6.4_

- [x] 2. Implement security utilities
  - [x] 2.1 Create security module with JWT, bcrypt, and password policy
    - Create `backend/security.py` with:
      - `hash_password(password: str) -> str` using bcrypt with work factor 12
      - `verify_password(plain: str, hashed: str) -> bool`
      - `create_access_token(username: str, role: str, first_time: bool) -> str` with 60-min expiry and unique `jti`
      - `decode_access_token(token: str) -> dict` with expiry validation
      - `validate_password_policy(password: str) -> bool` enforcing 8+ chars, uppercase, lowercase, digit, special char
      - `generate_reset_token() -> str` for one-time reset tokens
    - Load JWT secret from environment variable `JWT_SECRET_KEY` with a fallback default for development
    - _Requirements: 1.1, 1.3, 1.5, 3.1, 3.4_

  - [x] 2.2 Implement login rate limiter
    - Add to `backend/security.py` a `RateLimiter` class that:
      - Tracks failed login attempts per username using the `login_attempts` database table
      - Rejects attempts after 5 failures within a 15-minute rolling window (returns True for "is_locked")
      - Resets the window on successful login
      - Reconstructs state from database on initialization
    - _Requirements: 1.4_

  - [x] 2.3 Write property tests for password policy (Property 7)
    - **Property 7: Password Policy Validation**
    - Test that `validate_password_policy` accepts strings if and only if they meet all criteria (8+ chars, uppercase, lowercase, digit, special char)
    - Use Hypothesis to generate arbitrary strings and verify the function's accept/reject decision matches the policy definition
    - **Validates: Requirements 3.4**

  - [x] 2.4 Write property tests for JWT issuance (Property 1)
    - **Property 1: JWT Issuance Correctness**
    - Test that for any valid (username, role) pair, the issued token decodes to contain correct `sub`, `role`, and `exp` exactly 60 minutes from issuance
    - Use Hypothesis to generate valid usernames and roles
    - **Validates: Requirements 1.1, 1.5**

  - [x] 2.5 Write property test for password hashing strength (Property 2)
    - **Property 2: Password Hashing Strength**
    - Test that for any password string, the resulting hash is a valid bcrypt hash with work factor ≥ 12
    - **Validates: Requirements 1.3**

- [x] 3. Implement auth middleware
  - [x] 3.1 Create auth middleware for JWT validation and blacklist check
    - Create `backend/api/middleware/auth_middleware.py` with a FastAPI dependency function `get_current_user(token)` that:
      - Extracts the Bearer token from the Authorization header
      - Decodes and validates the JWT (checks expiry)
      - Checks `jti` against the `token_blacklist` table — rejects with 401 if blacklisted
      - Returns a dict with `username`, `role`, `first_time` claims
      - Returns 401 if token is missing, invalid, or expired
    - _Requirements: 2.2, 5.6_

  - [x] 3.2 Write property test for blacklisted token rejection (Property 5)
    - **Property 5: Blacklisted Token Rejection**
    - Test that for any token whose `jti` is in the blacklist, the middleware rejects with 401
    - **Validates: Requirements 2.2**

- [x] 4. Implement RBAC middleware
  - [x] 4.1 Create RBAC dependency for role-based permission enforcement
    - Create `backend/api/middleware/rbac.py` with:
      - A `require_role(*allowed_roles)` dependency factory that returns 403 if user's role is not in allowed_roles
      - A `require_not_first_time()` dependency that returns 403 if `first_time` is true (blocks access to all endpoints except password-change)
      - Permission mapping: Admin → all endpoints; L1_User → KB read endpoints only
    - _Requirements: 4.3, 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 4.2 Write property test for RBAC permission matrix (Property 8)
    - **Property 8: RBAC Permission Matrix**
    - Test all combinations of role × endpoint × first_time_flag and verify correct allow/deny behavior
    - Use Hypothesis to generate role/endpoint/flag combinations
    - **Validates: Requirements 4.3, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.4**

- [x] 5. Checkpoint - Core security layer
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement authentication routes
  - [x] 6.1 Create auth router with login and logout endpoints
    - Create `backend/api/routes/auth.py` with:
      - `POST /api/auth/login`: validate credentials, check rate limiter, check first_time_flag, issue JWT, return LoginResponse
      - `POST /api/auth/logout`: add token `jti` to blacklist, return success message
    - Register router in `backend/api/main.py`
    - _Requirements: 1.1, 1.2, 1.4, 1.5, 2.1_

  - [x] 6.2 Add password reset and first-time change endpoints
    - Add to `backend/api/routes/auth.py`:
      - `POST /api/auth/reset-request`: generate reset token with 30-min expiry, store in reset_tokens table, return token
      - `POST /api/auth/reset`: validate reset token (not expired, not used), validate new password policy, update password hash, mark token as used
      - `POST /api/auth/change-password`: for first-time users, validate current password, validate new password policy, update hash, set first_time_flag=false, issue new JWT
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.1, 4.2_

  - [x] 6.3 Write property test for invalid credentials rejection (Property 3)
    - **Property 3: Invalid Credentials Rejection**
    - Test that for any username/password pair where credentials don't match, the login endpoint returns 401
    - **Validates: Requirements 1.2**

  - [x] 6.4 Write property test for rate limiter threshold (Property 4)
    - **Property 4: Rate Limiter Threshold Enforcement**
    - Test that after 5 failed attempts within 15 minutes, all subsequent attempts are rejected with 429
    - **Validates: Requirements 1.4**

  - [x] 6.5 Write property test for reset token single-use (Property 6)
    - **Property 6: Reset Token Single-Use Invariant**
    - Test that once a reset token is used or expired, subsequent uses return 400
    - **Validates: Requirements 3.2, 3.3**

- [x] 7. Implement user management routes
  - [x] 7.1 Create user management router (Admin only)
    - Create `backend/api/routes/users.py` with:
      - `POST /api/users`: create user with username, hashed temporary password, role, first_time_flag=true; return 409 if username exists; validate role is Admin or L1_User
      - `GET /api/users`: list all users with username, role, created_at
    - Protect both endpoints with `require_role('Admin')` and `require_not_first_time()` dependencies
    - Register router in `backend/api/main.py`
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 7.2 Write property test for first-time flag invariant (Property 9)
    - **Property 9: New User First-Time Flag Invariant**
    - Test that every user created via the API has first_time_flag=true
    - **Validates: Requirements 6.1**

  - [x] 7.3 Write property test for username uniqueness (Property 10)
    - **Property 10: Username Uniqueness Enforcement**
    - Test that creating a user with a duplicate username returns 409 and existing record is unchanged
    - **Validates: Requirements 6.2**

- [x] 8. Implement KB document routes
  - [x] 8.1 Create KB document router
    - Create `backend/api/routes/kb.py` with:
      - `POST /api/kb/documents` (Admin only): accept file upload with title, validate file type (PDF, DOCX, plain text) and size (≤10 MB), store file to `uploads/kb/`, save metadata to db, return document ID
      - `GET /api/kb/documents` (Authenticated): list all documents with title, upload date, uploader name
      - `GET /api/kb/documents/{id}` (Authenticated): return file as download; 404 if not found
    - Protect upload with `require_role('Admin')`; protect reads with auth middleware only
    - Register router in `backend/api/main.py`
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 8.1, 8.2, 8.3_

  - [x] 8.2 Write property test for KB file type and size validation (Property 13)
    - **Property 13: KB File Type and Size Validation**
    - Test that files are accepted if and only if content type is in {PDF, DOCX, plain text} AND size ≤ 10 MB
    - **Validates: Requirements 7.2, 7.3**

  - [x] 8.3 Write property test for non-existent resource 404 (Property 14)
    - **Property 14: Non-Existent Resource Returns 404**
    - Test that any non-existent document ID returns 404
    - **Validates: Requirements 8.3**

  - [x] 8.4 Write property test for KB upload round-trip (Property 11)
    - **Property 11: KB Document Upload Round-Trip**
    - Test that uploaded documents can be retrieved with identical content and correct metadata
    - **Validates: Requirements 7.1, 7.4, 8.2**

  - [x] 8.5 Write property test for KB document list completeness (Property 12)
    - **Property 12: KB Document List Completeness**
    - Test that the list endpoint returns exactly the set of uploaded documents with correct metadata
    - **Validates: Requirements 6.3, 8.1**

- [x] 9. Checkpoint - Backend API complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Seed admin user and integrate with existing routes
  - [x] 10.1 Create seed admin user on database initialization
    - In `backend/database.py`, after table creation, insert a default admin user (username: `admin`, password: `Admin@1234`, role: `Admin`, first_time_flag: true) if no users exist
    - This enables first-time bootstrapping of the system
    - _Requirements: 6.1, 4.1_

  - [x] 10.2 Protect existing API routes with auth and RBAC middleware
    - Update `backend/api/routes/query.py` to require authentication and `Admin` role
    - Update `backend/api/routes/recommendations.py` to require authentication
    - Update `backend/api/routes/costs.py` to require authentication and `Admin` role
    - Update `backend/api/routes/status.py` to require authentication
    - Add the auth middleware and RBAC dependencies to existing route handlers
    - _Requirements: 5.2, 5.5, 5.6_

  - [x] 10.3 Add token blacklist cleanup background task
    - In `backend/api/main.py`, add an `on_startup` event that launches a background task to purge expired entries from `token_blacklist` every 30 minutes
    - Call `database.init_db()` on startup to ensure tables exist
    - _Requirements: 2.1_

- [x] 11. Implement frontend login page
  - [x] 11.1 Create login page HTML and styles
    - Create `frontend/aiops/login.html` with:
      - Centered login form with username field, password field, and submit button
      - Platform name "Multi-Cloud AIOps Platform" heading above form
      - Dark navy (#1e293b) background, white (#ffffff) card, teal-blue (#0ea5e9) accent
      - Responsive layout working from 320px to 1920px
      - Inline validation error messages below input fields
      - First-time password change form (hidden until needed)
    - Update `frontend/aiops/styles.css` with the new color palette and login page styles
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 11.2 Create frontend auth module
    - Create `frontend/aiops/auth.js` with:
      - `login(username, password)` function calling POST /api/auth/login
      - `logout()` function calling POST /api/auth/logout and clearing stored token
      - `getToken()` / `setToken()` for localStorage token management
      - `isAuthenticated()` check (token exists and not expired client-side)
      - `getUserRole()` extracting role from stored token/response
      - Auto-redirect to login page if token is missing or expired
      - Handle `requires_password_change` response by showing password change form
    - _Requirements: 1.1, 2.1, 4.1, 4.2_

- [x] 12. Implement frontend dashboard
  - [x] 12.1 Create ops dashboard HTML with sidebar layout
    - Create `frontend/aiops/dashboard.html` with:
      - Sidebar navigation on the left, main content area on the right
      - Dark navy sidebar, white content cards, teal-blue accent color
      - User info display (username + role) in sidebar header
      - Logout button in sidebar
      - Responsive: sidebar collapses to hamburger menu below 768px viewport width
      - Content sections: Query (Admin), KB Upload (Admin), KB Articles (all), User Management (Admin)
    - _Requirements: 10.1, 10.2, 10.4, 10.5, 10.6_

  - [x] 12.2 Create dashboard JavaScript for role-based navigation and section loading
    - Create `frontend/aiops/dashboard.js` with:
      - On load: check auth state, redirect to login if unauthenticated
      - Render sidebar nav items based on user role (Admin: Query, KB Upload, KB Articles, User Management; L1_User: KB Articles only)
      - Section switching logic (show/hide content panels)
      - KB Articles section: fetch and display document list, allow download
      - KB Upload section (Admin): file upload form with title field
      - User Management section (Admin): create user form, user list display
      - Query section (Admin): integrate with existing query endpoint
      - Hamburger menu toggle for mobile responsive sidebar
    - _Requirements: 10.3, 10.4, 10.5, 10.6_

- [x] 13. Final checkpoint - Full integration
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (Properties 1-14)
- Unit tests validate specific examples and edge cases
- The backend uses Python (FastAPI) with async SQLite; the frontend uses vanilla HTML/CSS/JS
- All new routes follow the existing project pattern: router registration in `main.py`, envelope responses
- The seed admin user (username: `admin`) has `first_time_flag=true`, forcing a password change on first login

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "2.5"] },
    { "id": 3, "tasks": ["3.1", "4.1"] },
    { "id": 4, "tasks": ["3.2", "4.2"] },
    { "id": 5, "tasks": ["6.1", "7.1", "8.1"] },
    { "id": 6, "tasks": ["6.2", "6.3", "6.4", "7.2", "7.3", "8.2", "8.3", "8.4", "8.5"] },
    { "id": 7, "tasks": ["6.5", "10.1", "10.2", "10.3"] },
    { "id": 8, "tasks": ["11.1", "11.2"] },
    { "id": 9, "tasks": ["12.1", "12.2"] }
  ]
}
```
