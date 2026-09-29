# Mail2WhatsApp

> **Fully Functional Production-Ready Automatic Gmail → WhatsApp Email Forwarding System**  
> Based on Mail2WhatsApp PRD Version 1.0.

---

## 1. Overview

**Mail2WhatsApp** is an event-driven automation platform that connects a Gmail inbox to a WhatsApp destination. Every incoming Gmail email is detected automatically and forwarded to the configured WhatsApp recipient with original email headers, semantic structure, links, and attachments preserved as closely as WhatsApp permits.

### Core Principles
- **No AI Rewriting/Paraphrasing**: Forwards exact email headers (From, To, CC, Subject, Date), body, and attachments without modification.
- **Event-Driven Push**: Uses Gmail `users.watch` + Google Cloud Pub/Sub push notifications (no busy-loop polling).
- **Official Meta Cloud API**: Integrates directly with Meta's official WhatsApp Business Platform / Cloud API (no fragile browser automation or scraping).
- **Deduplication**: Enforces strict database-level unique constraints (`UNIQUE(gmail_message_id)`) to prevent duplicate WhatsApp dispatches even if Pub/Sub retries events.
- **Resilience & Reconciliation**: Implements exponential backoff with jitter for transient errors and automated periodic reconciliation fallback to recover any missed messages.

---

## 2. End-to-End Architecture

```
   ┌──────────────────────────────────────────────┐
   │             Incoming Gmail Message           │
   └──────────────────────┬───────────────────────┘
                          │ Gmail users.watch
                          ▼
   ┌──────────────────────────────────────────────┐
   │           Google Cloud Pub/Sub Topic         │
   └──────────────────────┬───────────────────────┘
                          │ HTTPS Push Webhook
                          ▼
   ┌──────────────────────────────────────────────┐
   │        FastAPI Orchestrator / Webhook        │
   │           (/webhook/google-pubsub)           │
   └───────┬──────────────┬───────────────┬───────┘
           │              │               │
           ▼              ▼               ▼
     ┌───────────┐  ┌───────────┐  ┌─────────────┐
     │ Gmail API │  │ PostgreSQL│  │  WhatsApp   │
     │ History + │  │ Supabase  │  │  Cloud API  │
     │ Messages  │  │ State/Logs│  │ Send & Media│
     └───────────┘  └───────────┘  └─────────────┘
           │              │               │
           ▼              │               ▼
     MIME Parser          │        WhatsApp User
     & Attachments        │               │
                          ▼               ▼
                   Delivery Logs ◄── Webhook Status
```

---

## 3. Directory Structure

```
Mail2WhatsApp/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI application entrypoint & background scheduler
│   ├── config.py                # Pydantic environment configuration & key derivation
│   ├── database.py              # SQLAlchemy engine, session maker & init
│   ├── dependencies.py          # Route dependencies (DB session, Pub/Sub verification)
│   ├── models/                  # SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── gmail_account.py     # Connected Gmail accounts & watch states
│   │   ├── email.py             # Deduplicated email records & state machine
│   │   ├── attachment.py        # Attachment metadata & upload states
│   │   ├── delivery.py          # WhatsApp message IDs & delivery audit logs
│   │   └── sync_run.py          # Reconciliation & sync audit history
│   ├── schemas/                 # Pydantic request/response schemas
│   │   ├── __init__.py
│   │   ├── email.py             # Parsed email & attachment schemas
│   │   ├── webhook.py           # Pub/Sub push & WhatsApp webhook payloads
│   │   ├── auth.py              # OAuth request/response models
│   │   └── health.py            # Health & dependency status models
│   ├── routes/                  # API endpoints
│   │   ├── __init__.py
│   │   ├── auth.py              # Google OAuth 2.0 login & callback
│   │   ├── gmail.py             # Watch renewal, reconciliation, email list
│   │   ├── webhook.py           # Pub/Sub push intake & WhatsApp delivery status
│   │   └── health.py            # /health & /health/ready probes
│   ├── services/                # Business logic services
│   │   ├── __init__.py
│   │   ├── gmail_service.py     # Gmail API v1 client & OAuth management
│   │   ├── pubsub_service.py    # Pub/Sub push payload decoding
│   │   ├── mime_parser.py       # Header decoder, HTML-to-WhatsApp converter, chunker
│   │   ├── attachment_service.py# Attachment downloader, validator & media dispatcher
│   │   ├── whatsapp_service.py  # Meta WhatsApp Cloud API client
│   │   ├── sync_service.py      # Core processing pipeline & reconciliation
│   │   └── retry_service.py     # Exponential backoff schedule & error classifier
│   └── utils/
│       ├── __init__.py
│       ├── logging.py           # Sanitized logger redacting secrets & credentials
│       └── security.py          # Fernet token encryption & webhook verification
├── migrations/                  # Alembic database migrations
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 001_initial_schema.py
├── tests/                       # Automated test suite (pytest)
│   ├── __init__.py
│   ├── conftest.py              # In-memory test DB & test client fixtures
│   ├── test_auth.py             # OAuth & encryption unit tests
│   ├── test_deduplication.py    # Idempotency & unique constraint tests
│   ├── test_health.py           # Healthcheck & readiness tests
│   ├── test_mime_parser.py      # MIME & HTML formatting tests
│   ├── test_pubsub_webhook.py   # Pub/Sub payload & auth tests
│   ├── test_retry_service.py    # Backoff calculation & error classifier tests
│   ├── test_sync_reconciliation.py # End-to-end pipeline & recovery tests
│   └── test_whatsapp_service.py # WhatsApp API & simulation tests
├── credentials/                 # Local credentials folder (never committed)
│   └── .gitkeep
├── .env.example                 # Environment configuration template
├── .gitignore                   # Secrets, DB, and cache exclusions
├── alembic.ini                  # Alembic configuration
├── Dockerfile                   # Production Python 3.12 slim container
├── docker-compose.yml           # Multi-container orchestration (App + PostgreSQL)
├── pytest.ini                   # Pytest configuration
├── requirements.txt             # Pinned production dependencies
└── README.md
```

