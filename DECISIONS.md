# Architecture Decisions & Feature Log

This living document records all engineering decisions (ADRs), architectural choices, trade-offs, and feature roadmap tracking for the **AI Receptionist Platform**.

---

## 🏛️ Architecture Decision Records (ADRs)

### ADR-001: Modular Multi-Tenant Separation of Concerns
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: The platform must support multiple business tenants who each have custom business hours, custom tools (appointment booking, pricing, FAQ), and tenant-specific configuration, while maintaining one unified, maintainable core codebase.
- **Decision**: Decouple the platform into clear, isolated layers:
  - `backend/`: FastAPI REST API for dashboard APIs, webhook handling, and business configuration services.
  - `agent/` & `backend/agent/`: Shared LangGraph conversation workflow and state machine parameterized by tenant configuration.
  - `tools/` & `backend/tools/`: Dynamic tool registry mapping enabled tools per business tenant.
  - `database/`: Supabase PostgreSQL data-access layer for tenant profiles, call history, and appointments.
  - `voice/`: Audio capture, transcription, text-to-speech, and telephony integrations.
  - `app.py`: Streamlit prototype frontend for tenant onboarding and management.
- **Consequences**: Enables parallel development of features without cross-layer coupling. Keeps the conversation orchestration engine clean and independent of web framework or database specifics.

---

### ADR-002: Core Technology Stack Selection
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: The platform requires fast LLM inference for conversational voice receptionists, rapid prototyping UI, robust asynchronous API endpoints, and structured graph orchestration.
- **Decision**:
  - **FastAPI + Uvicorn**: High-performance asynchronous API framework with automatic OpenAPI documentation and native Pydantic validation.
  - **Streamlit**: Fast prototyping dashboard UI for tenant configuration without frontend build overhead.
  - **LangGraph**: Stateful multi-actor conversation orchestration, enabling cyclic conversation graphs, state rollbacks, and structured agent flow.
  - **Groq API**: Selected for ultra-low latency inference essential for realistic real-time phone reception.
  - **Pydantic v2 & `pydantic-settings`**: Strict typing, data validation, and fail-fast environment variable management.
  - **Supabase PostgreSQL**: Managed relational database with row-level security for multi-tenancy.
- **Consequences**: Developer productivity is maximized; low-latency conversational response targets can be met.

---

### ADR-003: Environment Variable & Secret Management
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: Sensitive credentials (Groq API keys, Supabase credentials, database URLs) must never be leaked into version control or application logs.
- **Decision**:
  - Use `pydantic-settings` with `.env` reading configured via `SettingsConfigDict(env_file=".env", extra="ignore")`.
  - Provide a safe `.env.example` with blank or placeholder values.
  - Add strict `.gitignore` patterns excluding `.env`, `.env.*`, and `.streamlit/secrets.toml`.
  - Never log raw credential values in stdout or log handlers.
- **Consequences**: Safe credential handling across local development and production deployments.

---

### ADR-004: Automated Testing with Zero External Dependencies
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: Automated test suites in early foundation steps must execute reliably in CI/CD and local environments without requiring active third-party API keys or live databases.
- **Decision**:
  - Use `pytest` paired with Starlette/FastAPI `TestClient` (backed by `httpx`).
  - Keep foundation tests focused on self-contained endpoints (`/health`).
  - Isolate external services with mocks or dependency injection in subsequent steps.
- **Consequences**: Fast, repeatable test runs that pass in any environment without external network calls.

---

### ADR-005: Multi-Tenant State Isolation via Session State & Business IDs
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: The prototype dashboard needs to demonstrate multi-tenant behavior where switching between distinct businesses (e.g., a restaurant and a clinic) displays separate profiles, tools, chat histories, and call records without server-side database persistence yet.
- **Decision**:
  - Store multi-tenant configurations in Streamlit's `st.session_state` indexed by internal identifiers (`biz_spice_garden`, `biz_apex_dental`) rather than display names.
  - Initialize session state once per user session using deep copies of template mock data, preventing mutations from leaking back to initial static fixtures.
  - Separate state management functions (`ui/state.py`) from rendering code (`ui/pages/`), facilitating future replacement with PostgreSQL queries and API calls.
- **Consequences**: Switching tenants preserves edits made to both businesses independently across Streamlit reruns.

---

### ADR-006: Modular Page Layout & Transparent Prototype Simulation
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: The user requested 5 distinct dashboard sections (Dashboard, Business Setup, Tool Library, Agent Playground, Call History) with clear visual disclaimers so users know LLM execution and database persistence arrive in later steps.
- **Decision**:
  - Modularized page rendering into dedicated modules under `ui/pages/` routed through a clean sidebar navigation in `app.py`.
  - Built an interactive conversation simulator in `ui/pages/agent_playground.py` displaying the tenant's greeting prompt and simulated prototype responses that explicitly state that Groq and LangGraph will be connected in Step 3.
  - Displayed mock data banners and tool configuration notices to clearly differentiate between configuration state and backend tool execution.
- **Consequences**: Highly professional SaaS appearance that cleanly sets expectations without misleading users about backend execution status.

---

### ADR-007: Groq LLM Integration & Safe Client Lifecycle
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: The Agent Playground requires real LLM inference using Groq without crashing when unconfigured, without leaking credentials in logs or errors, and allowing dependency injection for fast automated testing.
- **Decision**:
  - Implemented `GroqService` in `backend/services/groq_service.py` with singleton access (`get_groq_service()`).
  - Safe client lifecycle: Reuses the initialized `Groq` client rather than reinstantiating it on every message turn.
  - Fail-safe configuration detection: Distinguishes between actual API keys, empty strings, and placeholder strings (`your_groq_api_key_here`).
  - Standardized `LLMResponse(content, error, success)` wrapper handling `groq.AuthenticationError`, `groq.RateLimitError`, `groq.APIConnectionError`, and `groq.APIStatusError` with customer-safe error descriptions that never leak API keys or internal stack traces.
  - Client injection support (`GroqService(client=mock_client)`) enabling 100% test coverage with zero network dependencies.
