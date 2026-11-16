---
title: CallMe Backend API
emoji: 📞
colorFrom: blue
colorTo: indigo
sdk: gradio
app_file: app.py
pinned: false
---

# AI Receptionist Platform

A modular, multi-tenant AI Receptionist platform designed to handle inbound business customer phone calls. Every business shares a unified LangGraph conversation workflow while maintaining tenant-specific business configurations, knowledge bases, and enabled tools.

---

## 🏛️ Architecture Overview

The platform is designed with clean modular boundaries:

```text
callme/
├── agent/            # High-level entry point re-exporting the conversation workflow
├── backend/          # FastAPI backend services, routing & configuration
│   ├── agent/        # Shared LangGraph conversation workflow (StateGraph & nodes)
│   │   ├── state.py  # AgentState TypedDict schema
│   │   ├── nodes.py  # Prepare Context, Generate Response, Finalize Response
│   │   └── graph.py  # StateGraph builder and workflow invocation
│   ├── config.py     # Pydantic-based safe environment configuration
│   ├── main.py       # FastAPI application entry point with /health
│   ├── services/     # Groq LLM integration services (groq_service.py)
│   └── tools/        # Modular tool registry, definitions, and domain handlers
│       ├── base.py   # ToolDefinition & ToolExecutionResult schemas
│       ├── definitions.py # Pydantic v2 input validation models
│       ├── registry.py    # ToolRegistry & execution boundary
│       └── implementations/ # Domain handlers (information, dining, healthcare, communication)
├── database/         # Data persistence layer (Supabase PostgreSQL)
├── tools/            # Re-exports backend tools for clean root access
├── ui/               # Streamlit dashboard pages, components & state helpers
│   ├── pages/        # Modular page views (Dashboard, Setup, Tools, Chat, History)
│   ├── components.py # Reusable layout components and metric cards
│   ├── mock_data.py  # Seed tenant profiles, tool catalogues & call logs
│   └── state.py      # Multi-tenant session state management
├── voice/            # Telephony (Twilio/WebRTC) and audio streaming
├── tests/            # Automated test suite (pytest: agent, groq, ui, health)
├── app.py            # Streamlit interactive UI prototype
├── requirements.txt  # Project dependencies
├── .env.example      # Environment variable template
├── .gitignore        # Git ignore rules for secrets and build artifacts
├── DECISIONS.md      # Architecture Decision Records (ADRs) & feature roadmap
├── CODEBASE_INDEX.md # File index, symbol catalog & component registry
└── README.md         # Project documentation
```

---

## 🚀 Getting Started

### 1. Prerequisites

- Python 3.10+ installed
- Git

### 2. Set Up Virtual Environment

#### On Windows (PowerShell):
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1
```

*(If PowerShell script execution is restricted, run: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process` or use CMD: `.\.venv\Scripts\activate.bat`)*

#### On macOS / Linux:
```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Copy the template file `.env.example` to `.env`:

#### On Windows (PowerShell):
```powershell
Copy-Item .env.example .env
```

#### On macOS / Linux:
```bash
cp .env.example .env
```

Open `.env` and fill in your credentials:

- `GROQ_API_KEY`: Obtain a free API key at [console.groq.com/keys](https://console.groq.com/keys) and paste it into `.env`.
- `GROQ_MODEL`: Defaults to `openai/gpt-oss-20b` (or other Groq-supported models like `llama-3.3-70b-versatile`).
- `DATABASE_URL`: Add your Supabase PostgreSQL connection string:
  `postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres`

*Real secrets must never be committed to source control.*

---

## 🗄️ Database Setup, Migrations & Seeding (Supabase PostgreSQL)

The platform uses SQLAlchemy 2.0 and Alembic to manage multi-tenant persistence.

### 1. Apply Database Migrations

Run Alembic to create all relational tables, foreign keys, unique constraints, and performance indexes on your Supabase database:

```bash
alembic upgrade head
```

### 2. Seed Initial Sample Tenants (Idempotent)

Seed the two default business tenants (`biz_spice_garden` and `biz_apex_dental`) along with their business FAQs, canonical tool configurations, and sample call audit logs:

```bash
python -m backend.database.seed
```

*(Note: The seeder is strictly idempotent. Running it multiple times creates zero duplicate rows and never overwrites existing user profile modifications.)*

---

## 🏃 Running the Application

### Start the FastAPI Backend

Run Uvicorn from the project root:

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

- API Base URL: `http://localhost:8000`
- Interactive API Docs (Swagger): `http://localhost:8000/docs`
- Health Endpoint: `http://localhost:8000/health`

