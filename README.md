# Multi-Cloud AIOps Platform

An AI-powered multi-cloud operations platform for managing resources across AWS, Azure, and GCP using natural language queries.

## Features

- **Natural Language Query Bot** — Manage cloud resources via conversational commands
- **Role-Based Access** — Admin and L1_User roles with appropriate permissions
- **Knowledge Base** — Upload and share operational documents
- **Cloud Monitors** — CPU utilization and cost tracking across providers
- **User Management** — Admin can create users with forced first-login password change
- **Secure Auth** — JWT tokens, bcrypt passwords, rate limiting, token blacklist

## Quick Start (Local)

```bash
pip install -r backend/requirements.txt
python -m backend.main
# In another terminal:
python -m http.server 3000 --directory frontend/aiops
```

Visit `http://localhost:3000/login.html`  
Default admin: `admin` / `Admin@1234` (forced password change on first login)

## Docker

```bash
docker build -t aiops-platform .
docker run -p 8000:8000 aiops-platform
```

## Deploy to AWS

1. Push to GitHub
2. SSH into EC2 instance
3. `git clone` + `docker build` + `docker run`

## Tech Stack

- **Backend:** Python, FastAPI, SQLite, JWT (python-jose), bcrypt
- **Frontend:** Vanilla HTML/CSS/JS
- **Cloud SDKs:** boto3 (AWS), azure-mgmt-compute (Azure), google-cloud-compute (GCP)