- **Consequences**: Fast, robust LLM conversations with graceful fallbacks and honest error reporting.

---

### ADR-008: Grounded System Instruction & Prompt Defense Architecture
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: The receptionist LLM must answer questions strictly based on the active business's configured hours, FAQs, and policies without hallucinating non-existent bookings, menu items, or prices.
- **Decision**:
  - Dynamic prompt construction via `build_business_system_instruction()` assembling: Business Identity, Operating Hours & Timezone, FAQs, Escalation Policy, and Enabled Tools.
  - Strict Operational Boundaries: Explicitly instructs the LLM that action execution (bookings, transfers) is in prototype mode, requiring it to explain that automated booking is being finalized and direct callers to the business phone number.
  - Prompt Injection Defense: Caller dialogue is treated strictly as conversational data, forbidding caller-commanded persona or system rule overrides.
- **Consequences**: Realistic, safe receptionist persona preventing hallucinations and unauthorized action claims.

---

### ADR-009: Shared Parameterized LangGraph Workflow Architecture
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: Conversation orchestration previously resided inside UI event handlers. The platform requires a unified, reusable conversation workflow where all tenants share the exact same graph topology while being dynamically parameterized by business identity, hours, FAQs, and enabled tools.
- **Decision**:
  - Built `backend/agent/` using LangGraph's `StateGraph(AgentState)`.
  - Topology: `START -> Prepare Context -> Generate Response -> Finalize Response -> END`.
    - **Prepare Context Node**: Validates tenant config and messages input; dynamically builds tenant system instruction without trusting user overrides.
    - **Generate Response Node**: Calls `GroqService` with the compiled context; handles authentication, rate-limit, and connection errors gracefully.
    - **Finalize Response Node**: Validates workflow outcome, ensuring errors are represented explicitly rather than fabricated into assistant responses.
  - Separation of Graph Construction from Invocation: `create_receptionist_graph()` builds the compiled graph with optional dependency injection, while `invoke_receptionist_workflow()` handles one-shot execution.
  - Independent of Streamlit: The graph can be called by Streamlit, FastAPI endpoints, or telephony voice runtimes interchangeably.
- **Consequences**: True multi-tenant graph reuse without code duplication or hardcoded per-tenant agents.

---

### ADR-010: Modular Tool Registry & Two-Phase Confirmation Execution Boundary
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: Different businesses require distinct operational capabilities (e.g. dining table reservations vs clinical consultations). The system needs a unified, validated tool registry with strict tenant permissions, Pydantic input models, and two-phase confirmation safeguards before committing sensitive actions.
- **Decision**:
  - Implemented `ToolRegistry` in `backend/tools/registry.py` with canonical definitions (`ToolDefinition`) and schema validation via Pydantic v2 input models (`definitions.py`).
  - Separation of Catalog from Permissions: The registry acts as the global catalog of capabilities; `business_config["enabled_tools"]` strictly gates which tools are permitted for a specific tenant.
  - Trusted Context Propagation: Handlers receive trusted `business_config` from the server boundary, preventing tenant context spoofing from caller-provided input arguments.
  - Two-Phase Confirmation Guard: State-modifying tools (`create_table_booking`, `create_appointment`) require `confirmed=True`. When unconfirmed, the execution boundary returns `ToolExecutionStatus.CONFIRMATION_REQUIRED` and refuses to commit the action.
  - Deterministic Mock Handlers: Availability checks and simulated actions generate structured reference codes (`TB-...`, `APT-...`, `MSG-...`, `XFER-...`) with explicit `[SIMULATED MOCK]` disclaimers.
- **Consequences**: Secure, extensible tool platform with robust tenant boundaries, protecting businesses from unauthorized or accidental actions.

---

### ADR-011: Autonomous LangGraph Tool-Calling Loop & Human-in-the-Loop Confirmation Boundary
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: The receptionist must be able to autonomously invoke enabled business tools (e.g., checking table availability, searching business FAQs, taking messages, or initiating bookings) and formulate natural responses from tool outputs. However, state-modifying tools must never be committed without explicit human confirmation, and LLMs must not be allowed to execute unauthorized or disabled tools.
- **Decision**:
  - **Tool Schema Conversion**: Extended `GroqService` with `convert_tool_definition_to_groq_schema()` converting Pydantic v2 `input_schema.model_json_schema()` directly to Groq function definitions.
  - **Cyclic Tool-Calling Workflow**:
    - Topology: `START -> prepare_context -> call_llm -> (execute_tools -> call_llm loop | finalize_response) -> END`.
    - Loop bounded to a strict maximum of 5 iterations (`iteration_count >= 5`) to prevent infinite recursion and excessive token consumption.
  - **Application Authorization Boundary**:
    - LLM proposals are validated against the tenant's `business_config["enabled_tools"]`. Any unauthorized tool invocation is immediately intercepted and rejected with a permission error tool message without executing the handler.
  - **Human-in-the-Loop Two-Phase Confirmation**:
    - State-modifying tools (`requires_confirmation=True`) trigger an interception in `execute_tools_node`. Rather than executing, a structured `pending_action` payload (UUID `action_id`, arguments, summary, status `pending_confirmation`) is attached to graph state and returned to the caller.
    - The conversation pauses, prompting the customer with an action summary.
    - Phase B execution occurs strictly via `execute_pending_action()` triggered by explicit UI buttons ("Confirm" / "Cancel"), verifying tenant ownership (`business_id`) and preventing double execution (`status="executed"`). LLM assertions of confirmation in text alone never trigger execution.
  - **Streamlit Playground UI Integration**:
    - Extended session state with `get_pending_action`, `set_pending_action`, and `clear_pending_action`.
    - Playground renders a dedicated confirmation card with action argument breakdowns, primary "Confirm & Execute" button, and secondary "Reject / Cancel" button.