### Start the Streamlit Dashboard & AI Playground

In a new terminal window (with the virtual environment activated):

```bash
streamlit run app.py
```

The Streamlit UI will open at `http://localhost:8501`. Navigate to the **💬 Agent Playground** in the sidebar to chat with the business receptionists.

---

## 🌐 FastAPI REST API Reference

The platform provides 12 REST API endpoints mounted under `/api` alongside `/health`:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | System status and database connectivity (without credential leaks) |
| `GET` | `/api/businesses` | List all registered business tenants |
| `GET` | `/api/businesses/{business_id}` | Retrieve full configuration profile and FAQs for a tenant |
| `PUT` | `/api/businesses/{business_id}` | Atomically update permitted business profile fields |
| `GET` | `/api/businesses/{business_id}/faqs` | List configured knowledge base FAQs |
| `PUT` | `/api/businesses/{business_id}/faqs` | Replace/update FAQs for a tenant |
| `GET` | `/api/businesses/{business_id}/tools` | List canonical tools and tenant activation statuses |
| `PUT` | `/api/businesses/{business_id}/tools` | Update enabled/disabled tool statuses (validated against canonical registry) |
| `GET` | `/api/businesses/{business_id}/calls` | Retrieve audited call history with pagination & outcome filter |
| `POST` | `/api/businesses/{business_id}/playground/messages` | Submit caller message; runs LangGraph workflow with tool calling |
| `POST` | `/api/businesses/{business_id}/pending-actions/{action_id}/confirm` | Phase B human confirmation; enforces business scoping and replay defense |
| `POST` | `/api/businesses/{business_id}/pending-actions/{action_id}/cancel` | Explicitly reject or cancel a pending action |

---

## 🔄 Shared LangGraph Conversation Workflow & Autonomous Tool Loop

Every business on the platform shares a unified conversation workflow graph compiled with LangGraph:

```text
[START]
   ↓
[Prepare Context]     # Resolves tenant-enabled tools from ToolRegistry & builds prompt
   ↓
[Call LLM]            # Calls Groq with conversation history + enabled tool schemas
   ↓
(Tool Calls Proposed?)
 ├─► YES: [Execute Tools]  # Authorizes, validates arguments via Pydantic;
 │             │           # Intercepts confirmation-required tools (pending_action);
 │             │           # Executes permitted mock tools & appends results.
 │             ↓
 │       (Pending Action Created?)
 │        ├─► YES ──────────────┐
 │        └─► NO  ─► [Call LLM] │ (loops back, bounded to max 5 iterations)
 └─► NO  ───────────────────────┼──────────┐
                                ↓          ↓
                      [Finalize Response]
                                ↓
                              [END]
```

### 🛡️ Two-Phase Human-in-the-Loop Confirmation Boundary

For state-modifying actions (`create_table_booking`, `create_appointment`), the platform strictly enforces a two-phase authorization boundary:
1. **Phase A (Interception)**: The graph intercepts the tool call, generates a pending action record with a UUID `action_id`, and halts tool execution. A clear summary prompt is returned to the user.
2. **Phase B (Human Confirmation)**: The Streamlit Agent Playground displays an interactive confirmation card with action details and explicit buttons ("✅ Confirm Action" or "❌ Cancel / Reject"). Execution is committed via `execute_pending_action()` only when the human clicks Confirm. Chat text alone cannot authorize sensitive operations.

