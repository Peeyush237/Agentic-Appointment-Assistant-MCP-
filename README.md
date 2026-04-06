# Full-Stack Developer Intern Assignment - Agentic AI with MCP

This project is a minimal full-stack implementation of:
- FastAPI backend
- MCP server exposing tools/resources/prompts
- MCP client that dynamically discovers tools at runtime
- LLM-driven orchestration using tool-calling
- React frontend for patient and doctor flows
- PostgreSQL-backed appointments and doctor schedules

## Why this satisfies MCP expectations

1. Tool execution is routed through MCP client-server protocol
- The agent never calls tool functions directly.
- Agent uses `MCPClient` over HTTP JSON-RPC to call `tools/list`, `tools/call`, `prompts/get`.

2. Tools are dynamically discovered at runtime
- `app/core/agent.py` calls MCP `tools/list` on each request and converts schemas to LLM tool definitions.
- No hardcoded tool schema in orchestration logic.

3. Workflow orchestration is LLM-driven
- LLM decides when/which tools to call.
- Backend does not use if/else flow to choose booking/reporting tool sequence.

4. Separation of concerns
- Client: `app/mcp/client.py`
- Server: `app/mcp/server.py`
- Tools: MCP handlers in server
- Prompts: MCP prompt registry (`prompts/list`, `prompts/get`)
- Resources: MCP resources (`resources/list`, `resources/read`)

## Project structure

- `backend/app/main.py` - FastAPI app bootstrap
- `backend/app/api/routes.py` - REST endpoints consumed by frontend
- `backend/app/core/agent.py` - LLM orchestration loop
- `backend/app/mcp/server.py` - MCP server protocol + tools/prompts/resources
- `backend/app/mcp/client.py` - MCP protocol client
- `backend/app/db/models.py` - PostgreSQL models
- `frontend/src/App.jsx` - role switch and UI shell
- `frontend/src/components/ChatPanel.jsx` - multi-turn chat and tool trace

## Features mapped to assignment scenarios

### Clinic schedule rules (enforced by MCP tools)
- Working days: Monday to Friday
- Working hours: 9:00 AM-1:00 PM and 2:00 PM-6:00 PM
- Lunch break: 1:00 PM-2:00 PM
- Slot duration: 30 minutes

### Scenario 1: Patient appointment scheduling
- Patient asks in natural language.
- LLM calls MCP tool `check_doctor_availability`.
- LLM calls MCP tool `book_appointment`.
- Booking tool creates Google Calendar event (mock/live depending on token).
- LLM then calls MCP tool `send_patient_email`.
- Frontend shows response and tool trace.

### Conversation continuity
- Session continuity is maintained by `session_id` and per-session chat history in `AgentOrchestrator`.
- Second user message can refer to previous turn context (e.g., “book 3 PM slot”).

### Scenario 2: Doctor summary report
- Doctor asks natural language query (today/tomorrow/yesterday/fever).
- LLM calls MCP tool `get_doctor_report_stats`.
- LLM summarizes and calls MCP tool `send_doctor_notification` (WhatsApp via Twilio or mock fallback).
- Same report flow can be triggered from chat or quick button helper in frontend.

## Setup

## 1) PostgreSQL
Create database:
- DB name: `appointment_mcp`
- User/password: update as needed in env

Quick start with Docker:
```bash
docker compose up -d
```

## 2) Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Update `backend/.env`:
- `DATABASE_URL`
- `OPENAI_API_KEY`
- Google Calendar (recommended): `GOOGLE_REFRESH_TOKEN`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (optional fallback: `GOOGLE_ACCESS_TOKEN`)
- for live patient email via SendGrid: `EMAIL_PROVIDER=sendgrid`, `EMAIL_FROM`, `EMAIL_API_KEY`
- for live doctor notifications: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`, `DOCTOR_WHATSAPP_TO`

Run backend:
```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## 3) Frontend
```bash
cd frontend
npm install
npm run dev
```

Open:
- Frontend: `http://localhost:5173`
- Backend health: `http://127.0.0.1:8000/api/health`

## Sample prompts

Patient mode:
- "I want to check Dr. Ahuja's availability for Friday afternoon"
- "Please book the 3 PM slot"
- "Book Dr. Ahuja tomorrow morning, my email is me@example.com"

Doctor mode:
- "How many patients visited yesterday for Dr. Ahuja?"
- "How many appointments do I have today and tomorrow for Dr. Ahuja?"
- "How many patients with fever visited yesterday for Dr. Ahuja?"

## API summary

- `POST /api/chat`
  - body: `{ role: "patient" | "doctor", message: string, session_id?: string }`
  - returns: `{ session_id, response, tool_trace }`

- MCP endpoint:
  - `POST /mcp` JSON-RPC methods:
    - `tools/list`, `tools/call`
    - `resources/list`, `resources/read`
    - `prompts/list`, `prompts/get`

## Optional integrations

- Google Calendar: provide `GOOGLE_CALENDAR_ID` and either:
  - recommended refresh flow: `GOOGLE_REFRESH_TOKEN`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
  - fallback static token: `GOOGLE_ACCESS_TOKEN`
- Email provider (SendGrid): set `EMAIL_PROVIDER=sendgrid`, `EMAIL_FROM` (verified sender), and `EMAIL_API_KEY`
- Doctor notification (WhatsApp): set Twilio credentials for live notifications

### SendGrid quick setup

1. Create SendGrid account and verify a sender identity.
2. Create an API key with Mail Send permission.
3. Set values in `backend/.env`:
  - `EMAIL_PROVIDER=sendgrid`
  - `EMAIL_FROM=<verified_sender_email>`
  - `EMAIL_API_KEY=<your_sendgrid_key>`
4. Restart backend.

### Twilio WhatsApp quick setup

1. Create a Twilio account and open WhatsApp Sandbox.
2. Join sandbox from your phone by sending the join code provided by Twilio.
3. Set values in `backend/.env`:
  - `TWILIO_ACCOUNT_SID`
  - `TWILIO_AUTH_TOKEN`
  - `TWILIO_WHATSAPP_FROM` (usually `whatsapp:+14155238886` in sandbox)
  - `DOCTOR_WHATSAPP_TO` (example: `whatsapp:+91XXXXXXXXXX`)
4. Restart backend.

## What to demo/screenshots

1. Patient booking flow
- prompt input
- tool trace with availability -> booking -> email
- success response

2. Doctor reporting flow
- report prompt
- tool trace with stats -> notification
- WhatsApp message (or mock response)