- **Consequences**:
  - Safe, predictable autonomous agent workflow.
  - Absolute isolation against tool-calling permission bypasses.
  - Complete multi-tenant isolation preserved across tool calls.

---

### ADR-012: Supabase PostgreSQL Persistence, Clean Repositories, and Idempotent Seeding
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: Prototype state previously lived exclusively inside Streamlit's in-memory session state. The platform requires durable, multi-tenant persistence in PostgreSQL (Supabase) covering business profiles, FAQs, tool configurations, call audit records, conversation histories, and pending action states, while allowing zero-dependency automated unit testing (via SQLite in-memory).
- **Decision**:
  - **ORM & Dialect Compatibility**: Used SQLAlchemy 2.0 with `psycopg2-binary` for Supabase PostgreSQL. Used standard column types (`String`, `Text`, `Integer`, `Boolean`, `DateTime(timezone=True)`, `JSON`) ensuring 100% dialect compatibility across PostgreSQL in production and SQLite in tests.
  - **Connection Pooling & Timeout Controls**: `create_database_engine()` applies `QueuePool(pool_size=5, max_overflow=10, pool_timeout=30, pool_recycle=1800, pool_pre_ping=True)` for PostgreSQL; uses `StaticPool` and `connect_args={"check_same_thread": False}` with `PRAGMA foreign_keys=ON` for SQLite.
  - **Repository & Service Pattern**: Kept all database access strictly outside of Streamlit UI modules and LangGraph agent nodes.
    - Entities: `BusinessRepository`, `FAQRepository`, `ToolConfigRepository`, `CallRepository`, `ConversationRepository`, `PendingActionRepository`.
    - High-level coordinator: `DatabaseService` with transactional `session_scope()`.
  - **Idempotent Seed Utility**: `seed_database()` idempotently populates `biz_spice_garden` and `biz_apex_dental` with complete profiles, FAQs, canonical tool configurations, and sample call records (marked `is_simulated=True`) without duplicating existing rows or overwriting user edits.
  - **Database Migration Framework**: Versioned initial migration using Alembic (`001_initial_schema.py`) defining primary keys, foreign keys with `ondelete='CASCADE'`, unique constraints (`(business_id, tool_id)`), and composite performance indexes (`(business_id, timestamp)`, `(business_id, status)`).
  - **Graceful UI Fallback & Transparency**: When `DATABASE_URL` is configured, `ui/state.py` hydrates and commits all edits to PostgreSQL. When unconfigured, it falls back to in-memory fixtures and displays an informational status badge rather than crashing.
  - **Security Limitation Note**: Multi-tenancy is currently partitioned by `business_id` at the application and repository layer. As user authentication and Supabase RLS are scheduled for future steps, business-ID filtering alone does not yet constitute a production security boundary.
- **Consequences**:
  - Reliable persistence across application restarts.
  - Zero-dependency test execution (73/73 tests pass in CI).
  - Clean boundary for future authentication and telephony steps.

---

### ADR-013: FastAPI REST API Layer and Decoupled Streamlit Client Integration
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: Streamlit UI components previously accessed database repositories and orchestrated LangGraph workflows directly in-process. To prepare the platform for telephony webhooks, external channels, and multi-interface access, all business operations, knowledge base management, tool enablement, call history retrieval, dialogue orchestration, and human confirmation must be exposed through standardized REST API endpoints with the dashboard acting strictly as an HTTP/REST API client.
- **Decision**:
  - **Modular FastAPI Routers**:
    - `GET /health`: Preserved health endpoint with database status (`connected`, `configured`, `dialect`) without credential exposure.
    - `GET /api/businesses`, `GET /api/businesses/{id}`, `PUT /api/businesses/{id}`: Tenant listing, detailed profile retrieval, and atomic profile updates with validation.
    - `GET /api/businesses/{id}/faqs`, `PUT /api/businesses/{id}/faqs`: Knowledge base listing and atomic replacement.
    - `GET /api/businesses/{id}/tools`, `PUT /api/businesses/{id}/tools`: Canonical tool listing and status toggling, validated against canonical `ToolRegistry`.
    - `GET /api/businesses/{id}/calls`: Audited call history with pagination (`limit`, `offset`) and outcome filtering.
    - `POST /api/businesses/{id}/playground/messages`: Caller dialogue endpoint invoking shared LangGraph conversation workflow and persisting turns and pending actions.
    - `POST /api/businesses/{id}/pending-actions/{action_id}/confirm`: Phase B execution committing confirmed tool operations, enforcing business scoping and replay defense (HTTP 400 on duplicate execution).
    - `POST /api/businesses/{id}/pending-actions/{action_id}/cancel`: Explicit action cancellation and status transition.
  - **Decoupled Streamlit Client (`ui/api_client.py`)**:
    - Created reusable `ApiClient` with dedicated exception hierarchy (`ApiClientError`, `ApiConnectionError`, `ApiNotFoundError`).
    - Rewrote `ui/state.py` and `ui/pages/agent_playground.py` to route all operations through `ApiClient`.
    - Maintained graceful offline fallback in UI with clear connection status badges and guidance to start `uvicorn backend.main:app --port 8000`.
  - **Architectural Security Boundary Limitation**:
    - While tenant scoping (`business_id`) and tool execution authorization are strictly enforced at the application and repository layer, user authentication (JWT/OAuth) and Supabase Row Level Security (RLS) are scheduled for subsequent production hardening steps. Tenant IDs currently serve as partition keys, not cryptographically verified identities.