---

## 🧰 Modular Business Tool Registry

The platform features a validated, multi-tenant tool registry ([`backend/tools/`](file:///d:/callme/backend/tools/)) enforcing Pydantic v2 input validation, tenant authorization, and a two-phase confirmation boundary for sensitive actions:

| Tool ID | Category | Current Handler Mode | Future Phase Integration | Requires Confirmation |
| :--- | :--- | :--- | :--- | :--- |
| `answer_faq` | Information | **Mock** (Matches against configured FAQs) | Vector search / RAG | No |
| `check_table_availability` | Dining | **Mock** (Checks operating hours & party limits) | OpenTable / Resy / POS API | No |
| `create_table_booking` | Dining | **Mock** (Generates simulated reference `TB-...`) | POS / Table Reservation API | **Yes** |
| `check_appointment_availability` | Healthcare | **Mock** (Checks clinic schedule & slot inventory) | EHR / Practice Calendar API | No |
| `create_appointment` | Healthcare | **Mock** (Generates simulated reference `APT-...`) | Clinical Booking API | **Yes** |
| `take_message` | Communication | **Mock** (Generates structured log `MSG-...`) | SMS / WhatsApp / Email Dispatch | No |
| `transfer_call` | Communication | **Mock** (Generates escalation ticket `XFER-...`) | Twilio / WebRTC Live Line Transfer | No |

---

## 🎙️ Voice & Telephony Architecture (Step 9A)

The platform provides a provider-independent voice and telephony foundation (`backend/voice/`) that connects inbound phone calls to the shared LangGraph conversation workflow without hardcoded vendor dependencies:

- **Clean Provider Abstractions**: `TelephonyProvider`, `SpeechToTextProvider`, `TextToSpeechProvider`, and `VoiceSessionManager` protocols.
- **Inbound Routing & Anti-Spoofing (`InboundCallRouter`)**:
  - Resolves business tenant by E.164-normalized dialled phone number.
  - Rejects unknown numbers (404), inactive numbers (400), and ambiguous numbers shared across multiple tenants (409).
  - Webhook verification: cross-checks claimed `business_id` against dialled number owner to prevent spoofing (403).
- **Concurrency Serialization & Turn Orchestration (`VoiceTurnOrchestrator`)**:
  - In-process session locking serializes concurrent speech turns per session.
  - Scopes conversation history to the specific phone call (`session_id`).
  - Preserves the two-phase confirmation boundary for sensitive actions (`create_table_booking`, `create_appointment`).
- **Privacy Masking**:
  - All logs, string representations, and `CallRecord` entries mask caller and called phone numbers (e.g., `+9180***5678`), protecting caller privacy.

### Voice REST & Simulation Endpoints

All voice endpoints are exposed under `/api/voice` (with `/api/v1/voice` alias):

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/voice/capabilities` | Returns active provider capabilities, feature flags, and supported audio codecs (`mulaw`, `pcm`, `mp3`, `audio/x-raw`). |
| `POST` | `/api/voice/simulation/inbound` | Simulates an inbound phone call, resolves tenant from dialled number, validates status, and returns greeting. |
| `POST` | `/api/voice/simulation/sessions/{id}/turns` | Simulates a customer speech turn, invokes the LangGraph receptionist, and returns assistant reply. |
| `POST` | `/api/voice/simulation/sessions/{id}/terminate` | Idempotently terminates an active call and creates a persistent `CallRecord` audit log. |
| `GET` | `/api/voice/sessions/{id}` | Retrieves session metadata, status, duration, and full conversation history. |
| `POST` | `/api/voice/webhook/{provider_name}` | Inbound webhook receiver for telephony providers with HMAC-SHA256 signature verification. |
| `POST` | `/api/voice/exotel/passthru` | Exotel Passthru applet webhook verifying `X-Exotel-Signature` and returning stream parameters. |
| `WSS` | `/api/voice/exotel/ws` | Bidirectional Exotel AgentStream WebSocket endpoint (`wss://.../api/voice/exotel/ws` or `/ws/voice/exotel`). |

---

## 📞 Exotel AgentStream Integration (Step 9B)

The platform supports live inbound telephony via **Exotel AgentStream** over secure bidirectional WebSockets (`WSS`):

### 1. Inbound Call Flow Setup (Exotel App Bazaar)
1. **Assign Virtual Number**: In the Exotel Dashboard, acquire or configure an Exophone (virtual phone number, e.g., `+91 80 4123 5678`).
2. **Build Call Flow**: Create an Exotel Call Flow and attach it to your assigned Exophone.
3. **Voicebot Applet**: Drag a **Voicebot Applet** onto the canvas:
   - **Stream URL**: Set to `wss://<API_KEY>:<API_TOKEN>@your-server.com/api/voice/exotel/ws?sample-rate=8000`
   - **Stream Type**: Set to `bidirectional`.
   - **Audio Format**: Raw Linear PCM 16-bit mono little-endian (`audio/x-raw`, 8000 Hz).
4. **Passthru Applet (Optional Pre/Post Routing)**: Connect a Passthru applet before or after the Voicebot applet pointing to `https://your-server.com/api/voice/exotel/passthru` to log call analytics or retrieve dynamic parameters.

### 2. Audio Format & Chunking Constraints
- **Encoding**: 16-bit Linear PCM mono little-endian (`audio/x-raw`, `audio/x-l16`, `linear16`).
- **Sample Rates**: 8000 Hz (default PSTN), 16000 Hz, or 24000 Hz.
- **Chunk Sizing**: Multiples of 320 bytes (e.g. 320, 640, 1600, 3200 bytes). Minimum 3.2 KB, maximum 100 KB.
- **Barge-in Support**: Send `{"event": "clear", "stream_sid": "..."}` to flush Exotel's playback buffer when a user interrupts the bot.

---

## 🎙️ Deepgram Real-Time STT/TTS & Barge-In Integration (Step 9C)

The platform integrates **Deepgram** streaming speech APIs to power real-time conversational voice over Exotel AgentStream:

### 1. Speech Pipeline Architecture
```text
Exotel Inbound Audio (Linear PCM, 8000 Hz)
    │
    ▼
Audio Validation & Resampling (backend/voice/audio.py)
    │
    ▼
Deepgram Streaming STT (wss://api.deepgram.com/v1/listen)
    │   ├─ Interim Hypotheses (is_final=False)  ──►  Barge-in: clear Exotel buffer
    │   └─ Finalized Utterances (speech_final)  ──►  VoiceTurnOrchestrator
    ▼
Shared LangGraph Conversation Workflow (Groq LLM + Tool Registry)
    │
    ▼
Deepgram Streaming TTS (wss://api.deepgram.com/v1/speak)
    │
    ▼
PCM Alignment (multiples of 320 bytes) & Base64 Framing
    │
    ▼
Exotel Outbound Media Frames (media + mark)
```

### 2. Conversational Barge-In
- When the AI receptionist is speaking, any new caller speech detected by Deepgram streaming STT immediately:
  1. Sets an internal cancellation token to halt the active TTS synthesis task.
  2. Sends an Exotel `{"event": "clear", "stream_sid": "..."}` frame to purge telecom hardware playback buffers on the carrier side.
  3. Seamlessly processes the caller's new utterance through the LangGraph receptionist.

### 3. Audio Format Constraints
- **Encoding**: 16-bit Linear PCM mono little-endian (`linear16` / `audio/x-raw`).
- **Sample Rates**: 8000 Hz (PSTN standard) or 16000 Hz (wideband).
- **Chunk Framing**: Automatically padded and framed into exact multiples of 320 bytes (20 ms at 8000 Hz) to strictly satisfy Exotel AgentStream boundary rules.

### 4. Verification & Smoke Test
- Run automated mocked provider tests:
  ```bash
  pytest tests/test_deepgram_providers.py tests/test_audit_production_readiness.py -v
  ```
- Run live manual Deepgram smoke test (STT transcription & TTS synthesis):
  ```bash
  python -m backend.voice.smoke_test
  ```
- Run live manual Exotel pre-flight audit (Basic Auth, HMAC signatures, and tenant routing):
  ```bash
  python -m backend.voice.smoke_test_exotel
  ```

---

## 📋 Live-Call Pre-Flight Checklist & Rollback Plan (Step 9D)

Before dialing a real PSTN carrier call into the Exotel AgentStream boundary, verify the following checklist:

### Pre-Flight Checklist
1. **Database Schema Current**: Confirm that `alembic upgrade head` has been executed on the production PostgreSQL database (verified at revision `002_voice_sessions`).
2. **Tenant Phone Number Seeded**: Verify that the virtual Exophone is assigned to an active tenant profile in the database (`Business.phone_number` formatted in E.164, e.g., `+91 80 4123 5678`).
3. **Exotel App Bazaar Flow**:
   - Voicebot Applet configured with stream URL: `wss://<EXOTEL_API_KEY>:<EXOTEL_API_TOKEN>@<public_domain>/api/voice/exotel/ws`
   - Audio format: Linear PCM 16-bit mono little-endian (`audio/x-raw`), 8000 Hz.
   - Stream type: Bidirectional.
4. **Environment Settings (`.env`)**:
   - `DEEPGRAM_API_KEY`: Active Deepgram API token with available credits.
   - `GROQ_API_KEY`: Valid Groq LLM API key.
   - `EXOTEL_ACCOUNT_SID`, `EXOTEL_API_KEY`, `EXOTEL_API_TOKEN`: Active Exotel credentials.
5. **Run Pre-Flight Smoke Tests**:
   - `python -m backend.voice.smoke_test` (passes without error).
   - `python -m backend.voice.smoke_test_exotel` (passes without error).
6. **Single-Worker Execution**: Start Uvicorn with a single worker (`--workers 1`) during the initial live test to ensure session locks remain local to the active process.

### Live Call Rollback Plan
If an unexpected carrier error, carrier audio corruption, or WebSocket disconnect occurs during the live PSTN test:
1. **Immediate Carrier Bypass**: In the Exotel Dashboard -> App Bazaar -> Call Flows, switch the Exophone applet from the **Voicebot Applet** to an IVR menu or direct phone number forward (e.g., forwarding calls to human receptionist).
2. **Inspect Server Logs**: Search for WebSocket disconnect close codes:
   - `1008`: Handshake authentication failure. Re-verify API Key and Token in Exotel Stream URL.
   - `1003`: Incompatible audio codec. Verify Voicebot applet is sending `audio/x-raw` (Linear PCM 8000 Hz).
   - `4004`: Unknown tenant number. Verify dialled Exophone matches `Business.phone_number` in database.
3. **Inspect Session Status**: Check `SELECT * FROM voice_sessions ORDER BY created_at DESC LIMIT 5;` to verify call record creation and error correlation.

---

## 🔑 Required Credentials in `.env` File

Below is the complete reference of all credentials and settings required in your `.env` file:

```ini
# ==============================================================================
# 1. Application & Server Settings
# ==============================================================================
ENVIRONMENT=development
DEBUG=true
HOST=0.0.0.0
PORT=8000
API_BASE_URL=http://localhost:8000

# ==============================================================================
# 2. Groq AI & LLM Inference (Steps 3-8)
# ==============================================================================
# Get a free key at: https://console.groq.com/keys
GROQ_API_KEY=gsk_your_groq_api_key_here
GROQ_MODEL=openai/gpt-oss-20b

# ==============================================================================
# 3. Supabase PostgreSQL Persistence (Step 7)
# ==============================================================================
# Get PostgreSQL connection URI from Supabase project settings -> Database
DATABASE_URL=postgresql://postgres.your_project_ref:your_password@aws-0-ap-south-1.pooler.supabase.com:6543/postgres
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_or_service_key

# ==============================================================================
# 4. Exotel Telephony & AgentStream (Step 9B)
# ==============================================================================
# From Exotel Dashboard -> API Settings
EXOTEL_ACCOUNT_SID=your_exotel_account_sid
EXOTEL_API_KEY=your_exotel_api_key
EXOTEL_API_TOKEN=your_exotel_api_token
EXOTEL_SUBDOMAIN=api.in.exotel.com
# Secret configured in Exotel App Bazaar for Passthru webhook signature checks
EXOTEL_WEBHOOK_SECRET=your_exotel_webhook_secret
# Publicly accessible WSS endpoint mapped in Exotel Voicebot Applet
EXOTEL_STREAM_URL=wss://your-domain.com/api/voice/exotel/ws
EXOTEL_SAMPLE_RATE=8000
EXOTEL_AUDIO_CODEC=audio/x-raw

# ==============================================================================
# 5. Deepgram Speech-to-Text & Text-to-Speech (Step 9C)
# ==============================================================================
# Get a key at: https://console.deepgram.com
DEEPGRAM_API_KEY=your_deepgram_api_key_here
DEEPGRAM_STT_MODEL=nova-2
DEEPGRAM_STT_LANGUAGE=en
DEEPGRAM_STT_ENDPOINTING_MS=300
DEEPGRAM_STT_SAMPLE_RATE=8000
DEEPGRAM_STT_ENCODING=linear16
DEEPGRAM_TTS_MODEL=aura-asteria-en
DEEPGRAM_TTS_VOICE=aura-asteria-en
DEEPGRAM_TTS_SAMPLE_RATE=8000
DEEPGRAM_TTS_ENCODING=linear16
VOICE_INTERTURN_TIMEOUT_SECONDS=30
```

---

## 🧪 Running Tests

Execute the automated test suite with pytest from the project root:

```bash
pytest
```

To run voice tests specifically:

```bash
pytest tests/test_voice_foundation.py tests/test_exotel_adapter.py tests/test_deepgram_providers.py -v
```

---

## 🗺️ Implementation Roadmap

- [x] **Step 1: Project Foundation & Architecture**
- [x] **Step 2: Tenant Configuration & Prototype Dashboard**
- [x] **Step 3: Groq LLM Playground Integration**
- [x] **Step 4: Shared LangGraph Conversation Workflow**
- [x] **Step 5: Modular Business Tool Registry**
- [x] **Step 6: Connected Tool-Calling LangGraph Agent**
- [x] **Step 7: Supabase PostgreSQL Persistence**
- [x] **Step 8: FastAPI REST API Layer & Dashboard Integration**
- [x] **Step 9A: Voice & Telephony Architecture Foundation**
- [x] **Step 9B: Exotel Telephony Adapter & Bidirectional WebSocket Integration**
- [x] **Step 9C: Real-Time STT/TTS & Barge-In Integration**
- [x] **Step 9D: Production Readiness Audit & Pre-Flight Hardening**
- [x] **Step 9E: Provider Compatibility Verification & Final Pre-Call Gate**
- [x] **Step 9F: Controlled First Call Preparation & Diagnostics** (Current)

---

## 🔒 Pre-Flight Inbound Call Gate & Human Operator Test Plan

Before initiating any real live PSTN telephone calls, verify system readiness according to this checklist:

### 1. Pre-Flight Diagnostic Command
Run the non-destructive pre-flight diagnostic runner:
```powershell
python -m backend.voice.preflight
```
To run against a specific tenant business or with optional live API checks:
```powershell
python -m backend.voice.preflight --business biz_spice_garden
python -m backend.voice.preflight --business biz_spice_garden --live
```

### 2. Official Provider Documentation References
- **Exotel AgentStream Protocol**: [Exotel AgentStream WebSocket Protocol](https://developer.exotel.com/docs/agentstream/websocket-protocol) & [Connect Voice AI](https://developer.exotel.com/docs/agentstream/connect-voice-ai)
  - Confirms URI format: `wss://<KEY>:<TOKEN>@domain/path`, parsed into standard HTTP Basic Auth headers (`Authorization: Basic base64(...)`).
  - Confirms JSON events: `connected`, `start`, `media`, `dtmf`, `mark`, `clear`, `stop`.
  - Confirms audio framing: 16-bit Linear PCM mono (`slin`), 8000/16000 Hz, framed in 320-byte chunks.
- **Deepgram Streaming Speech APIs**:
  - **Listen (STT)**: [Deepgram Streaming STT Reference](https://developers.deepgram.com/reference/listen/listen-streaming/) (`wss://api.deepgram.com/v1/listen` with `Authorization: Token <KEY>` in headers, `speech_final=True` turn boundary, and `CloseStream` graceful close).
  - **Speak (TTS)**: [Deepgram Streaming TTS Reference](https://developers.deepgram.com/reference/speak/speak-streaming/) (`wss://api.deepgram.com/v1/speak` with `Authorization: Token <KEY>` in headers, and `Speak`, `Flush`, `Clear` frames).

### 3. Required Production Environment Variables (Names Only)
- `ENVIRONMENT` (set to `production`)
- `GROQ_API_KEY`
- `DATABASE_URL`
- `EXOTEL_ACCOUNT_SID`
- `EXOTEL_API_KEY`
- `EXOTEL_API_TOKEN`
- `EXOTEL_WEBHOOK_SECRET`
- `EXOTEL_STREAM_URL`
- `DEEPGRAM_API_KEY`

### 4. Verification Commands
```powershell
# 1. Run the complete automated test suite (162 passing tests)
.\.venv\Scripts\pytest.exe -v

# 2. Verify Supabase database migration state is at 002_voice_sessions
.\.venv\Scripts\alembic.exe current

# 3. Run pre-flight diagnostic check (zero paid calls)
python -m backend.voice.preflight
```

### 5. Manual Human Operator Test Plan
Execute this sequence strictly after pre-flight diagnostics pass:
1. **Call Test Number**: Dial `+91 80 4123 5678` from an authorized mobile phone.
2. **Verify Greeting**: Confirm the spoken greeting matches: *"Hello, thank you for calling Royal Spice Garden! How can I assist you today?"*
3. **Ask In-Scope FAQ**: Ask *"What are your opening hours on Friday?"* Confirm grounded answer (*"12:00 PM to 11:00 PM"*).
4. **Ask Out-of-Scope Question**: Ask *"Do you offer valet parking for helicopters?"* Confirm agent politely refuses without hallucinating false services.
5. **Test Barge-In**: Start speaking while the assistant is mid-sentence; verify assistant audio ceases immediately.
6. **Test Table Booking**: Request *"I would like to book a table for two tonight at 8 PM."* Confirm assistant details the request and prompts for confirmation, but does NOT finalize or fake booking without human approval.
7. **Verify Session Persistence**: End call. In dashboard or REST API (`GET /api/voice/sessions/{session_id}`), verify call duration, status (`completed`), and turn history.
8. **Test Fallback**: If agent errors or connection drops, confirm Exotel routes to the designated human operator desk phone.

### 6. Acoustic Echo Limitation & Operational Notice
- **Telephony DSP AEC**: True Acoustic Echo Cancellation is handled by carrier-grade PSTN media gateways, mobile baseband DSPs, and handset hardware.
- **Application Mitigation**: The software-level transcript comparison in `handle_exotel_media_stream` suppresses obvious self-playback echo loops but is an interim safety guard, not a replacement for carrier/DSP AEC.

### 7. Rollback Plan
If an in-flight call experiences provider failure:
1. **Immediate Telecom Fallback**: In the Exotel Call Flow dashboard, switch the Virtual Number's fallback applet to standard call forwarding (e.g., human agent desk number).
2. **Database Reversion**: Database migration `002_voice_sessions` is non-breaking. To revert: `alembic downgrade -1`.
3. **Environment Switch**: Set `ENVIRONMENT=development` to re-enable local simulation tools.
