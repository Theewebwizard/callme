# Codebase Index & Symbol Registry

This living document indexes every source file across the project, cataloging its architectural purpose, defined classes, functions, endpoints, and exported symbols.

> **Maintenance Note**: Whenever a file is added, modified with new symbols, or refactored, update this file to reflect the changes.

---

## 🗂️ File Registry & Symbol Breakdown

### 1. Root & Core Entry Points

#### [`app.py`](file:///d:/callme/app.py)
- **Role**: Streamlit prototype frontend application entry point.
- **Dependencies**: `streamlit`, `ui.state`, `ui.pages.*`
- **Key Responsibilities**:
  - Global page configuration (`st.set_page_config`).
  - Session state bootstrap via [`init_session_state()`](file:///d:/callme/ui/state.py#L12-L40).
  - Sidebar multi-tenant business selector (`st.selectbox`) with internal IDs (`biz_spice_garden`, `biz_apex_dental`).
  - Sidebar navigation menu (`st.radio`) routing to the 5 modular page views.
  - Sidebar active tenant summary card.

#### [`requirements.txt`](file:///d:/callme/requirements.txt)
- **Role**: Project dependency specifications with version pinning (`fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`, `python-dotenv`, `streamlit`, `groq`, `langgraph`, `pytest`, `httpx`).

#### [`.env.example`](file:///d:/callme/.env.example)
- **Role**: Environment variable reference template containing placeholders for `GROQ_API_KEY` and `GROQ_MODEL=openai/gpt-oss-20b`.

#### [`.gitignore`](file:///d:/callme/.gitignore)
- **Role**: Version control exclusion rules for secrets, caches, virtual environments, and build artifacts.

#### [`README.md`](file:///d:/callme/README.md)
- **Role**: Project orientation, setup, run instructions, Groq API configuration guide, and developer documentation.

#### [`DECISIONS.md`](file:///d:/callme/DECISIONS.md)
- **Role**: Architectural Decision Records (ADRs ADR-001 through ADR-011) and feature roadmap tracking.

#### [`CODEBASE_INDEX.md`](file:///d:/callme/CODEBASE_INDEX.md)
- **Role**: Current file. Symbol catalog, function registry, and component map.

---

### 2. Orchestration & Conversation Graph (`backend/agent/` & `agent/`)

#### [`backend/agent/__init__.py`](file:///d:/callme/backend/agent/__init__.py) & [`agent/__init__.py`](file:///d:/callme/agent/__init__.py)
- **Role**: Public interface and exports for the shared LangGraph conversation workflow and tool-calling loop.
- **Exported Symbols**:
  - `AgentState`: Typed state container for the graph execution.
  - `create_receptionist_graph`: Factory for building the compiled LangGraph `StateGraph`.
  - `invoke_receptionist_workflow`: One-shot caller for executing dialogue turns with tool loops.
  - `execute_pending_action`: Phase B confirmation handler for state-modifying tools.
  - Node definitions: `prepare_context_node`, `call_llm_node`, `execute_tools_node`, `finalize_response_node`.

#### [`backend/agent/state.py`](file:///d:/callme/backend/agent/state.py)
- **Role**: Schema definition for workflow execution state (`AgentState`).
- **Fields**:
  - `business_id`: Active tenant identifier (`str`).
  - `business_config`: Active tenant business profile and hours (`Dict[str, Any]`).
  - `enabled_tools`: Map of allowed tools (`Dict[str, Any]`).
  - `tool_definitions`: Converted Groq function tool schemas (`List[Dict[str, Any]]`).
  - `messages`: Chronological conversation turns (`List[Dict[str, Any]]`).
  - `system_instruction`: Dynamically constructed system instructions (`Optional[str]`).
  - `response_content`: Generated assistant response (`Optional[str]`).
  - `pending_action`: Intercepted state-modifying action requiring Phase B confirmation (`Optional[Dict[str, Any]]`).
  - `latest_tool_calls`: Tool calls proposed by LLM on the current turn (`Optional[List[Dict[str, Any]]]`).
  - `iteration_count`: Cycle count for bounding recursion (`int`).
  - `error`: Error description if execution failed (`Optional[str]`).
  - `success`: Workflow status boolean (`bool`).

#### [`backend/agent/nodes.py`](file:///d:/callme/backend/agent/nodes.py)
- **Role**: Execution nodes and Phase B confirmation logic.
- **Functions**:
  - `prepare_context_node(state, tool_registry)`: Resolves enabled tenant tools from `ToolRegistry`, compiles system instructions, and formats tools for Groq.
  - `call_llm_node(state, groq_service)`: Calls Groq Chat Completions passing conversation history and enabled tools; tracks iteration counts.
  - `execute_tools_node(state, tool_registry)`: Validates tool existence, checks tenant authorization, validates arguments via Pydantic models, intercepts confirmation-required actions as `pending_action`, executes read-only/mock tools, and appends tool turns.
  - `finalize_response_node(state)`: Formats final workflow response without converting errors into fake assistant claims.
  - `execute_pending_action(business_id, business_config, pending_action, confirmed, tool_registry)`: Phase B human-in-the-loop executor verifying business match and preventing double execution.

#### [`backend/agent/graph.py`](file:///d:/callme/backend/agent/graph.py)
- **Role**: LangGraph StateGraph builder and execution runner.
- **Functions**:
  - `route_after_llm(state)`: Directs to `execute_tools` if tool calls are present and iterations < 5; otherwise directs to `finalize_response`.
  - `route_after_tools(state)`: Directs to `finalize_response` if a `pending_action` was created; otherwise loops back to `call_llm`.
  - `create_receptionist_graph(groq_service, tool_registry)`: Compiles the cyclic `StateGraph`.
  - `invoke_receptionist_workflow(...)`: Convenience one-shot execution function.

---

### 3. Modular Tool Registry (`backend/tools/` & `tools/`)

#### [`backend/tools/__init__.py`](file:///d:/callme/backend/tools/__init__.py) & [`tools/__init__.py`](file:///d:/callme/tools/__init__.py)
- **Role**: Public interface and exports for the tool registry framework.
- **Exported Symbols**:
  - `ToolDefinition`, `ToolExecutionResult`, `ToolExecutionStatus`, `ToolExecutionMode`, `ToolCategory`.
  - Pydantic models: `AnswerFAQInput`, `CheckTableAvailabilityInput`, `CreateTableBookingInput`, `CheckAppointmentAvailabilityInput`, `CreateAppointmentInput`, `TakeMessageInput`, `TransferCallInput`.
  - `ToolRegistry`, `build_default_tool_registry`, `get_tool_registry`.

#### [`backend/tools/base.py`](file:///d:/callme/backend/tools/base.py)
- **Role**: Fundamental schemas and data models for tools.
- **Enums**:
  - `ToolExecutionMode`: `MOCK`, `UNAVAILABLE`, `LIVE`.
  - `ToolCategory`: `INFORMATION`, `DINING`, `HEALTHCARE`, `COMMUNICATION`.
  - `ToolExecutionStatus`: `SUCCESS`, `ERROR`, `DISABLED`, `CONFIRMATION_REQUIRED`, `VALIDATION_ERROR`, `UNAVAILABLE`.
- **Classes**:
  - `ToolExecutionResult(BaseModel)`: Standardized result container.
  - `ToolDefinition(BaseModel)`: Canonical tool descriptor and handler specification.

#### [`backend/tools/definitions.py`](file:///d:/callme/backend/tools/definitions.py)
- **Role**: Pydantic input models enforcing schema validation, boundaries, and input constraints.
- **Classes**:
  - `AnswerFAQInput`: Question string.
  - `CheckTableAvailabilityInput`: Date (`YYYY-MM-DD`), time (`HH:MM`), party size (`1-20`).
  - `CreateTableBookingInput`: Customer name, phone, date, time, party size, optional requests.
  - `CheckAppointmentAvailabilityInput`: Service/department, preferred date, optional preferred time.
  - `CreateAppointmentInput`: Patient name, phone, department, date, time, optional notes.
  - `TakeMessageInput`: Caller name, phone, message text, urgency (`low`, `normal`, `urgent`).
  - `TransferCallInput`: Escalation reason, optional target department.

#### [`backend/tools/registry.py`](file:///d:/callme/backend/tools/registry.py)
- **Role**: Tool registration, lookup, tenant authorization, and execution boundary.
- **Classes**:
  - `ToolRegistry`: Manages registered tools, duplicate rejection, tenant filtering via `get_enabled_tools_for_business()`, and safe execution via `execute_tool()`.
- **Functions**:
  - `build_default_tool_registry() -> ToolRegistry`: Factory initializing the 7 canonical tools.
  - `get_tool_registry() -> ToolRegistry`: Singleton accessor.

#### [`backend/tools/implementations/`](file:///d:/callme/backend/tools/implementations/)
- **`information.py`**: [`handle_answer_faq()`](file:///d:/callme/backend/tools/implementations/information.py#L21-L101) — Matches against business configured FAQs using stop-word filtered keyword overlap.
- **`dining.py`**: [`handle_check_table_availability()`](file:///d:/callme/backend/tools/implementations/dining.py#L18-L82) & [`handle_create_table_booking()`](file:///d:/callme/backend/tools/implementations/dining.py#L85-L115) — Deterministic hours checking, party limit checks, and simulated booking creation.
- **`healthcare.py`**: [`handle_check_appointment_availability()`](file:///d:/callme/backend/tools/implementations/healthcare.py#L18-L62) & [`handle_create_appointment()`](file:///d:/callme/backend/tools/implementations/healthcare.py#L65-L95) — Operating hours checks and simulated appointment booking.
- **`communication.py`**: [`handle_take_message()`](file:///d:/callme/backend/tools/implementations/communication.py#L18-L51) & [`handle_transfer_call()`](file:///d:/callme/backend/tools/implementations/communication.py#L54-L86) — Structured message logging and simulated call transfers.

---

### 4. Backend Application & Services (`backend/`)

#### [`backend/__init__.py`](file:///d:/callme/backend/__init__.py)
- **Role**: Package initializer for backend services.

#### [`backend/config.py`](file:///d:/callme/backend/config.py)
- **Role**: Application settings and environment variable validation (`Settings`, `get_settings()`).

#### [`backend/main.py`](file:///d:/callme/backend/main.py)
- **Role**: FastAPI backend application with CORS middleware and health checks (`GET /health`).

#### [`backend/services/groq_service.py`](file:///d:/callme/backend/services/groq_service.py)
- **Role**: Groq LLM integration service with client reuse, grounded prompt construction, and tool calling schemas.
- **Classes**:
  - `LLMResponse`: Encapsulates `content`, `tool_calls`, `error`, `success`.
  - `GroqService`: Wrapper over Groq client supporting text generation and structured function tool calls.
- **Functions**:
  - `convert_tool_definition_to_groq_schema(tool_def)`: Generates OpenAI/Groq function schemas from Pydantic `input_schema.model_json_schema()`.
  - `build_business_system_instruction(business_config)`: Assembles grounded prompts with business hours, FAQs, policies, and anti-jailbreak instructions.
  - `get_groq_service()`: Singleton factory accessor.

---

### 5. Frontend UI Package (`ui/`)

#### [`ui/__init__.py`](file:///d:/callme/ui/__init__.py), [`ui/mock_data.py`](file:///d:/callme/ui/mock_data.py), [`ui/components.py`](file:///d:/callme/ui/components.py)
- **Role**: UI presentation components and static seed fixtures.

#### [`ui/state.py`](file:///d:/callme/ui/state.py)
- **Role**: Session state access layer and multi-tenant data helpers.
- **Functions**:
  - `init_session_state`: Initializes tenant configs, catalogues, and chat histories.
  - `get_active_business_id`, `set_active_business_id`, `get_active_business`: Tenant context controls.
  - `get_playground_messages`, `add_playground_message`, `reset_playground_messages`: Chat state management.
  - `get_pending_action`, `set_pending_action`, `clear_pending_action`: Phase B confirmation state persistence.

#### [`ui/pages/`](file:///d:/callme/ui/pages/)
- **`dashboard.py`**: Page 1: Operations overview dashboard.
- **`business_setup.py`**: Page 2: Multi-tenant business configuration and receptionist policies form.
- **`tool_library.py`**: Page 3: Reusable tool catalog and tenant activation toggles.
- **`agent_playground.py`**: Page 4: Business-aware conversation playground orchestrated by LangGraph & Groq LLM with interactive confirmation cards for state-modifying actions.
- **`call_history.py`**: Page 5: Representative call logs and transcript review.

---

### 6. Database Persistence Layer (`backend/database/` & `database/`)

#### [`database/__init__.py`](file:///d:/callme/database/__init__.py) & [`backend/database/__init__.py`](file:///d:/callme/backend/database/__init__.py)
- **Role**: Public interface and exports for Supabase PostgreSQL persistence (models, engine, repositories, service, seeder).

#### [`backend/database/config.py`](file:///d:/callme/backend/database/config.py)
- **Role**: Database URL normalization and placeholder detection (`is_placeholder_db_url`, `normalize_database_url`, `get_effective_database_url`).

#### [`backend/database/models.py`](file:///d:/callme/backend/database/models.py)
- **Role**: SQLAlchemy 2.0 Declarative ORM models supporting PostgreSQL and SQLite.
- **Models**:
  - `Business`: Tenant profile, operating hours, timezone, instructions, and relations (`businesses`).
  - `BusinessFAQ`: Tenant knowledge-base items and Q&As (`business_faqs`).
  - `BusinessToolConfig`: Per-tenant enabled/disabled tool statuses with uniqueness constraint (`business_tool_configs`).
  - `CallRecord`: Inbound call logs with privacy-masked caller numbers, outcomes, and simulation flags (`call_records`).
  - `ConversationMessage`: Playground chat turns scoped to tenant (`conversation_messages`).
  - `PendingAction`: Two-phase confirmation state-modifying actions awaiting human approval (`pending_actions`).

#### [`backend/database/engine.py`](file:///d:/callme/backend/database/engine.py)
- **Role**: Engine factory, connection pooling, sessionmaker, transactional context manager, and healthcheck.
- **Functions & Classes**:
  - `DatabaseConfigurationError`, `DatabaseConnectionError`: Controlled exception hierarchy.
  - `create_database_engine(database_url, is_test, echo)`: Engine factory configuring QueuePool (PostgreSQL) or StaticPool with foreign keys (SQLite).
  - `session_scope(session_factory, engine)`: Context manager with auto-commit, rollback, and session close.
  - `check_database_connection(engine)`: Probes `SELECT 1` without exposing credentials.
  - `init_db_schema(engine)`: Creates all tables via `Base.metadata.create_all()`.

#### [`backend/database/repositories/`](file:///d:/callme/backend/database/repositories/)
- **`business_repo.py`**: [`BusinessRepository`](file:///d:/callme/backend/database/repositories/business_repo.py) — Tenant CRUD and full profile assembly (`get_full_profile`).
- **`faq_repo.py`**: [`FAQRepository`](file:///d:/callme/backend/database/repositories/faq_repo.py) — FAQ operations with tenant boundary checks and atomic replacement.
- **`tool_config_repo.py`**: [`ToolConfigRepository`](file:///d:/callme/backend/database/repositories/tool_config_repo.py) — Tool activation status lookup and updates.
- **`call_repo.py`**: [`CallRepository`](file:///d:/callme/backend/database/repositories/call_repo.py) — Call logging, filtering by outcome, and summary analytics.
- **`conversation_repo.py`**: [`ConversationRepository`](file:///d:/callme/backend/database/repositories/conversation_repo.py) — Chronological chat turn persistence and reset.
- **`pending_action_repo.py`**: [`PendingActionRepository`](file:///d:/callme/backend/database/repositories/pending_action_repo.py) — Two-phase confirmation action tracking and replay attack protection.

#### [`backend/database/service.py`](file:///d:/callme/backend/database/service.py)
- **Role**: High-level unified coordinator providing safe, tenant-scoped data access for UI and agent layers (`DatabaseService`, `get_database_service`).

#### [`backend/database/seed.py`](file:///d:/callme/backend/database/seed.py)
- **Role**: Idempotent database seeder (`seed_database`) populating initial sample tenants (`biz_spice_garden`, `biz_apex_dental`) without duplicating records or destroying existing user edits. Executable via `python -m backend.database.seed`.

#### [`backend/database/migrations/`](file:///d:/callme/backend/database/migrations/)
- **Role**: Alembic migration scripts (`env.py`, `script.py.mako`, `versions/001_initial_schema.py`) establishing the versioned initial database schema.

---

### 7. FastAPI REST API Layer (`backend/api/` & `ui/api_client.py`)

#### [`backend/api/schemas.py`](file:///d:/callme/backend/api/schemas.py)
- **Role**: Pydantic v2 request and response validation schemas for all REST API endpoints.
- **Schemas**:
  - `BusinessSummaryResponse`: Concise summary for tenant selector and listings.
  - `FAQItem`, `FAQListUpdateRequest`: Knowledge base QA item and atomic replacement payload.
  - `BusinessDetailResponse`, `BusinessUpdateRequest`: Tenant configuration profile retrieval and update models.
  - `ToolItemResponse`, `BusinessToolsResponse`, `ToolStatusUpdateRequest`: Canonical tool catalog and enablement models.
  - `CallRecordResponse`, `CallHistoryResponse`: Paginated call audit log models.
  - `PlaygroundMessageRequest`, `PlaygroundMessageResponse`: Dialogue request and orchestrated turn response.
  - `ActionConfirmResponse`: Phase B human-in-the-loop action confirmation response.

#### [`backend/api/routers/`](file:///d:/callme/backend/api/routers/)
- **`businesses.py`**: `GET /api/businesses`, `GET /api/businesses/{id}`, `PUT /api/businesses/{id}` — Tenant listing, detail, and atomic profile update.
- **`faqs.py`**: `GET /api/businesses/{id}/faqs`, `PUT /api/businesses/{id}/faqs` — FAQ knowledge base listing and update.
- **`tools.py`**: `GET /api/businesses/{id}/tools`, `PUT /api/businesses/{id}/tools` — Canonical tool listing and status update with canonical registry validation.
- **`calls.py`**: `GET /api/businesses/{id}/calls` — Audited call records with pagination and outcome filtering.
- **`playground.py`**: `POST /api/businesses/{id}/playground/messages` — Conversation endpoint orchestrating LangGraph workflow with tool calling and turn persistence.
- **`pending_actions.py`**: `POST /api/businesses/{id}/pending-actions/{action_id}/confirm` and `cancel` — Phase B confirmation and cancellation enforcing business scoping and replay defense (HTTP 400).
- **`voice.py`**: Voice and telephony endpoints:
  - `GET /api/voice/capabilities` (and `/api/v1/voice/capabilities`) — Supported providers, streaming flags, and audio codecs.
  - `POST /api/voice/simulation/inbound` — Inbound call simulation, tenant resolution, status checks, and greeting.
  - `POST /api/voice/simulation/sessions/{session_id}/turns` — Inbound speech turns orchestrating LangGraph workflow.
  - `POST /api/voice/simulation/sessions/{session_id}/terminate` — Idempotent session termination and CallRecord auditing.
  - `GET /api/voice/sessions/{session_id}` — Detailed session metadata and conversation history.
  - `POST /api/voice/webhook/{provider_name}` — Telephony provider webhook with HMAC-SHA256 signature verification.

#### [`ui/api_client.py`](file:///d:/callme/ui/api_client.py)
- **Role**: Reusable HTTP REST API client connecting Streamlit UI components to the FastAPI backend.
- **Classes & Functions**:
  - `ApiClientError`, `ApiConnectionError`, `ApiNotFoundError`: Dedicated exception hierarchy.
  - `ApiClient`: Client wrapping `httpx` with timeout controls, error translation, and endpoints mapping.
  - `get_api_client()`, `set_api_client()`: Singleton accessor and dependency-injection override.

---

### 8. Voice and Telephony Architecture Foundation (`backend/voice/` & `voice/`)

#### [`backend/voice/__init__.py`](file:///d:/callme/backend/voice/__init__.py) & [`voice/__init__.py`](file:///d:/callme/voice/__init__.py)
- **Role**: Package export aggregator for telephony protocols, typed events, routers, orchestrators, and utility functions.

#### [`backend/voice/utils.py`](file:///d:/callme/backend/voice/utils.py)
- **Role**: Phone number normalization and privacy masking utilities.
- **Functions**:
  - `normalize_phone_number(raw_phone: Optional[str]) -> str`: Canonical E.164 normalization supporting Indian trunk prefixes (0), standard 10 digits, and international format (+91).
  - `mask_phone_number(phone: Optional[str]) -> str`: Privacy-compliant masking of phone numbers (`+9180***5678` or `[ANONYMOUS]`).

#### [`backend/voice/events.py`](file:///d:/callme/backend/voice/events.py)
- **Role**: Typed Pydantic data schemas for voice events and sessions.
- **Classes**:
  - `CallStatus`, `SessionStatus`: Enumerations of telephony and session states.
  - `ProviderCapabilities`: Capability matrix for telephony, STT, and TTS engines.
  - `InboundCallEvent`: Normalized inbound telephony call event with phone masking properties.
  - `CallSession`: Active or completed voice conversation session model.
  - `TranscriptEvent`: Finalized speech-to-text transcript turn event.
  - `VoiceTurnResult`: Result of LangGraph orchestration for a voice turn.
  - `CallTerminationEvent`: Call hangup and outcome event.
  - `CallControlResult`: Telephony action payload returned to providers.

#### [`backend/voice/interfaces.py`](file:///d:/callme/backend/voice/interfaces.py)
- **Role**: Provider-independent Protocols and abstract contracts.
- **Protocols**:
  - `TelephonyProvider`: Contract for webhook parsing, cryptographic signature verification, call accept/reject/hangup.
  - `SpeechToTextProvider`: Contract for audio stream/buffer transcription.
  - `TextToSpeechProvider`: Contract for text synthesis into audio frames.
  - `VoiceSessionManager`: Contract for session creation, updates, history, and idempotent termination.

#### [`backend/voice/providers/`](file:///d:/callme/backend/voice/providers/)
- **Role**: Telephony, STT, and TTS provider registry and adapter implementations.
- **Components**:
  - `BaseTelephonyProvider`: Abstract base class for telephony adapters.
  - `ExotelTelephonyProvider`: Production adapter for Exotel AgentStream WebSockets and Passthru webhooks with Linear PCM audio validation and HMAC-SHA256 signature checks.
  - `ExotelWebSocketMessage`, `ExotelStartData`, `ExotelMediaData`, `ExotelStopData`, `ExotelMarkData`, `ExotelDtmfData`, `ExotelMediaFormat`: Pydantic event schemas for the official Exotel protocol.
  - `build_exotel_media_message()`, `build_exotel_mark_message()`, `build_exotel_clear_message()`: Outbound protocol frame builders.
  - `validate_exotel_audio_format()`: Linear PCM 16-bit mono audio format and sample rate validator (8000, 16000, 24000 Hz).
  - `DeepgramSTTProvider`, `DeepgramSTTStream`: Production streaming and batch Speech-to-Text provider connecting Exotel audio to Deepgram Listen WebSocket API (`wss://api.deepgram.com/v1/listen`) with interim vs final transcript differentiation and endpointing.
  - `DeepgramTTSProvider`: Production streaming and batch Text-to-Speech provider synthesizing speech via Deepgram Speak WebSocket API (`wss://api.deepgram.com/v1/speak`) into Linear PCM 16-bit mono chunks with cancellation support.
  - `MockTelephonyProvider`: Deterministic mock provider with configurable HMAC-SHA256 signature verification.
  - `MockSTTProvider`, `MockTTSProvider`, `MockSTTStream`: Deterministic speech transcription and synthesis adapters.
  - `get_telephony_provider()`, `register_telephony_provider()`, `get_stt_provider()`, `register_stt_provider()`, `get_tts_provider()`, `register_tts_provider()`: Provider registry factory functions.

#### [`backend/voice/audio.py`](file:///d:/callme/backend/voice/audio.py)
- **Role**: Audio conversion and framing utilities for telephony streaming.
- **Functions**:
  - `resample_pcm16(audio_bytes, in_rate, out_rate) -> bytes`: Resamples 16-bit Linear PCM audio between carrier and provider sample rates while preserving 2-byte sample alignment.
  - `chunk_pcm16(audio_bytes, chunk_size_bytes=320, pad=False) -> List[bytes]`: Splits continuous PCM streams into discrete chunks matching carrier constraints.
  - `pad_pcm16_to_multiple(audio_bytes, multiple=320) -> bytes`: Silence-pads audio buffers so total length is an exact multiple of 320 bytes.
  - `validate_pcm16_chunk(chunk, max_bytes=102400) -> Tuple[bool, Optional[str]]`: Verifies 16-bit PCM even-byte length and size limits.

#### [`backend/voice/smoke_test.py`](file:///d:/callme/backend/voice/smoke_test.py)
- **Role**: Standalone manual smoke test verifying live Deepgram credentials, TTS synthesis, and STT transcription without leaking secrets. Executable via `python -m backend.voice.smoke_test`.

#### [`backend/voice/smoke_test_exotel.py`](file:///d:/callme/backend/voice/smoke_test_exotel.py)
- **Role**: Standalone manual pre-flight audit script verifying Exotel Basic Auth validation, HMAC-SHA256 signature verification, and database tenant routing without placing paid calls. Executable via `python -m backend.voice.smoke_test_exotel`.

#### [`backend/voice/session_manager.py`](file:///d:/callme/backend/voice/session_manager.py)
- **Role**: Persistent voice session lifecycle management (`DatabaseVoiceSessionManager`).
- **Key Responsibilities**:
  - Backed by `DatabaseService` and `VoiceSessionRepository`.
  - Creates durable `VoiceSession` records with correlation tracking.
  - Scopes conversation turns to individual phone calls (`session_id`).
  - Idempotent termination: logs audit `CallRecord` on first completion without duplicate rows on repeat calls.

#### [`backend/voice/router.py`](file:///d:/callme/backend/voice/router.py)
- **Role**: Tenant resolution and inbound call routing (`InboundCallRouter`).
- **Key Responsibilities**:
  - Resolves business tenant by E.164-normalized `called_number`.
  - Rejects unassigned numbers (`UnknownTenantError` -> 404).
  - Rejects inactive or disconnected numbers (`InactiveTenantError` -> 400).
  - Detects and rejects numbers shared across multiple tenants (`AmbiguousTenantError` -> 409).
  - Anti-spoofing check: verifies claimed `business_id` against dialled number owner (`TenantMismatchError` -> 403).
  - Instantiates session and records initial tenant greeting.

#### [`backend/voice/orchestrator.py`](file:///d:/callme/backend/voice/orchestrator.py)
- **Role**: Voice turn dialogue execution (`VoiceTurnOrchestrator`).
- **Key Responsibilities**:
  - Serializes concurrent speech turns per session using in-process session locks (`_session_locks`).
  - Fetches isolated session history and full business configuration.
  - Executes shared LangGraph receptionist workflow and modular tool registry.
  - Enforces two-phase action confirmation boundary (preserves `pending_action`).
  - Error boundary: returns polite fallback message without fabricating false reservations.

#### [`backend/voice/diagnostics.py`](file:///d:/callme/backend/voice/diagnostics.py)
- **Role**: Sanitized call diagnostics and telemetry tracker (`CallDiagnostics`).
- **Key Responsibilities**:
  - Tracks timestamps and latencies: WebSocket connection, authentication, start, routing, first audio frame, first final customer transcript (chars/confidence only), LLM execution duration (`llm_duration_ms`), TTS first audio chunk duration (`tts_duration_ms`), barge-in count, and session persistence status.
  - Masks provider identifiers (`mask_identifier`) to prevent plaintext leakage of sensitive IDs.
  - Eliminates raw audio and full customer speech logging by default.

#### [`backend/voice/preflight.py`](file:///d:/callme/backend/voice/preflight.py)
- **Role**: Pre-flight diagnostic and controlled call gate CLI (`PreFlightRunner`). Executable via `python -m backend.voice.preflight`.
- **Key Responsibilities**:
  - Validates production configuration and secrets without printing credential values or placeholders.
  - Inspects Supabase PostgreSQL connectivity and Alembic schema revision (`002_voice_sessions`).
  - Validates test business status (`biz_spice_garden`), unambiguous number mapping (`+91 80 4123 5678`), and tool scoping.
  - Validates WSS endpoint consistency, mock provider prohibition in production, and human operator fallback.
  - Separates local checks from live provider checks.

---

### 9. Database Layer & Migrations (`backend/database/`)

#### [`backend/database/models.py`](file:///d:/callme/backend/database/models.py)
- Added `VoiceSession` model and `ConversationMessage.session_id` foreign key.

#### [`backend/database/repositories/voice_session_repo.py`](file:///d:/callme/backend/database/repositories/voice_session_repo.py)
- `VoiceSessionRepository`: Handles session CRUD, status transitions, last turn timestamps, and active session queries.

#### [`backend/database/migrations/versions/002_voice_sessions.py`](file:///d:/callme/backend/database/migrations/versions/002_voice_sessions.py)
- Alembic migration creating `voice_sessions` table and adding `session_id` column to `conversation_messages`.

---

### 10. Automated Test Suite (`tests/`)

#### [`tests/test_exotel_adapter.py`](file:///d:/callme/tests/test_exotel_adapter.py)
- **Role**: Automated unit and integration tests for Step 9B: Exotel Telephony Adapter and Bidirectional WebSocket Media Boundary (16 tests).
- **Coverage**:
  - Exotel provider registration, capabilities, and format validators.
  - Passthru webhook HMAC-SHA256 signature verification (`X-Exotel-Signature`).
  - Handshake HTTP Basic Authentication verification and rejection.
  - Full valid WebSocket lifecycle (`connected` -> `start` -> `media` -> `mark` -> `stop`).
  - Rejection of out-of-order events (`media` before `start`).
  - Rejection of unsupported audio encodings and sample rates.
  - Rejection of unassigned and inactive called numbers.
  - Duplicate `start` event resiliency.
  - Idempotent termination on disconnect / `stop` (single `CallRecord`).
  - Root `/ws/voice/exotel` and `/api/voice/exotel/ws` route parity.
  - Frame size limit enforcement (128 KB) and bounded audio buffering (1 MB).
  - DTMF and clear (barge-in) event handling.
  - Cross-tenant conversation history isolation across simultaneous streams.

#### [`tests/test_call_diagnostics_and_preflight.py`](file:///d:/callme/tests/test_call_diagnostics_and_preflight.py)
- **Role**: Automated unit and integration tests for Step 9F: Call Diagnostics and Pre-Flight Gate (6 tests).
- **Coverage**:
  - `CallDiagnostics` complete lifecycle tracking, timestamp recording, and identifier masking.
  - Sanitized diagnostic exports via `to_dict()` (no secrets, raw audio, or transcripts).
  - Error paths: failed authentication, failed routing, and empty/short identifier masking.
  - `PreFlightRunner` validation of production configuration, Supabase connection, Alembic migration `002_voice_sessions`, and test business isolation.
  - `PreFlightRunner` missing secret and placeholder detection without secret exposure.
  - WebSocket media stream integration verifying live diagnostic recording during active sessions.

#### [`tests/test_audit_production_readiness.py`](file:///d:/callme/tests/test_audit_production_readiness.py)
- **Role**: Automated audit, security, and regression tests for Step 9D/9E: Production Readiness & Provider Verification (9 tests).
- **Coverage**:
  - Production mode mandatory WebSocket handshake authentication (close code 1008).
  - Public transcript inspection tenant authorization (403) and production authentication requirement (401).
  - Multi-segment Deepgram STT utterance accumulation and endpointing (`speech_final=False` vs `speech_final=True`).
  - Acoustic echo and self-playback loop suppression.
  - Fail-closed production configuration startup validation (`validate_production_configuration`).
  - Prohibition of silent mock fallbacks in production mode for telephony, STT, and TTS.
  - Deepgram token header authentication verification (no secrets in URL query parameters).
  - Dual HTTP GET & POST support for Exotel Passthru applet webhooks.
  - Rejection of spoofed/forged tenant claims on inbound calls (403 Forbidden).

#### [`tests/test_deepgram_providers.py`](file:///d:/callme/tests/test_deepgram_providers.py)
- **Role**: Automated unit and integration tests for Step 9C: Deepgram Speech-to-Text, Text-to-Speech, and Real-Time Voice Pipeline (15 tests).
- **Coverage**:
  - Linear PCM audio sample rate conversion (8000 Hz <-> 16000 Hz) and 16-bit alignment.
  - Silence padding to multiples of 320 bytes and frame chunking.
  - Streaming STT interim vs final transcript differentiation and endpointing.
  - Empty, malformed, and keepalive frame handling.
  - Audio chunk validation and size limit enforcement.
  - Streaming TTS chunk generation, Speak/Flush frames, and completion markers.
  - Real-time barge-in cancellation and Exotel `clear` frame emission.
  - Batch STT/TTS REST fallback and error handling without crashing.
  - Cross-tenant session and history isolation during concurrent streams.
  - Two-phase pending action confirmation protection in spoken conversation.

#### [`tests/test_voice_foundation.py`](file:///d:/callme/tests/test_voice_foundation.py)
- **Role**: Automated unit and integration tests for Step 9A: Voice and Telephony Architecture Foundation (19 tests).
- **Coverage**:
  - Voice capabilities endpoint and codecs.
  - Inbound routing and tenant resolution from called numbers.
  - E.164 normalization across diverse input formats.
  - Rejection of unknown, inactive, ambiguous, and spoofed tenant calls.
  - Session conversation history isolation between separate calls and the playground.
  - Voice turn orchestration through LangGraph and Groq.
  - Two-phase action confirmation preservation in voice turns.
  - Concurrency serialization per session lock.
  - Idempotent session termination and CallRecord generation.
  - Webhook HMAC signature verification.
  - Privacy masking of caller and called phone numbers.

#### [`tests/test_api.py`](file:///d:/callme/tests/test_api.py)
- **Role**: Automated unit and integration tests for all REST API endpoints, Pydantic schemas, LangGraph playground integration, Phase B pending action confirmation/cancellation, replay protection, and `ApiClient` error handling (24 tests).

#### [`tests/test_database.py`](file:///d:/callme/tests/test_database.py)
- **Role**: Automated unit and integration tests for database configuration, engine creation, model CRUD, foreign key enforcement, tool uniqueness, call filtering, conversation persistence, pending action lifecycle, replay protection, and seed idempotency (16 tests).

#### [`tests/test_agent_tools.py`](file:///d:/callme/tests/test_agent_tools.py)
- **Role**: Automated unit tests for autonomous tool calling, execution loop limits, malformed JSON recovery, tenant authorization boundaries, Phase A pending action interception, Phase B user confirmation execution, and cross-tenant action rejection (10 tests).

#### [`tests/test_tool_registry.py`](file:///d:/callme/tests/test_tool_registry.py)
- **Role**: Automated unit tests for tool definitions, registration, duplicate checks, tenant permissions, Pydantic validation, confirmation guards, and mock handlers (16 tests).

#### [`tests/test_agent_graph.py`](file:///d:/callme/tests/test_agent_graph.py)
- **Role**: Automated unit tests for LangGraph StateGraph, node transitions, and tenant parameterization (11 tests).

#### [`tests/test_groq_service.py`](file:///d:/callme/tests/test_groq_service.py)
- **Role**: Automated unit tests for Groq LLM service, response parsing, error handling, and prompt construction (12 tests).

#### [`tests/test_ui_state.py`](file:///d:/callme/tests/test_ui_state.py)
- **Role**: Automated unit tests for Streamlit multi-tenant session-state isolation, business tools logic, and pending action lifecycle (7 tests).

#### [`tests/test_health.py`](file:///d:/callme/tests/test_health.py)
- **Role**: Automated unit tests for FastAPI backend `/health` endpoint (2 tests).