- **Consequences**:
  - Single conversation and tool authorization pipeline shared identically by dashboard playground, future telephony webhooks, and third-party integrations.
  - Complete architectural separation of frontend UI from backend persistence and graph orchestration.
  - 97 automated tests passing across the entire platform.

---

### ADR-014: Provider-Independent Voice Telephony Architecture and Session Isolation Foundation
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: To support telephony channels (e.g., Twilio, WebRTC, SIP trunks) without coupling the platform to vendor-specific APIs or building duplicate agent loops, the platform requires a provider-independent voice foundation. Key requirements include phone-number-to-tenant routing, webhook spoofing prevention, turn concurrency serialization, durable session isolation across simultaneous calls and playground chats, two-phase confirmation preservation, and customer privacy masking.
- **Decision**:
  - **Provider-Independent Protocols (`backend/voice/interfaces.py`)**:
    - Defined clean contracts: `TelephonyProvider` (webhook parsing, cryptographic signature verification, call control), `SpeechToTextProvider` (transcription), `TextToSpeechProvider` (speech synthesis), and `VoiceSessionManager` (lifecycle state machine).
    - Implemented deterministic `MockTelephonyProvider`, `MockSTTProvider`, and `MockTTSProvider` with provider registry (`backend/voice/providers/`) for testing and local simulation without external network dependencies.
  - **Tenant Resolution & Webhook Spoofing Defense (`InboundCallRouter`)**:
    - Tenant identity is resolved strictly from the E.164-normalized `called_number` against trusted database business records (`BusinessRepository.get_by_phone_number`).
    - Unassigned numbers are rejected (HTTP 404).
    - Inactive numbers (status other than "Active & Connected") are rejected (HTTP 400).
    - Ambiguous numbers mapped to multiple tenants are detected and rejected (HTTP 409).
    - External webhook `business_id` claims are verified against the registered owner of the called number; mismatches are rejected (HTTP 403) to prevent cross-tenant spoofing.
  - **Voice Turn Concurrency & Graph Orchestration (`VoiceTurnOrchestrator`)**:
    - Inbound speech turns for a given voice session are serialized using in-process session locks (`_session_locks`) to prevent race conditions and interleaving graph state.
    - Each turn loads isolated session-scoped history (`session_id`) and executes the shared LangGraph receptionist workflow and canonical tool registry without code duplication.
    - Preserves two-phase human confirmation boundaries: sensitive operations yield `pending_action` for explicit confirmation rather than executing immediately over audio.
    - Error boundary catches LLM or tool failures and returns polite fallback speech without hallucinating false bookings.
  - **Durable PostgreSQL Persistence (`002_voice_sessions`)**:
    - Created `voice_sessions` table with indexes on `business_id`, `provider_call_id`, and `status`.
    - Added `session_id` foreign key to `conversation_messages` to partition phone call history from dashboard playground history.
    - Implemented idempotent session termination via `DatabaseVoiceSessionManager.terminate_session`, generating an audited `CallRecord` on first completion without duplicate audit rows on repeat calls.
  - **FastAPI Endpoints (`/api/voice` & `/api/v1/voice`)**:
    - `GET /capabilities`: Provider capabilities, codec support, and feature flags.
    - `POST /simulation/inbound`: Simulates inbound calls, executes routing, and returns greeting.
    - `POST /simulation/sessions/{session_id}/turns`: Simulates user speech turns and executes receptionist workflow.
    - `POST /simulation/sessions/{session_id}/terminate`: Idempotent call termination.
    - `GET /sessions/{session_id}`: Retrieves session status and full turn history.
    - `POST /webhook/{provider_name}`: Telephony webhook receiver with HMAC-SHA256 signature verification.
  - **Privacy Masking (`backend/voice/utils.py`)**:
    - Customer and business phone numbers are masked in all logs, string representations, and `CallRecord` entries (e.g., `+9180***5678`), protecting caller privacy.
- **Consequences**:
  - Voice channels integrate seamlessly with the existing shared LangGraph workflow and modular tool registry.
  - Zero duplicate agent code or hardcoded vendor APIs.
  - Complete test coverage: 116 automated tests passing across the platform.

---

