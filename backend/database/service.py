"""
Unified Database Service coordinating repositories across business operations.
Provides transactional boundaries, fallback detection, and decoupled data access for UI and agents.
"""

from typing import Optional, Dict, List, Any, Tuple
import time
import logging
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import Engine, select, func

from backend.database.engine import (
    get_engine,
    get_session_factory,
    session_scope,
    check_database_connection,
    DatabaseConfigurationError,
)
from backend.database.repositories import (
    BusinessRepository,
    FAQRepository,
    ToolConfigRepository,
    CallRepository,
    ConversationRepository,
    PendingActionRepository,
    VoiceSessionRepository,
    ToolDemandRepository,
    ResourceRepository,
    ReservationRepository,
    ReservationConflictError,
)

logger = logging.getLogger(__name__)


class DatabaseService:
    """Unified service providing safe, tenant-scoped data access."""

    def __init__(
        self,
        engine: Optional[Engine] = None,
        session_factory: Optional[sessionmaker] = None,
    ) -> None:
        self._engine = engine
        self._session_factory = session_factory
        self._profile_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._calls_cache: Dict[str, Tuple[float, Tuple[List[Dict[str, Any]], int]]] = {}

    def invalidate_profile_cache(self, business_id: Optional[str] = None) -> None:
        """Clear cached business profile and calls for real-time consistency."""
        if business_id:
            self._profile_cache.pop(business_id, None)
            keys_to_del = [k for k in self._calls_cache if k.startswith(f"{business_id}:")]
            for k in keys_to_del:
                self._calls_cache.pop(k, None)
        else:
            self._profile_cache.clear()
            self._calls_cache.clear()

    @property
    def session_factory(self) -> sessionmaker:
        """Lazy-loaded session factory."""
        if self._session_factory is None:
            self._session_factory = get_session_factory(engine=self._engine)
        return self._session_factory

    def is_available(self) -> bool:
        """Check if database is configured and operational with short TTL cache."""
        now = time.time()
        if hasattr(self, "_last_avail_check"):
            last_ts, last_val = self._last_avail_check
            if (now - last_ts) < 30.0:
                return last_val

        status = check_database_connection(engine=self._engine)
        val = bool(status.get("connected", False))
        self._last_avail_check = (now, val)
        return val

    def get_connection_info(self) -> Dict[str, Any]:
        """Return connectivity diagnosis information."""
        return check_database_connection(engine=self._engine)

    def get_all_businesses(self) -> Dict[str, Dict[str, Any]]:
        """Retrieve full profiles for all registered businesses."""
        with session_scope(self.session_factory) as session:
            repo = BusinessRepository(session)
            return repo.list_all_full()

    def get_business_profile(self, business_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve full profile for a specific business with in-memory TTL caching."""
        cached = self._profile_cache.get(business_id)
        if cached:
            ts, profile = cached
            if (time.time() - ts) < 180.0:
                return profile

        with session_scope(self.session_factory) as session:
            repo = BusinessRepository(session)
            profile = repo.get_full_profile(business_id)
            if profile:
                self._profile_cache[business_id] = (time.time(), profile)
            return profile

    def business_exists(self, business_id: str) -> bool:
        """Check if business exists, using cached profile or fast primary key lookup."""
        if business_id in self._profile_cache:
            return True
        with session_scope(self.session_factory) as session:
            repo = BusinessRepository(session)
            return repo.exists(business_id)

    def get_business_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Retrieve full profile for a business by owner Gmail address."""
        with session_scope(self.session_factory) as session:
            repo = BusinessRepository(session)
            biz = repo.get_by_owner_email(email)
            if not biz:
                return None
            return repo.get_full_profile(biz.id)

    def authenticate_business(self, email_or_identifier: str, plain_password: str) -> Optional[Dict[str, Any]]:
        """Verify business tenant Gmail/identifier and password, returning full profile if valid."""
        from backend.auth import verify_password
        with session_scope(self.session_factory) as session:
            repo = BusinessRepository(session)
            target = email_or_identifier.strip().lower()

            from sqlalchemy.orm import joinedload
            from backend.database.models import Business
            stmt = (
                select(Business)
                .options(joinedload(Business.faqs), joinedload(Business.tool_configs))
                .where(func.lower(Business.owner_email) == target)
                .limit(1)
            )
            biz = session.scalars(stmt).unique().first()

            # 2. Look up by business ID or Name if email lookup misses
            if not biz:
                id_stmt = (
                    select(Business)
                    .options(joinedload(Business.faqs), joinedload(Business.tool_configs))
                    .where(
                        (func.lower(Business.id) == target)
                        | (func.lower(Business.name) == target)
                    )
                    .limit(1)
                )
                biz = session.scalars(id_stmt).unique().first()

            if not biz:
                return None

            # Verify password
            if not biz.password_hash or not verify_password(plain_password, biz.password_hash):
                return None

            base_dict = biz.to_dict()
            base_dict["faqs"] = [faq.to_dict() for faq in (biz.faqs or [])]
            base_dict["enabled_tools"] = {tc.tool_id: tc.is_enabled for tc in (biz.tool_configs or [])}
            base_dict["tool_configs"] = {tc.tool_id: tc.to_dict() for tc in (biz.tool_configs or [])}
            base_dict["stats"] = {
                "active_status": "Active",
                "total_calls": 0,
                "bookings_completed": 0,
                "escalated_calls": 0,
                "avg_duration": "0m 00s",
            }
            return base_dict

    def save_business_profile(
        self,
        business_id: str,
        updates: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Update business profile fields and optionally replace FAQs if supplied.
        Runs in a single transactional unit.
        """
        self.invalidate_profile_cache(business_id)
        with session_scope(self.session_factory) as session:
            biz_repo = BusinessRepository(session)
            updated_biz = biz_repo.update(business_id, updates)
            if not updated_biz:
                return None

            # If FAQs are included in updates, replace them atomically
            if "faqs" in updates:
                faq_repo = FAQRepository(session)
                faq_repo.replace_all_for_business(business_id, updates["faqs"])

            session.flush()
            session.expire(updated_biz)
            profile = biz_repo.get_full_profile(business_id)
            if profile:
                self._profile_cache[business_id] = (time.time(), profile)
            return profile

    def create_business(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new business record."""
        with session_scope(self.session_factory) as session:
            biz_repo = BusinessRepository(session)
            biz = biz_repo.create(data)
            return biz.to_dict()

    def update_business(self, business_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update mutable fields of a business."""
        return self.save_business_profile(business_id, updates)

    def delete_business(self, business_id: str) -> bool:
        """Delete a business and cascade delete related records."""
        self.invalidate_profile_cache(business_id)
        with session_scope(self.session_factory) as session:
            biz_repo = BusinessRepository(session)
            return biz_repo.delete(business_id)

    def save_business_faqs(
        self,
        business_id: str,
        faqs: List[Dict[str, str]],
    ) -> List[Dict[str, Any]]:
        """Replace all FAQs for a business."""
        self.invalidate_profile_cache(business_id)
        with session_scope(self.session_factory) as session:
            faq_repo = FAQRepository(session)
            created = faq_repo.replace_all_for_business(business_id, faqs)
            return [f.to_dict() for f in created]

    def list_faqs(self, business_id: str) -> List[Dict[str, Any]]:
        """List all FAQs configured for a business tenant."""
        with session_scope(self.session_factory) as session:
            faq_repo = FAQRepository(session)
            faqs = faq_repo.list_for_business(business_id)
            return [f.to_dict() for f in faqs]

    def set_tool_status(
        self,
        business_id: str,
        tool_id: str,
        is_enabled: bool,
    ) -> None:
        """Update tool activation status for a tenant."""
        self.invalidate_profile_cache(business_id)
        with session_scope(self.session_factory) as session:
            tool_repo = ToolConfigRepository(session)
            tool_repo.set_tool_status(business_id, tool_id, is_enabled)

    def get_tool_config(self, business_id: str, tool_id: str) -> Optional[Dict[str, Any]]:
        """Fetch detailed tool capability configuration for a tenant."""
        with session_scope(self.session_factory) as session:
            tool_repo = ToolConfigRepository(session)
            cfg = tool_repo.get_tool_config(business_id, tool_id)
            return cfg.to_dict() if cfg else None

    def list_tool_configs(self, business_id: str) -> List[Dict[str, Any]]:
        """Fetch all tool capability configurations for a tenant."""
        with session_scope(self.session_factory) as session:
            tool_repo = ToolConfigRepository(session)
            configs = tool_repo.list_tool_configs(business_id)
            return [c.to_dict() for c in configs]

    def set_tool_capability(
        self,
        business_id: str,
        tool_id: str,
        is_enabled: Optional[bool] = None,
        status: Optional[str] = None,
        selected_option_id: Optional[str] = None,
        configuration: Optional[Dict[str, Any]] = None,
        readiness_details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Update tool capability state, configuration, and readiness verification."""
        self.invalidate_profile_cache(business_id)
        with session_scope(self.session_factory) as session:
            tool_repo = ToolConfigRepository(session)
            cfg = tool_repo.set_tool_capability(
                business_id=business_id,
                tool_id=tool_id,
                is_enabled=is_enabled,
                status=status,
                selected_option_id=selected_option_id,
                configuration=configuration,
                readiness_details=readiness_details,
            )
            return cfg.to_dict()

    # ---------------------------------------------------------------------------
    # Capability Setup Wizard Sessions & Credentials
    # ---------------------------------------------------------------------------

    def save_setup_session(
        self,
        business_id: str,
        tool_id: str,
        session_id: Optional[str] = None,
        selected_option_id: Optional[str] = None,
        current_step: str = "select_option",
        step_data: Optional[Dict[str, Any]] = None,
        status: str = "needs_input",
        validation_errors: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Create or update a resumable capability setup session."""
        with session_scope(self.session_factory) as session:
            tool_repo = ToolConfigRepository(session)
            sess = tool_repo.save_setup_session(
                business_id=business_id,
                tool_id=tool_id,
                session_id=session_id,
                selected_option_id=selected_option_id,
                current_step=current_step,
                step_data=step_data,
                status=status,
                validation_errors=validation_errors,
            )
            return sess.to_dict()

    def get_setup_session(self, session_id: str, business_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Fetch setup session by ID."""
        with session_scope(self.session_factory) as session:
            tool_repo = ToolConfigRepository(session)
            sess = tool_repo.get_setup_session(session_id, business_id=business_id)
            return sess.to_dict() if sess else None

    def get_setup_session_by_tool(self, business_id: str, tool_id: str) -> Optional[Dict[str, Any]]:
        """Fetch latest setup session for a tool."""
        with session_scope(self.session_factory) as session:
            tool_repo = ToolConfigRepository(session)
            sess = tool_repo.get_setup_session_by_tool(business_id, tool_id)
            return sess.to_dict() if sess else None

    def delete_setup_session(self, session_id: str, business_id: Optional[str] = None) -> bool:
        """Purge completed setup session."""
        with session_scope(self.session_factory) as session:
            tool_repo = ToolConfigRepository(session)
            return tool_repo.delete_setup_session(session_id, business_id=business_id)

    def save_credential(
        self,
        business_id: str,
        tool_id: str,
        option_id: Optional[str] = None,
        encrypted_secrets: str = "",
        key_fingerprint: str = "",
        scopes: Optional[List[str]] = None,
        provider_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Store encrypted integration secrets."""
        effective_option = option_id or provider_name or "default"
        with session_scope(self.session_factory) as session:
            tool_repo = ToolConfigRepository(session)
            cred = tool_repo.save_credential(
                business_id=business_id,
                tool_id=tool_id,
                option_id=effective_option,
                encrypted_secrets=encrypted_secrets,
                key_fingerprint=key_fingerprint,
                scopes=scopes,
            )
            return cred.to_dict()

    save_credential_encrypted = save_credential

    def get_credential_raw(self, business_id: str, tool_id: str) -> Optional[Dict[str, Any]]:
        """Fetch raw credential record (including encrypted secrets for internal decryption)."""
        with session_scope(self.session_factory) as session:
            tool_repo = ToolConfigRepository(session)
            cred = tool_repo.get_credential(business_id, tool_id)
            if not cred:
                return None
            return {
                "id": cred.id,
                "business_id": cred.business_id,
                "tool_id": cred.tool_id,
                "option_id": cred.option_id,
                "encrypted_secrets": cred.encrypted_secrets,
                "key_fingerprint": cred.key_fingerprint,
                "scopes": cred.scopes or [],
                "expires_at": cred.expires_at,
            }

    def delete_credential(self, business_id: str, tool_id: str) -> bool:
        """Purge credentials for a tool integration."""
        with session_scope(self.session_factory) as session:
            tool_repo = ToolConfigRepository(session)
            return tool_repo.delete_credential(business_id, tool_id)

    def record_capability_audit(
        self,
        business_id: str,
        tool_id: str,
        event_type: str,
        details: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record operational audit telemetry."""
        with session_scope(self.session_factory) as session:
            tool_repo = ToolConfigRepository(session)
            event = tool_repo.record_audit_event(
                business_id=business_id,
                tool_id=tool_id,
                event_type=event_type,
                details=details,
                correlation_id=correlation_id,
            )
            return event.to_dict()

    def list_capability_audits(
        self,
        business_id: str,
        tool_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List audit events for a tenant capability."""
        with session_scope(self.session_factory) as session:
            tool_repo = ToolConfigRepository(session)
            events = tool_repo.list_audit_events(business_id, tool_id=tool_id, limit=limit)
            return [e.to_dict() for e in events]

    list_capability_audit_events = list_capability_audits

    # ---------------------------------------------------------------------------
    # First-Party Reservable Resources & Reservations
    # ---------------------------------------------------------------------------

    def list_resources(
        self,
        business_id: str,
        resource_type: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """List reservable resources (tables, rooms) for a business."""
        with session_scope(self.session_factory) as session:
            res_repo = ResourceRepository(session)
            items = res_repo.list_resources(business_id, resource_type=resource_type, is_active=is_active)
            return [r.to_dict() for r in items]

    def get_resources(
        self,
        business_id: str,
        resource_type: Optional[str] = None,
        active_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Query resources for a business with optional active filter."""
        return self.list_resources(
            business_id=business_id,
            resource_type=resource_type,
            is_active=True if active_only else None,
        )

    def get_resource(self, resource_id: str, business_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Fetch a specific resource."""
        with session_scope(self.session_factory) as session:
            res_repo = ResourceRepository(session)
            res = res_repo.get_resource(resource_id, business_id=business_id)
            return res.to_dict() if res else None

    def create_resource(
        self,
        business_id: str,
        name: str,
        capacity: int = 4,
        min_party_size: int = 1,
        max_party_size: int = 4,
        resource_type: str = "table",
        section: Optional[str] = None,
        is_active: bool = True,
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Register a new reservable table or room."""
        with session_scope(self.session_factory) as session:
            res_repo = ResourceRepository(session)
            res = res_repo.create_resource(
                business_id=business_id,
                name=name,
                capacity=capacity,
                min_party_size=min_party_size,
                max_party_size=max_party_size,
                resource_type=resource_type,
                section=section,
                is_active=is_active,
                metadata_json=metadata_json,
            )
            return res.to_dict()

    def update_resource(
        self,
        business_id: str,
        resource_id: str,
        updates: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Update an existing resource."""
        with session_scope(self.session_factory) as session:
            res_repo = ResourceRepository(session)
            res = res_repo.update_resource(business_id, resource_id, updates)
            return res.to_dict() if res else None

    def delete_resource(self, business_id: str, resource_id: str) -> bool:
        """Delete a resource."""
        with session_scope(self.session_factory) as session:
            res_repo = ResourceRepository(session)
            return res_repo.delete_resource(business_id, resource_id)

    def find_available_resources(
        self,
        business_id: str,
        start_time: Any,
        end_time: Any,
        party_size: int,
        resource_type: str = "table",
        section: Optional[str] = None,
        exclude_reservation_id: Optional[str] = None,
        buffer_minutes: int = 0,
    ) -> List[Dict[str, Any]]:
        """Query currently available tables/rooms for the given time slot."""
        with session_scope(self.session_factory) as session:
            res_repo = ReservationRepository(session)
            available = res_repo.find_available_resources(
                business_id=business_id,
                start_time=start_time,
                end_time=end_time,
                party_size=party_size,
                resource_type=resource_type,
                section=section,
                exclude_reservation_id=exclude_reservation_id,
                buffer_minutes=buffer_minutes,
            )
            return [r.to_dict() for r in available]

    def create_reservation_atomic(
        self,
        business_id: str,
        customer_name: str,
        customer_phone: str,
        party_size: int,
        start_time: Any,
        end_time: Any,
        resource_id: Optional[str] = None,
        resource_type: str = "table",
        section: Optional[str] = None,
        special_requests: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        status: str = "confirmed",
        metadata: Optional[Dict[str, Any]] = None,
        buffer_minutes: int = 0,
    ) -> Dict[str, Any]:
        """Atomically create a reservation with double-booking prevention and idempotency."""
        with session_scope(self.session_factory) as session:
            res_repo = ReservationRepository(session)
            booking = res_repo.create_reservation_atomic(
                business_id=business_id,
                customer_name=customer_name,
                customer_phone=customer_phone,
                party_size=party_size,
                start_time=start_time,
                end_time=end_time,
                resource_id=resource_id,
                resource_type=resource_type,
                section=section,
                special_requests=special_requests,
                idempotency_key=idempotency_key,
                status=status,
                metadata=metadata,
                buffer_minutes=buffer_minutes,
            )
            return booking.to_dict()

    def create_hold_atomic(
        self,
        business_id: str,
        customer_name: str,
        customer_phone: str,
        party_size: int,
        start_time: Any,
        end_time: Any,
        hold_minutes: int = 15,
        resource_id: Optional[str] = None,
        resource_type: str = "table",
        section: Optional[str] = None,
        special_requests: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        buffer_minutes: int = 0,
    ) -> Dict[str, Any]:
        """Place an expiring temporary hold on a resource."""
        with session_scope(self.session_factory) as session:
            res_repo = ReservationRepository(session)
            hold = res_repo.create_hold_atomic(
                business_id=business_id,
                customer_name=customer_name,
                customer_phone=customer_phone,
                party_size=party_size,
                start_time=start_time,
                end_time=end_time,
                hold_minutes=hold_minutes,
                resource_id=resource_id,
                resource_type=resource_type,
                section=section,
                special_requests=special_requests,
                idempotency_key=idempotency_key,
                metadata=metadata,
                buffer_minutes=buffer_minutes,
            )
            return hold.to_dict()

    def confirm_hold_atomic(
        self,
        business_id: str,
        reservation_id: str,
        customer_phone: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Convert an active hold into a confirmed reservation."""
        with session_scope(self.session_factory) as session:
            res_repo = ReservationRepository(session)
            booking = res_repo.confirm_hold_atomic(
                business_id=business_id,
                reservation_id=reservation_id,
                customer_phone=customer_phone,
            )
            return booking.to_dict()

    def reschedule_reservation_atomic(
        self,
        business_id: str,
        reservation_id: str,
        new_start_time: Any,
        new_end_time: Any,
        new_resource_id: Optional[str] = None,
        customer_phone: Optional[str] = None,
        party_size: Optional[int] = None,
        buffer_minutes: int = 0,
    ) -> Dict[str, Any]:
        """Atomically reschedule an existing reservation."""
        with session_scope(self.session_factory) as session:
            res_repo = ReservationRepository(session)
            booking = res_repo.reschedule_reservation_atomic(
                business_id=business_id,
                reservation_id=reservation_id,
                new_start_time=new_start_time,
                new_end_time=new_end_time,
                new_resource_id=new_resource_id,
                customer_phone=customer_phone,
                party_size=party_size,
                buffer_minutes=buffer_minutes,
            )
            return booking.to_dict()

    def get_reservation(self, business_id: str, reservation_id: str) -> Optional[Dict[str, Any]]:
        """Fetch reservation details."""
        with session_scope(self.session_factory) as session:
            res_repo = ReservationRepository(session)
            res = res_repo.get_reservation(reservation_id, business_id=business_id)
            return res.to_dict() if res else None

    def cancel_reservation(
        self,
        business_id: str,
        reservation_id: str,
        customer_phone: Optional[str] = None,
        cancellation_deadline_hours: Optional[int] = None,
        strict_cancellation: bool = False,
        reason: Optional[str] = None,
    ) -> bool:
        """Cancel a reservation with optional cancellation policy check."""
        with session_scope(self.session_factory) as session:
            res_repo = ReservationRepository(session)
            return res_repo.cancel_reservation(
                business_id,
                reservation_id,
                customer_phone=customer_phone,
                cancellation_deadline_hours=cancellation_deadline_hours,
                strict_cancellation=strict_cancellation,
                reason=reason,
            )

    def list_reservations(
        self,
        business_id: str,
        start_date: Optional[Any] = None,
        end_date: Optional[Any] = None,
        status: Optional[str] = None,
        resource_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List reservations for a business."""
        with session_scope(self.session_factory) as session:
            res_repo = ReservationRepository(session)
            bookings = res_repo.list_reservations(
                business_id,
                start_date=start_date,
                end_date=end_date,
                status=status,
                resource_id=resource_id,
            )
            return [b.to_dict() for b in bookings]

    def add_to_waitlist(
        self,
        business_id: str,
        customer_name: str,
        customer_phone: str,
        requested_time: Any,
        party_size: int = 2,
        resource_type: str = "table",
        section: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add customer to waiting list queue."""
        with session_scope(self.session_factory) as session:
            res_repo = ReservationRepository(session)
            entry = res_repo.add_to_waitlist(
                business_id=business_id,
                customer_name=customer_name,
                customer_phone=customer_phone,
                requested_time=requested_time,
                party_size=party_size,
                resource_type=resource_type,
                section=section,
                notes=notes,
            )
            return entry.to_dict()

    def get_waitlist(
        self,
        business_id: str,
        resource_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List active waiting list queue entries."""
        with session_scope(self.session_factory) as session:
            res_repo = ReservationRepository(session)
            entries = res_repo.get_waitlist(business_id=business_id, resource_type=resource_type)
            return [e.to_dict() for e in entries]

    def create_tool_demand(self, business_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Record a custom tool/feature request demanded by a business tenant."""
        with session_scope(self.session_factory) as session:
            repo = ToolDemandRepository(session)
            demand = repo.create(business_id, data)
            return demand.to_dict()

    def list_tool_demands(self, business_id: str) -> List[Dict[str, Any]]:
        """List all custom tool demands requested by a business tenant."""
        with session_scope(self.session_factory) as session:
            repo = ToolDemandRepository(session)
            return repo.list_dicts_for_business(business_id)

    def list_all_tool_demands(self) -> List[Dict[str, Any]]:
        """List all custom tool demands across all businesses."""
        with session_scope(self.session_factory) as session:
            repo = ToolDemandRepository(session)
            return repo.list_all_demands()

    def update_tool_demand_status(self, demand_id: str, new_status: str) -> Optional[Dict[str, Any]]:
        """Update lifecycle status of a tool demand."""
        with session_scope(self.session_factory) as session:
            repo = ToolDemandRepository(session)
            return repo.update_status(demand_id, new_status)

    def get_call_history_and_count(
        self,
        business_id: str,
        outcome_filter: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[List[Dict[str, Any]], int]:
        """Retrieve audited call history records and total count with in-memory caching."""
        cache_key = f"{business_id}:{outcome_filter}:{limit}:{offset}"
        cached = self._calls_cache.get(cache_key)
        if cached:
            ts, val = cached
            if (time.time() - ts) < 60.0:
                return val

        with session_scope(self.session_factory) as session:
            call_repo = CallRepository(session)
            total = call_repo.count_for_business(business_id=business_id, outcome_filter=outcome_filter)
            calls = call_repo.list_dicts_for_business(
                business_id=business_id,
                outcome_filter=outcome_filter,
                limit=limit,
                offset=offset,
            )
            res = (calls, total)
            self._calls_cache[cache_key] = (time.time(), res)
            return res

    def get_call_history(
        self,
        business_id: str,
        outcome_filter: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Retrieve audited call history records for a tenant with SQL offset pagination."""
        with session_scope(self.session_factory) as session:
            call_repo = CallRepository(session)
            return call_repo.list_dicts_for_business(
                business_id=business_id,
                outcome_filter=outcome_filter,
                limit=limit,
                offset=offset,
            )

    def get_call_count(
        self,
        business_id: str,
        outcome_filter: Optional[str] = None,
    ) -> int:
        """Count total audited call history records for a tenant."""
        with session_scope(self.session_factory) as session:
            call_repo = CallRepository(session)
            return call_repo.count_for_business(
                business_id=business_id,
                outcome_filter=outcome_filter,
            )

    def log_call(
        self,
        business_id: str,
        caller_number: str,
        duration_seconds: int,
        outcome: str,
        summary: str,
        tools_used: Optional[List[str]] = None,
        duration_formatted: Optional[str] = None,
        is_simulated: bool = True,
        call_id: Optional[str] = None,
        transcript: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Record an inbound call audit log."""
        with session_scope(self.session_factory) as session:
            call_repo = CallRepository(session)
            call = call_repo.log_call(
                business_id=business_id,
                caller_number=caller_number,
                duration_seconds=duration_seconds,
                duration_formatted=duration_formatted,
                outcome=outcome,
                summary=summary,
                tools_used=tools_used,
                is_simulated=is_simulated,
                call_id=call_id,
                transcript=transcript,
            )
            # Invalidate calls cache for real-time visibility
            keys_to_del = [k for k in self._calls_cache if k.startswith(f"{business_id}:")]
            for k in keys_to_del:
                self._calls_cache.pop(k, None)
            return call.to_dict()

    def get_conversation_messages(
        self,
        business_id: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Retrieve conversation history for the playground."""
        with session_scope(self.session_factory) as session:
            conv_repo = ConversationRepository(session)
            return conv_repo.list_dicts(business_id, limit=limit)

    def add_conversation_message(
        self,
        business_id: str,
        role: str,
        content: str,
        is_simulated: bool = True,
    ) -> Dict[str, Any]:
        """Persist a conversation message turn."""
        with session_scope(self.session_factory) as session:
            conv_repo = ConversationRepository(session)
            msg = conv_repo.add_message(
                business_id=business_id,
                role=role,
                content=content,
                is_simulated=is_simulated,
            )
            return msg.to_dict()

    def reset_conversation_messages(self, business_id: str) -> None:
        """Clear conversation history and restore default greeting."""
        with session_scope(self.session_factory) as session:
            conv_repo = ConversationRepository(session)
            conv_repo.clear_for_business(business_id)

            # Insert initial business greeting
            biz_repo = BusinessRepository(session)
            biz = biz_repo.get(business_id)
            if biz and biz.greeting_message:
                conv_repo.add_message(
                    business_id=business_id,
                    role="assistant",
                    content=biz.greeting_message,
                    is_simulated=True,
                )

    def get_pending_action(self, business_id: str) -> Optional[Dict[str, Any]]:
        """Fetch active pending confirmation action for a business."""
        with session_scope(self.session_factory) as session:
            pending_repo = PendingActionRepository(session)
            action = pending_repo.get_latest_pending(business_id)
            return action.to_dict() if action else None

    def get_pending_action_by_id(self, business_id: str, action_id: str) -> Optional[Dict[str, Any]]:
        """Fetch pending action by exact action_id and verify business ownership."""
        with session_scope(self.session_factory) as session:
            pending_repo = PendingActionRepository(session)
            action = pending_repo.get(action_id)
            if not action or action.business_id != business_id:
                return None
            return action.to_dict()

    def save_pending_action(
        self,
        business_id: str,
        pending_action: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Persist a newly intercepted pending action awaiting confirmation."""
        with session_scope(self.session_factory) as session:
            pending_repo = PendingActionRepository(session)
            action = pending_repo.create_action(
                business_id=business_id,
                action_id=pending_action["action_id"],
                action_type=pending_action.get("tool_id", "unknown"),
                tool_name=pending_action.get("tool_name", "Unknown Action"),
                arguments=pending_action.get("arguments", {}),
                summary=pending_action.get("summary", ""),
            )
            return action.to_dict()

    def transition_pending_action(
        self,
        business_id: str,
        action_id: str,
        new_status: str,
        execution_reference: Optional[str] = None,
    ) -> bool:
        """Update status of a pending action to executed or cancelled."""
        with session_scope(self.session_factory) as session:
            pending_repo = PendingActionRepository(session)
            return pending_repo.transition_status(
                business_id=business_id,
                action_id=action_id,
                new_status=new_status,
                execution_reference=execution_reference,
            )

    def set_pending_action_reference(
        self,
        business_id: str,
        action_id: str,
        execution_reference: str,
    ) -> bool:
        """Record external execution reference on an executed action record."""
        with session_scope(self.session_factory) as session:
            pending_repo = PendingActionRepository(session)
            return pending_repo.set_execution_reference(
                business_id=business_id,
                action_id=action_id,
                execution_reference=execution_reference,
            )

    def clear_pending_actions(self, business_id: str) -> int:
        """Cancel all pending confirmation actions for a tenant."""
        with session_scope(self.session_factory) as session:
            pending_repo = PendingActionRepository(session)
            return pending_repo.cancel_all_pending(business_id)

    def get_business_by_phone_number(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """Lookup business by phone number with E.164 normalization."""
        with session_scope(self.session_factory) as session:
            biz_repo = BusinessRepository(session)
            biz = biz_repo.get_by_phone_number(phone_number)
            return biz.to_dict() if biz else None

    def create_voice_session(
        self,
        session_id: str,
        business_id: str,
        provider_call_id: str,
        provider_name: str,
        called_number: str,
        caller_number: Optional[str] = None,
        correlation_id: Optional[str] = None,
        session_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create and persist a new voice session."""
        with session_scope(self.session_factory) as session:
            repo = VoiceSessionRepository(session)
            voice_session = repo.create_session(
                session_id=session_id,
                business_id=business_id,
                provider_call_id=provider_call_id,
                provider_name=provider_name,
                called_number=called_number,
                caller_number=caller_number,
                correlation_id=correlation_id,
                session_metadata=session_metadata,
            )
            return voice_session.to_dict()

    def get_voice_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve voice session by session ID."""
        with session_scope(self.session_factory) as session:
            repo = VoiceSessionRepository(session)
            s = repo.get(session_id)
            return s.to_dict() if s else None

    def get_voice_session_by_provider_call_id(
        self,
        provider_call_id: str,
        provider_name: str = "exotel",
    ) -> Optional[Dict[str, Any]]:
        """Retrieve voice session by external provider call ID."""
        with session_scope(self.session_factory) as session:
            repo = VoiceSessionRepository(session)
            s = repo.get_by_provider_call_id(provider_call_id, provider_name=provider_name)
            return s.to_dict() if s else None

    def get_voice_session_by_correlation_id(
        self,
        correlation_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve voice session by correlation ID (e.g. stream_sid)."""
        with session_scope(self.session_factory) as session:
            repo = VoiceSessionRepository(session)
            s = repo.get_by_correlation_id(correlation_id)
            return s.to_dict() if s else None

    def update_voice_session_metadata(
        self,
        session_id: str,
        metadata_updates: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Update session_metadata for a voice session."""
        with session_scope(self.session_factory) as session:
            repo = VoiceSessionRepository(session)
            s = repo.update_metadata(session_id, metadata_updates)
            return s.to_dict() if s else None

    def transition_voice_session_status(
        self,
        session_id: str,
        new_status: str,
        ended_at: Optional[Any] = None,
        call_record_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Transition voice session status and optional completion data."""
        with session_scope(self.session_factory) as session:
            repo = VoiceSessionRepository(session)
            s = repo.transition_status(
                session_id=session_id,
                new_status=new_status,
                ended_at=ended_at,
                call_record_id=call_record_id,
            )
            return s.to_dict() if s else None

    def update_voice_session_last_turn(
        self,
        session_id: str,
        timestamp: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update last_turn_at timestamp on a voice session."""
        with session_scope(self.session_factory) as session:
            repo = VoiceSessionRepository(session)
            s = repo.update_last_turn(session_id=session_id, timestamp=timestamp)
            return s.to_dict() if s else None

    def list_active_voice_sessions(self, business_id: str) -> List[Dict[str, Any]]:
        """Retrieve all active voice sessions for a tenant."""
        with session_scope(self.session_factory) as session:
            repo = VoiceSessionRepository(session)
            return [s.to_dict() for s in repo.list_active_for_business(business_id)]

    def list_voice_sessions(self, business_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent voice sessions for a tenant."""
        with session_scope(self.session_factory) as session:
            repo = VoiceSessionRepository(session)
            return [s.to_dict() for s in repo.list_for_business(business_id, limit=limit)]

    def add_session_message(
        self,
        business_id: str,
        session_id: str,
        role: str,
        content: str,
        is_simulated: bool = True,
    ) -> Dict[str, Any]:
        """Persist a conversation message scoped to a voice session."""
        with session_scope(self.session_factory) as session:
            conv_repo = ConversationRepository(session)
            msg = conv_repo.add_message(
                business_id=business_id,
                role=role,
                content=content,
                is_simulated=is_simulated,
                session_id=session_id,
            )
            return msg.to_dict()

    def get_session_messages(
        self,
        business_id: str,
        session_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Retrieve message history scoped to a voice session."""
        with session_scope(self.session_factory) as session:
            conv_repo = ConversationRepository(session)
            return conv_repo.list_session_dicts(business_id=business_id, session_id=session_id, limit=limit)



_DEFAULT_SERVICE: Optional[DatabaseService] = None


def get_database_service() -> DatabaseService:
    """Retrieve or initialize singleton DatabaseService."""
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        _DEFAULT_SERVICE = DatabaseService()
    return _DEFAULT_SERVICE