---

## 4. Setup & Configuration

### Prerequisites
- Python 3.12+
- Google Cloud Project with Gmail API & Cloud Pub/Sub enabled
- Meta Developer Account with WhatsApp Cloud API configured
- PostgreSQL database (or local SQLite for development)

### 1. Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Configure the following variables in `.env`:
```ini
# Application
APP_ENV=production
SECRET_KEY=your-32-byte-secure-random-secret-key
LOG_LEVEL=INFO

# Google OAuth 2.0 (from Google Cloud Console -> Credentials)
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=https://your-domain.example/auth/google/callback

# Gmail / Pub/Sub
GMAIL_PUBSUB_TOPIC=projects/your-gcp-project/topics/gmail-events
GOOGLE_CLOUD_PROJECT=your-gcp-project
PUBSUB_VERIFICATION_TOKEN=optional-secret-token

# Database
DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/mail2whatsapp
# Or for local development:
# DATABASE_URL=sqlite:///./mail2whatsapp.db

# WhatsApp Business Platform / Cloud API
WHATSAPP_ACCESS_TOKEN=your-meta-system-user-access-token
WHATSAPP_PHONE_NUMBER_ID=your-whatsapp-phone-number-id
WHATSAPP_VERIFY_TOKEN=your-custom-webhook-verify-token
WHATSAPP_RECIPIENT_NUMBER=15551234567
WHATSAPP_API_VERSION=v21.0
```

---

## 5. Google Cloud & Meta Setup

### Google Cloud Setup
1. **Enable APIs**: In Google Cloud Console, enable **Gmail API** and **Cloud Pub/Sub API**.
2. **Create Pub/Sub Topic**: Create a topic named `gmail-events`.
3. **Grant Publish Permissions**: Grant `gmail-api-push@system.gserviceaccount.com` the role **Pub/Sub Publisher** on your topic.
4. **Create Push Subscription**:
   - Subscription name: `gmail-events-push`
   - Delivery type: **Push**
   - Endpoint URL: `https://<YOUR_DOMAIN>/webhook/google-pubsub?token=<PUBSUB_VERIFICATION_TOKEN>`
5. **OAuth Consent Screen & Credentials**:
   - Create OAuth 2.0 Client ID (Web Application).
   - Add Authorized redirect URI: `https://<YOUR_DOMAIN>/auth/google/callback`.
   - Required scope: `https://www.googleapis.com/auth/gmail.readonly`.

### Meta WhatsApp Cloud API Setup
1. Register on [Meta for Developers](https://developers.facebook.com/).
2. Create a Meta App with the **WhatsApp** product.
3. Obtain your **Phone Number ID** and generate a permanent **System User Access Token**.
4. In WhatsApp **Configuration** > **Webhook**:
   - Callback URL: `https://<YOUR_DOMAIN>/webhook/whatsapp`
   - Verify Token: Matches `WHATSAPP_VERIFY_TOKEN` in `.env`
   - Webhook Fields: Subscribe to `messages` (for delivery status updates).

---

## 6. Running Locally

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Apply Database Migrations
```bash
alembic upgrade head
```

### Start the Application Server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Interactive API documentation is accessible at `http://localhost:8000/docs`.

### Connect Your Gmail Account
1. Open your browser and navigate to `http://localhost:8000/auth/google/login?redirect=true`.
2. Authorize with your Google account.
3. Google redirects to `/auth/google/callback`. The backend securely encrypts your refresh token, records your account, and registers the Gmail mailbox watch!

---

## 7. Running with Docker & Docker Compose

Launch the complete application with PostgreSQL in Docker:
```bash
docker-compose up --build -d
```
The service will automatically run Alembic migrations on startup and begin listening on port `8080`.

---

## 8. Automated Testing

The project includes an extensive test suite verifying:
- MIME header decoding and HTML-to-WhatsApp formatting
- WhatsApp message chunking (4096 character limit)
- Pub/Sub push notification decoding and security verification
- Deduplication and database unique constraint enforcement
- Exponential backoff calculations and error classification
- End-to-end message sync and reconciliation fallback
- WhatsApp delivery webhook status tracking
- Health and readiness endpoints

Run all tests:
```bash
pytest -v
```

---

## 9. Operational & Recovery Features

### Automated Watch Renewal
Gmail mailbox watches expire in 7 days. The background scheduler checks active accounts every minute and automatically renews watches expiring within 24 hours. You can also trigger renewal manually:
```bash
POST /gmail/watch/renew
```

### Reconciliation Recovery Job
If Pub/Sub events are missed due to network downtime or if a history window expires, the reconciliation job recovers missing messages by scanning recent emails against the database:
```bash
POST /gmail/reconcile
```

### Health & Readiness Probes
- `GET /health`: Comprehensive status of DB connection, WhatsApp API, Pub/Sub, active accounts, and pending retries.
- `GET /health/ready`: Kubernetes and Cloud Run readiness check.

---

## 10. License & Compliance
Built strictly in adherence with Google API Terms of Service, Google User Data Policy (requesting the narrowest scope: `gmail.readonly`), and Meta WhatsApp Business Messaging Policies.