### ADR-015: Exotel AgentStream Telephony Adapter and Bidirectional WebSocket Media Boundary
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: To connect the AI Receptionist platform to real Indian telecom networks (PSTN/virtual numbers), the platform requires a dedicated Exotel telephony adapter implementing Exotel's official AgentStream WebSocket protocol. The adapter must handle inbound calls routed via Exotel Voicebot and Passthru applets, stream bidirectional audio frames, validate Linear PCM audio constraints, verify cryptographic signatures, and enforce session isolation and error boundaries without breaking existing Mock provider compatibility or duplicating graph orchestration.
- **Decision**:
  - **Exotel Telephony Adapter (`backend/voice/providers/exotel.py`)**:
    - Implemented `ExotelTelephonyProvider(BaseTelephonyProvider)` fulfilling `TelephonyProvider`.
    - Typed Pydantic schemas for Exotel protocol: `ExotelWebSocketMessage`, `ExotelStartData`, `ExotelMediaData`, `ExotelStopData`, `ExotelMarkData`, `ExotelDtmfData`, `ExotelMediaFormat`.
    - Outbound frame builders: `build_exotel_media_message` (streaming audio back to caller), `build_exotel_mark_message` (tracking playback milestones), and `build_exotel_clear_message` (instant buffer flush on caller barge-in).
  - **Audio Format & Constraint Validation**:
    - Validates audio format against Exotel specifications: raw Linear PCM (16-bit mono little-endian, `audio/x-raw`, `audio/x-l16`, `linear16`) at 8000 Hz, 16000 Hz, or 24000 Hz. Incompatible encodings or sample rates are rejected with WebSocket close code 1003 (Unsupported Data).
    - Enforces chunk size boundaries (multiples of 320 bytes, maximum 100 KB).
  - **Authentication & Webhook Signature Schemes**:
    - **HTTP Webhooks**: Verifies `X-Exotel-Signature` header (`sha256=<hex_digest>`) using HMAC-SHA256 with configured `EXOTEL_WEBHOOK_SECRET`.
    - **WebSocket Handshake**: Verifies HTTP Basic Authentication (`Authorization: Basic base64(api_key:api_token)`) conforming to Exotel's `wss://<key>:<token>@host/path` connection scheme.
  - **Inbound Tenant Routing & Anti-Spoofing**:
    - Resolves tenant identity strictly from `start["to"]` (or Passthru `To`) against trusted database records (`BusinessRepository.get_by_phone_number`).
    - Unassigned numbers reject with close code 4004 (Tenant Not Found).
    - Inactive numbers reject with close code 4000 (Tenant Inactive).
    - Ambiguous numbers reject with close code 4009 (Ambiguous Tenant).
  - **FastAPI WebSocket Media Boundary (`backend/api/routers/voice.py`)**:
    - Mounted at `/api/voice/exotel/ws` (with aliases `/api/v1/voice/exotel/ws` and `/ws/voice/exotel`).
    - Protocol sequence enforcement: rejects premature `media` frames arriving before `start` with close code 1002 (Protocol Error).
    - Bounded buffering: prevents memory exhaustion with a 128 KB frame limit (`VOICE_WS_MAX_MESSAGE_BYTES`) and 1 MB audio buffer cap (`VOICE_MAX_BUFFER_BYTES`).
    - Handles disconnects, `stop` events, and idle timeouts (`VOICE_WS_IDLE_TIMEOUT_SECONDS`) idempotently, logging exactly one `CallRecord`.
  - **Pluggable Speech Processing Boundary**:
    - Preserves provider-independent `SpeechToTextProvider` and `TextToSpeechProvider` abstractions.
    - Never passes raw binary audio bytes to Groq LLM text endpoints.
  - **Zero Database Schema Mutations**:
    - Stored `stream_sid` in existing `VoiceSession.correlation_id` and `session_metadata`, maintaining full persistence compatibility without live database migrations.
- **Consequences**:
  - Exotel AgentStream integration fully operational and tested with 16 dedicated unit and integration tests.
  - 132 automated tests passing across the entire platform with 0 regressions.

---

### ADR-016: Deepgram Real-Time STT/TTS Streaming, Linear PCM Framing, and Barge-In Buffer Clearance
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: To enable natural, low-latency spoken conversations over Exotel AgentStream, the platform requires production-grade speech engines. Real-time phone conversations demand streaming Speech-to-Text with accurate endpointing and interim hypothesis detection, streaming Text-to-Speech outputting raw Linear PCM audio compatible with Exotel's telecom framing constraints, and instant barge-in support allowing callers to interrupt the AI receptionist naturally without hearing queued playback audio.
- **Decision**:
  - **Deepgram Streaming Speech-to-Text (`DeepgramSTTProvider`, `DeepgramSTTStream`)**:
    - Implemented `SpeechToTextProvider` protocol with both batch REST fallback and asynchronous WebSocket streaming (`wss://api.deepgram.com/v1/listen`).
    - Configured explicitly with `model=nova-2`, `language=en`, `encoding=linear16`, `sample_rate=8000/16000`, `channels=1`, and `endpointing=300ms`.
    - Differentiates interim hypotheses (`is_final=False`) from finalized utterances (`is_final=True` and `speech_final=True`). Interim hypotheses drive real-time barge-in detection, while finalized utterances trigger conversation turns through LangGraph.
    - Handles timeouts, keepalives, disconnects, and malformed frames gracefully without throwing uncaught exceptions or sending raw audio bytes to LLM text endpoints.
  - **Deepgram Streaming Text-to-Speech (`DeepgramTTSProvider`)**:
    - Implemented `TextToSpeechProvider` protocol with streaming WebSocket client (`wss://api.deepgram.com/v1/speak`) and REST fallback.
    - Generates 16-bit Linear PCM mono audio chunks configured at Exotel's native sample rate (8000 Hz or 16000 Hz) using `aura-asteria-en` voice.
    - Eliminates audio format transcoding overhead by matching carrier codec specifications directly at generation time.
    - Supports real-time stream cancellation via `asyncio.Event` tokens, immediately emitting `{"type": "Clear"}` control frames upon caller interruption.
  - **Audio Resampling and Framing Utilities (`backend/voice/audio.py`)**:
    - Built explicit, tested audio manipulation primitives: `resample_pcm16` (stateful/sample-aligned sample rate conversion via stdlib `audioop`), `chunk_pcm16` (multiples of 320 bytes), `pad_pcm16_to_multiple` (silence padding for PSTN boundary compliance), and `validate_pcm16_chunk` (even-byte 16-bit PCM verification).
  - **End-to-End Voice Pipeline with Barge-In (`backend/api/routers/voice.py`)**:
    - Pipeline stages: `Exotel inbound audio -> audio validation/conversion -> Deepgram STT stream -> interim speech detection (barge-in) -> finalized transcript -> VoiceTurnOrchestrator -> LangGraph receptionist workflow -> Deepgram TTS stream -> 320-byte PCM alignment -> Exotel outbound media frames`.
    - When caller begins speaking while receptionist is speaking: active TTS transmission aborts instantly, an Exotel `clear` frame is sent to purge telecom hardware buffers, and the new caller utterance is processed cleanly.
    - Preserves tenant isolation, session correlation by `stream_sid`, conversation history persistence, and two-phase pending action confirmation protections.
  - **Zero Paid Calls During Testing & Safe Manual Smoke Test**:
    - Full mock WebSocket test doubles in `tests/test_deepgram_providers.py` verify all streaming STT/TTS behaviors, codec conversions, barge-in cancellations, and tenant boundaries without requiring real credentials or incurring paid API usage.
    - Created standalone manual smoke-test script `python -m backend.voice.smoke_test` that safely verifies live credentials when configured in `.env` without exposing secrets.
- **Consequences**:
  - Live conversational voice capabilities operational and tested with 15 dedicated unit and integration tests.
  - 147 automated tests passing across the entire platform with 0 regressions.

---

## 🗺️ Feature Tracker & Roadmap

| Feature / Step | Target Scope | Status | Notes |
| :--- | :--- | :--- | :--- |
| **Step 1: Project Foundation** | Directory layout, FastAPI `/health`, config manager, `.gitignore`, initial tests | **Completed** | Clean modular boundaries established. |
| **Step 2: Tenant Dashboard & Config UI** | Streamlit prototype dashboard, business hours setup, tenant profile editor, tool library, playground, call history | **Completed** | Full multi-tenant session-state prototype operational. |
| **Step 3: Groq LLM Playground Integration** | `GroqService`, business-aware system prompts, error boundaries, playground LLM chat | **Completed** | Secure live AI conversations enabled. |
| **Step 4: Shared LangGraph Conversation Workflow** | `StateGraph`, `AgentState`, 3-node workflow (`START -> Prepare -> Generate -> Finalize -> END`), playground integration | **Completed** | Decoupled orchestration engine active. |
| **Step 5: Modular Business Tool Registry** | `ToolRegistry`, Pydantic input models, tenant permission enforcement, two-phase confirmation, mock handlers | **Completed** | Validated tool execution infrastructure ready for Step 6. |
| **Step 6: Connected Tool-Calling LangGraph Agent** | Cyclic tool-calling loop, Groq tool schemas, application authorization, two-phase confirmation boundary, UI cards | **Completed** | 57 automated tests passing; end-to-end autonomous tool orchestration. |
| **Step 7: Supabase Persistence Layer** | PostgreSQL schemas, Alembic migrations, repositories, idempotent seeds, UI & agent integration | **Completed** | 73 automated tests passing; complete multi-tenant persistence. |
| **Step 8: FastAPI REST API Layer & UI Integration** | 12 REST endpoints, Pydantic schemas, `ApiClient`, replay defense, playground via API | **Completed** | 97 automated tests passing; dashboard fully decoupled from database. |
| **Step 9A: Voice & Telephony Architecture Foundation** | Provider-independent protocols, typed events, tenant call router, turn orchestrator, durable session storage, simulation endpoints | **Completed** | 116 automated tests passing; robust foundation for live telephony providers. |
| **Step 9B: Exotel Telephony Adapter & Bidirectional WebSocket Integration** | Exotel AgentStream protocol, Linear PCM audio validation, Basic Auth handshake, HMAC signature checks, WebSocket media endpoint | **Completed** | 132 automated tests passing; live inbound Exotel adapter ready for production flows. |
---

### ADR-017: Production Readiness Hardening, Multi-Segment STT Accumulation, and Acoustic Echo Suppression
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: Prior to initiating live PSTN telephone calls, a comprehensive production readiness audit was performed across the Exotel AgentStream and Deepgram speech integration to verify protocol compliance, eliminate security vulnerabilities, prevent audio pipeline failure modes, and ensure high concurrency resilience.
- **Decision**:
  - **Database Schema Migration Resolution (`002_voice_sessions`)**:
    - Discovered that `voice_sessions` table migration (`002_voice_sessions`) was missing from the live Supabase PostgreSQL database. Applied `alembic upgrade head`, establishing the physical `voice_sessions` table and foreign key constraints on the live production cluster.
  - **STT Multi-Segment Utterance Accumulation**:
    - Identified that Deepgram streaming STT emits multiple `is_final=True` messages prior to endpointing (`speech_final=False`). Previously, premature turns could trigger on intermediate phrases.
    - Updated `DeepgramSTTStream` to accumulate intermediate finalized phrases in an internal buffer, emitting turn-ready `TranscriptEvent`s only when `speech_final=True` or `UtteranceEnd` signals that the speaker has finished their turn.
    - Preserved `is_final=False` interim hypotheses for immediate caller barge-in detection.
  - **Mandatory Production WebSocket Handshake Authentication**:
    - Hardened `@router.websocket("/exotel/ws")` to enforce mandatory HTTP Basic Authentication when `ENVIRONMENT == "production"`. Reject unauthenticated connection attempts immediately with WebSocket close code `1008 Policy Violation`.
  - **Public Voice Session Transcript Protection**:
    - Hardened `GET /api/voice/sessions/{session_id}` with tenant authorization. Reject cross-tenant session inspection with `403 Forbidden` (`Tenant authorization mismatch`), and reject anonymous transcript access in production mode with `401 Unauthorized`.
  - **Cooperative Event Loop Yielding During Audio Streaming**:
    - Injected `await asyncio.sleep(0)` between 320-byte PCM chunk transmissions, ensuring the event loop yields cycles to read incoming caller audio frames without starving inbound I/O or blocking barge-in interruptions.
  - **Acoustic Echo and Self-Playback Loop Suppression**:
    - Added an acoustic echo guard tracking recent assistant speech output. Dropped incoming transcripts matching the assistant's previous response to prevent runaway feedback loops caused by caller speakerphone reflections.
  - **Dual Pre-Flight Smoke-Test Tooling**:
    - Maintained `python -m backend.voice.smoke_test` for live Deepgram STT/TTS validation.
    - Created `python -m backend.voice.smoke_test_exotel` for live Exotel credentials, HMAC signature, and virtual number routing pre-flight verification without placing paid calls.
- **Consequences**:
  - All critical, high, and medium audit findings resolved.
  - 151 automated tests passing across 12 test modules with 0 regressions.

---

## 🗺️ Feature Tracker & Roadmap

| Feature / Step | Target Scope | Status | Notes |
| :--- | :--- | :--- | :--- |
| **Step 1: Project Foundation** | Directory layout, FastAPI `/health`, config manager, `.gitignore`, initial tests | **Completed** | Clean modular boundaries established. |
| **Step 2: Tenant Dashboard & Config UI** | Streamlit prototype dashboard, business hours setup, tenant profile editor, tool library, playground, call history | **Completed** | Full multi-tenant session-state prototype operational. |
| **Step 3: Groq LLM Playground Integration** | `GroqService`, business-aware system prompts, error boundaries, playground LLM chat | **Completed** | Secure live AI conversations enabled. |
| **Step 4: Shared LangGraph Conversation Workflow** | `StateGraph`, `AgentState`, 3-node workflow (`START -> Prepare -> Generate -> Finalize -> END`), playground integration | **Completed** | Decoupled orchestration engine active. |
| **Step 5: Modular Business Tool Registry** | `ToolRegistry`, Pydantic input models, tenant permission enforcement, two-phase confirmation, mock handlers | **Completed** | Validated tool execution infrastructure ready for Step 6. |
| **Step 6: Connected Tool-Calling LangGraph Agent** | Cyclic tool-calling loop, Groq tool schemas, application authorization, two-phase confirmation boundary, UI cards | **Completed** | 57 automated tests passing; end-to-end autonomous tool orchestration. |
| **Step 7: Supabase Persistence Layer** | PostgreSQL schemas, Alembic migrations, repositories, idempotent seeds, UI & agent integration | **Completed** | 73 automated tests passing; complete multi-tenant persistence. |
| **Step 8: FastAPI REST API Layer & UI Integration** | 12 REST endpoints, Pydantic schemas, `ApiClient`, replay defense, playground via API | **Completed** | 97 automated tests passing; dashboard fully decoupled from database. |
| **Step 9A: Voice & Telephony Architecture Foundation** | Provider-independent protocols, typed events, tenant call router, turn orchestrator, durable session storage, simulation endpoints | **Completed** | 116 automated tests passing; robust foundation for live telephony providers. |
| **Step 9B: Exotel Telephony Adapter & Bidirectional WebSocket Integration** | Exotel AgentStream protocol, Linear PCM audio validation, Basic Auth handshake, HMAC signature checks, WebSocket media endpoint | **Completed** | 132 automated tests passing; live inbound Exotel adapter ready for production flows. |
| **Step 9C: Real-Time STT/TTS & Barge-In Integration** | Deepgram streaming STT/TTS adapters, Linear PCM framing, sample rate conversion, barge-in buffer flush, voice pipeline | **Completed** | 147 automated tests passing; complete real-time spoken voice pipeline active. |
| **Step 9D: Production Readiness Audit & Pre-Flight Hardening** | Security audit, Supabase migration verification, multi-segment utterance accumulation, echo suppression, pre-flight smoke tests | **Completed** | 151 automated tests passing; verified production readiness for live PSTN calls. |
| **Step 9E: Provider Compatibility Verification & Final Pre-Call Gate** | Official doc alignment, fail-closed startup validation, mock fallback prohibition, GET/POST passthru, secret sanitization, AEC scope | **Completed** | 156 automated tests passing; live Supabase verified; final pre-call gate locked. |
| **Step 9F: Controlled First Call Preparation & Diagnostics** | Pre-flight diagnostic CLI, sanitized call telemetry engine, test business isolation, manual human test plan, safe boundaries | **Completed** | 162 automated tests passing; zero calls placed; pre-flight checks and manual test plan ready. |

---

### ADR-019: Controlled First Inbound Call Preparation, Real-Time Call Diagnostics, and Safe Test Business Isolation
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: In preparation for a controlled, human-initiated first live PSTN call, the platform required a comprehensive pre-flight verification harness, strict single-tenant isolation for the designated test number, structured sanitized observability for live call milestones, and a clear manual test sequence with human fallback procedures.
- **Decision**:
  - **Pre-Flight Diagnostic Runner (`backend/voice/preflight.py`)**:
    - Created a non-destructive CLI command (`python -m backend.voice.preflight`) separating local system verification from live provider checks.
    - Local checks: production secret presence (never logging values or placeholders), live Supabase connectivity, Alembic schema revision `002_voice_sessions`, test business status (`biz_spice_garden` / `Royal Spice Garden`), unambiguous phone number assignment (`+91 80 4123 5678`), tool scoping (dining enabled, cross-tenant healthcare disabled), endpoint protocol and path consistency (`wss://<domain>/api/voice/exotel/ws`), mock provider prohibition in production, and human operator fallback.
  - **Sanitized Call Diagnostics Engine (`backend/voice/diagnostics.py`)**:
    - Created `CallDiagnostics` tracking real-time timestamps and latencies: WebSocket connection, HTTP Basic Auth acceptance/rejection, masked `call_sid` and `stream_sid` (e.g. `call..._001`), tenant routing success/failure, first inbound audio frame arrival (bytes and timestamp), first finalized customer transcript (char count and confidence only, without logging raw transcript text by default), LLM execution duration (`llm_duration_ms`), TTS first chunk synthesis duration (`tts_duration_ms`), barge-in interruption count, and session persistence status.
    - Integrated diagnostics directly into `handle_exotel_media_stream` in `backend/api/routers/voice.py` and `VoiceTurnOrchestrator` in `backend/voice/orchestrator.py`.
  - **Safe Test-Business Isolation Boundary**:
    - Designated `biz_spice_garden` as the sole authorized test tenant. Verified that `+91 80 4123 5678` resolves to exactly one tenant and that state-modifying actions (table bookings) remain strictly in Phase A `pending_confirmation` status, preventing live database mutations or appointment fabrication during spoken calls.
  - **Human Operator Manual Test Plan**:
    - Established an 8-step testing sequence (greeting verification, grounded FAQ, unavailable fact refusal, caller barge-in cut-off, session persistence audit, explicit booking confirmation boundary, human operator transfer check, and immediate telecom fallback triggers).
- **Consequences**:
  - 162 automated tests passing across 13 test modules with 0 regressions.
  - Pre-flight diagnostic CLI operational and tested.
  - Zero live calls placed; human operator control strictly maintained.

---

### ADR-018: Provider Compatibility Verification, Acoustic Echo Mitigation, and Final Pre-Call Gate
- **Date**: 2026-10-24
- **Status**: Accepted
- **Context**: Prior to placing any live PSTN phone call, a rigorous verification pass was mandated to reconcile the implementation against official Exotel AgentStream and Deepgram streaming specifications, enforce fail-closed production gates, eliminate silent fallback to mocks, support flexible webhook methods, sanitize error logs, and clarify the operational boundaries of software echo suppression.
- **Decision**:
  - **Official Provider Protocol Verification**:
    - **Exotel AgentStream**: Reconciled against official documentation (`https://developer.exotel.com/docs/agentstream/websocket-protocol` and `https://developer.exotel.com/docs/agentstream/connect-voice-ai`). Confirmed that Exotel's Voicebot Applet accepts `wss://<API_KEY>:<API_TOKEN>@domain/path` and converts it into standard HTTP Basic Auth headers (`Authorization: Basic base64(KEY:TOKEN)`) on the WebSocket upgrade request. Confirmed JSON lifecycle events: `connected`, `start`, `media`, `dtmf`, `mark`, `clear`, `stop`. Confirmed audio constraints: raw 16-bit Linear PCM mono (`slin`), 8000 Hz or 16000 Hz, framed in 320-byte chunks.
    - **Deepgram Listen (STT)**: Reconciled against official documentation (`https://developers.deepgram.com/reference/listen/listen-streaming/`). Confirmed WebSocket URL `wss://api.deepgram.com/v1/listen` with query parameters `model=nova-2`, `language=en`, `encoding=linear16`, `sample_rate=8000`, `channels=1`, `endpointing=300`, `interim_results=true`, `smart_format=true`. Confirmed server-side authentication using the `Authorization: Token <API_KEY>` HTTP header (no tokens in URLs). Confirmed `speech_final=True` and `UtteranceEnd` event semantics for turn finalization.
    - **Deepgram Speak (TTS)**: Reconciled against official documentation (`https://developers.deepgram.com/reference/speak/speak-streaming/`). Confirmed WebSocket URL `wss://api.deepgram.com/v1/speak` with query params `model=aura-asteria-en`, `encoding=linear16`, `sample_rate=8000`, `container=none`. Confirmed header authentication `Authorization: Token <API_KEY>`. Confirmed JSON messages `{"type": "Speak"}`, `{"type": "Flush"}`, `{"type": "Clear"}` (for immediate caller barge-in cancellation), and `{"type": "Close"}`.
  - **Fail-Closed Production Startup Validation**:
    - Added `validate_production_configuration()` hooked into FastAPI's `lifespan` context manager in `backend/main.py`. In `ENVIRONMENT == "production"`, validates that `GROQ_API_KEY`, `DATABASE_URL`, `EXOTEL_ACCOUNT_SID`, `EXOTEL_API_KEY`, `EXOTEL_API_TOKEN`, and `DEEPGRAM_API_KEY` are all present, non-empty, and free of placeholder strings (e.g., `[YOUR-PASSWORD]`). If any are missing, raises a sanitized `RuntimeError` naming the missing keys without printing any credential values.
  - **Prohibition of Silent Mock Fallback in Production**:
    - Hardened `get_stt_provider()`, `get_tts_provider()`, and `get_telephony_provider()` in `backend/voice/providers/__init__.py`. When running under `ENVIRONMENT == "production"`, requesting `"mock"` providers or failing to configure live providers immediately raises a `RuntimeError`, preventing silent prototype fallbacks in live deployments.
  - **Dual HTTP GET & POST Passthru Webhook Support**:
    - Extended `@router.api_route("/exotel/passthru", methods=["GET", "POST"])` and `@router.api_route("/webhook/{provider_name}", methods=["GET", "POST"])` to support both HTTP GET and POST applets configured in Exotel call flows.
  - **Credential Sanitization in Logging**:
    - Sanitized base64 decoding error logs in `backend/voice/providers/exotel.py` to prevent credential exposure.
    - Sanitized Deepgram REST and WebSocket error logs in `backend/voice/providers/deepgram.py` to log HTTP status codes and exception class names rather than raw response bodies.
  - **Acoustic Echo Scope Clarification**:
    - Formally documented that true Acoustic Echo Cancellation (AEC) is a hardware and DSP layer responsibility (handled by mobile phone basebands, PSTN carrier echo cancelers, and telephony media gateways). The application-layer substring comparison in `handle_exotel_media_stream` serves strictly as an interim software loopback guard, not a replacement for DSP AEC.
- **Consequences**:
  - Regression test suite expanded to 156 passing tests across 12 test modules with 0 failures.
  - Live Supabase PostgreSQL database verified at migration revision `002_voice_sessions (head)`.
  - Zero live PSTN calls placed; final pre-call gate firmly locked and documented.
