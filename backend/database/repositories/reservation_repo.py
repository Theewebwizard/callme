"""
Repository for transactional reservations, appointments, and resource allocations.
Enforces double-booking prevention, concurrency safety, holding periods,
rescheduling, waiting lists, cancellation policies, and idempotency across business domains
(dining tables, hotel rooms, clinic rooms/practitioners, and service staff).
"""

from typing import List, Optional, Dict, Any, Union
from datetime import datetime, timezone, timedelta
import uuid
import logging
from sqlalchemy import select, and_, or_, not_, desc, func
from sqlalchemy.orm import Session

from backend.database.models import Reservation, ReservableResource, utcnow
from backend.database.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ReservationConflictError(Exception):
    """Raised when a requested reservation time slot overlaps with an existing booking or hold."""
    pass


class CancellationPolicyViolation(Exception):
    """Raised when a cancellation request violates the business's cancellation deadline policy."""
    pass


class ReservationRepository(BaseRepository):
    """Repository handling transactional reservation operations and conflict prevention."""

    def find_available_resources(
        self,
        business_id: str,
        start_time: datetime,
        end_time: datetime,
        party_size: int,
        resource_type: str = "table",
        section: Optional[str] = None,
        exclude_reservation_id: Optional[str] = None,
        buffer_minutes: int = 0,
    ) -> List[ReservableResource]:
        """
        Query all active resources that accommodate the party size and have NO
        conflicting reservations or active holds during the requested [start_time, end_time) window.
        Buffer minutes expand the conflict checking window.
        """
        # Ensure UTC timezone awareness
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        # Apply buffer minutes to effective window
        effective_start = start_time - timedelta(minutes=buffer_minutes)
        effective_end = end_time + timedelta(minutes=buffer_minutes)

        # 1. Candidate resources matching business, type, active status, capacity, and section
        candidate_stmt = (
            select(ReservableResource)
            .where(
                ReservableResource.business_id == business_id,
                ReservableResource.resource_type == resource_type,
                ReservableResource.is_active == True,
                ReservableResource.min_party_size <= party_size,
                ReservableResource.max_party_size >= party_size,
            )
        )
        if section:
            candidate_stmt = candidate_stmt.where(ReservableResource.section == section)

        candidate_stmt = candidate_stmt.order_by(ReservableResource.capacity.asc())
        candidates = list(self.session.scalars(candidate_stmt).all())
        if not candidates:
            return []

        candidate_ids = [c.id for c in candidates]
        now = utcnow()

        # 2. Conflicting reservations overlapping with effective window
        # Active holds are included if hold_expires_at is null or in the future
        active_hold_cond = and_(
            Reservation.status == "hold",
            or_(Reservation.hold_expires_at.is_(None), Reservation.hold_expires_at > now),
        )
        active_status_cond = or_(
            Reservation.status.in_(["confirmed", "pending_confirmation"]),
            active_hold_cond,
        )

        conflict_cond = and_(
            Reservation.business_id == business_id,
            Reservation.resource_id.in_(candidate_ids),
            active_status_cond,
            Reservation.start_time < effective_end,
            Reservation.end_time > effective_start,
        )
        if exclude_reservation_id:
            conflict_cond = and_(conflict_cond, Reservation.id != exclude_reservation_id)

        conflict_stmt = select(Reservation.resource_id).where(conflict_cond)
        booked_resource_ids = set(self.session.scalars(conflict_stmt).all())

        # 3. Filter out booked resources
        available = [c for c in candidates if c.id not in booked_resource_ids]
        return available

    def get_reservation_by_idempotency_key(
        self,
        business_id: str,
        idempotency_key: str,
    ) -> Optional[Reservation]:
        """Fetch existing reservation by idempotency key to prevent duplicate booking operations."""
        if not idempotency_key:
            return None
        stmt = (
            select(Reservation)
            .where(
                Reservation.business_id == business_id,
                Reservation.idempotency_key == idempotency_key,
            )
        )
        return self.session.scalar(stmt)

    def get_reservation(
        self,
        reservation_id: str,
        business_id: Optional[str] = None,
    ) -> Optional[Reservation]:
        """Fetch reservation by ID, optionally verifying tenant ownership."""
        stmt = select(Reservation).where(Reservation.id == reservation_id)
        if business_id:
            stmt = stmt.where(Reservation.business_id == business_id)
        return self.session.scalar(stmt)

    def create_reservation_atomic(
        self,
        business_id: str,
        customer_name: str,
        customer_phone: str,
        party_size: int,
        start_time: datetime,
        end_time: datetime,
        resource_id: Optional[str] = None,
        resource_type: str = "table",
        section: Optional[str] = None,
        special_requests: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        status: str = "confirmed",
        metadata: Optional[Dict[str, Any]] = None,
        buffer_minutes: int = 0,
    ) -> Reservation:
        """
        Atomically reserve a resource for a customer.
        Rechecks availability within the transaction to prevent concurrent double-booking.
        Handles idempotent retries and domain prefixes.
        """
        # Ensure UTC timezone awareness
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        # 1. Idempotency check: if client/LLM retried with same key, return existing record
        if idempotency_key:
            existing = self.get_reservation_by_idempotency_key(business_id, idempotency_key)
            if existing:
                logger.info(
                    "Idempotent reservation replay detected: %s (Key: %s)",
                    existing.id,
                    idempotency_key,
                )
                return existing

        now = utcnow()
        effective_start = start_time - timedelta(minutes=buffer_minutes)
        effective_end = end_time + timedelta(minutes=buffer_minutes)

        # 2. Select matching resource and verify no conflict
        target_resource: Optional[ReservableResource] = None
        if resource_id:
            # Caller requested a specific resource: check that it is valid, active, and available
            res = self.session.get(ReservableResource, resource_id)
            if not res or res.business_id != business_id or not res.is_active:
                raise ReservationConflictError(f"Resource '{resource_id}' is invalid or inactive.")

            active_hold_cond = and_(
                Reservation.status == "hold",
                or_(Reservation.hold_expires_at.is_(None), Reservation.hold_expires_at > now),
            )
            active_status_cond = or_(
                Reservation.status.in_(["confirmed", "pending_confirmation"]),
                active_hold_cond,
            )

            conflict_stmt = (
                select(Reservation.id)
                .where(
                    Reservation.resource_id == resource_id,
                    active_status_cond,
                    Reservation.start_time < effective_end,
                    Reservation.end_time > effective_start,
                )
            )
            if self.session.scalar(conflict_stmt) is not None:
                raise ReservationConflictError(f"Resource '{res.name}' is already reserved during this time slot.")
            target_resource = res
        else:
            # Find any available resource matching capacity and section
            available = self.find_available_resources(
                business_id=business_id,
                start_time=start_time,
                end_time=end_time,
                party_size=party_size,
                resource_type=resource_type,
                section=section,
                buffer_minutes=buffer_minutes,
            )
            if not available:
                raise ReservationConflictError(
                    f"No available {resource_type}s found for party size {party_size} "
                    f"between {start_time.strftime('%H:%M')} and {end_time.strftime('%H:%M')}."
                )
            target_resource = available[0]

        # 3. Domain-specific ID prefix
        prefix_map = {
            "table": "TB-",
            "room": "HTL-",
            "clinic_room": "CLN-",
            "practitioner": "APT-",
            "service_staff": "SRV-",
        }
        prefix = prefix_map.get(resource_type, "BK-")
        booking_id = f"{prefix}{uuid.uuid4().hex[:8].upper()}"

        meta = dict(metadata or {})
        meta["resource_type"] = resource_type
        meta["resource_name"] = target_resource.name
        if section:
            meta["section"] = section

        reservation = Reservation(
            id=booking_id,
            business_id=business_id,
            resource_id=target_resource.id,
            customer_name=customer_name.strip(),
            customer_phone=customer_phone.strip(),
            party_size=party_size,
            start_time=start_time,
            end_time=end_time,
            status=status,
            metadata_json=meta,
            special_requests=special_requests.strip() if special_requests else None,
            idempotency_key=idempotency_key,
            created_at=now,
            updated_at=now,
        )
        self.session.add(reservation)
        self.session.flush()

        logger.info(
            "Created reservation %s for %s (%s) on resource %s (%s - %s) status=%s",
            booking_id,
            customer_name,
            customer_phone,
            target_resource.name,
            start_time.isoformat(),
            end_time.isoformat(),
            status,
        )
        return reservation

    def create_hold_atomic(
        self,
        business_id: str,
        customer_name: str,
        customer_phone: str,
        party_size: int,
        start_time: datetime,
        end_time: datetime,
        hold_minutes: int = 15,
        resource_id: Optional[str] = None,
        resource_type: str = "table",
        section: Optional[str] = None,
        special_requests: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        buffer_minutes: int = 0,
    ) -> Reservation:
        """
        Atomically place a temporary hold on a resource with an expiration timestamp.
        Slots held by active holds are protected from other bookings until expiration.
        """
        now = utcnow()
        hold_expires_at = now + timedelta(minutes=hold_minutes)

        meta = dict(metadata or {})
        meta["hold_minutes"] = hold_minutes
        meta["placed_at"] = now.isoformat()

        res = self.create_reservation_atomic(
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
            status="hold",
            metadata=meta,
            buffer_minutes=buffer_minutes,
        )
        res.hold_expires_at = hold_expires_at
        self.session.flush()
        return res

    def confirm_hold_atomic(
        self,
        business_id: str,
        reservation_id: str,
        customer_phone: Optional[str] = None,
    ) -> Reservation:
        """
        Convert an active hold into a confirmed reservation.
        Rejects if the hold has already expired.
        """
        res = self.get_reservation(reservation_id, business_id=business_id)
        if not res:
            raise ReservationConflictError(f"Reservation hold '{reservation_id}' not found.")

        if res.status != "hold":
            if res.status == "confirmed":
                return res
            raise ReservationConflictError(f"Booking '{reservation_id}' is not in hold state (status: {res.status}).")

        now = utcnow()
        hold_exp = res.hold_expires_at
        if hold_exp and hold_exp.tzinfo is None:
            hold_exp = hold_exp.replace(tzinfo=timezone.utc)
        if hold_exp and hold_exp <= now:
            res.status = "cancelled"
            res.updated_at = now
            self.session.flush()
            raise ReservationConflictError("Booking hold has expired and inventory was released.")

        if customer_phone:
            clean_in = "".join(filter(str.isdigit, customer_phone))
            clean_rec = "".join(filter(str.isdigit, res.customer_phone))
            if clean_in and clean_rec and not (clean_in in clean_rec or clean_rec in clean_in):
                raise ReservationConflictError("Customer phone does not match hold record.")

        res.status = "confirmed"
        res.hold_expires_at = None
        res.updated_at = now
        self.session.flush()
        return res

    def reschedule_reservation_atomic(
        self,
        business_id: str,
        reservation_id: str,
        new_start_time: datetime,
        new_end_time: datetime,
        new_resource_id: Optional[str] = None,
        customer_phone: Optional[str] = None,
        party_size: Optional[int] = None,
        buffer_minutes: int = 0,
    ) -> Reservation:
        """
        Atomically reschedule an existing reservation to a new time slot/resource.
        Verifies availability in the new slot excluding the booking's own current slot.
        Maintains audit history of the change.
        """
        res = self.get_reservation(reservation_id, business_id=business_id)
        if not res:
            raise ReservationConflictError(f"Reservation '{reservation_id}' not found.")

        if res.status in ("cancelled", "completed"):
            raise ReservationConflictError(f"Cannot reschedule a reservation with status '{res.status}'.")

        if customer_phone:
            clean_in = "".join(filter(str.isdigit, customer_phone))
            clean_rec = "".join(filter(str.isdigit, res.customer_phone))
            if clean_in and clean_rec and not (clean_in in clean_rec or clean_rec in clean_in):
                raise ReservationConflictError("Customer phone verification failed.")

        if new_start_time.tzinfo is None:
            new_start_time = new_start_time.replace(tzinfo=timezone.utc)
        if new_end_time.tzinfo is None:
            new_end_time = new_end_time.replace(tzinfo=timezone.utc)

        target_size = party_size or res.party_size
        target_res_id = new_resource_id or res.resource_id
        target_resource = self.session.get(ReservableResource, target_res_id) if target_res_id else None

        if not target_resource or target_resource.business_id != business_id or not target_resource.is_active:
            # Find an available alternative of same type
            res_type = target_resource.resource_type if target_resource else "table"
            available = self.find_available_resources(
                business_id=business_id,
                start_time=new_start_time,
                end_time=new_end_time,
                party_size=target_size,
                resource_type=res_type,
                exclude_reservation_id=reservation_id,
                buffer_minutes=buffer_minutes,
            )
            if not available:
                raise ReservationConflictError("No available resources for the rescheduled time slot.")
            target_resource = available[0]
        else:
            # Check conflict for specific resource excluding this reservation
            now = utcnow()
            effective_start = new_start_time - timedelta(minutes=buffer_minutes)
            effective_end = new_end_time + timedelta(minutes=buffer_minutes)

            active_hold_cond = and_(
                Reservation.status == "hold",
                or_(Reservation.hold_expires_at.is_(None), Reservation.hold_expires_at > now),
            )
            active_status_cond = or_(
                Reservation.status.in_(["confirmed", "pending_confirmation"]),
                active_hold_cond,
            )

            conflict_stmt = (
                select(Reservation.id)
                .where(
                    Reservation.resource_id == target_resource.id,
                    Reservation.id != reservation_id,
                    active_status_cond,
                    Reservation.start_time < effective_end,
                    Reservation.end_time > effective_start,
                )
            )
            if self.session.scalar(conflict_stmt) is not None:
                raise ReservationConflictError(f"Resource '{target_resource.name}' is unavailable during the requested reschedule window.")

        # Record audit change
        meta = dict(res.metadata_json or {})
        prev_start = res.start_time
        if prev_start and prev_start.tzinfo is None:
            prev_start = prev_start.replace(tzinfo=timezone.utc)
        prev_end = res.end_time
        if prev_end and prev_end.tzinfo is None:
            prev_end = prev_end.replace(tzinfo=timezone.utc)

        history = meta.get("reschedule_history", [])
        history.append({
            "previous_start": prev_start.isoformat() if prev_start else None,
            "previous_end": prev_end.isoformat() if prev_end else None,
            "previous_resource_id": res.resource_id,
            "rescheduled_at": utcnow().isoformat(),
        })
        meta["reschedule_history"] = history

        res.rescheduled_from_id = res.id
        res.start_time = new_start_time
        res.end_time = new_end_time
        res.resource_id = target_resource.id
        res.party_size = target_size
        res.metadata_json = meta
        res.updated_at = utcnow()
        self.session.flush()

        logger.info("Rescheduled reservation %s to %s - %s", reservation_id, new_start_time, new_end_time)
        return res

    def cancel_reservation(
        self,
        business_id: str,
        reservation_id: str,
        customer_phone: Optional[str] = None,
        cancellation_deadline_hours: Optional[int] = None,
        strict_cancellation: bool = False,
        reason: Optional[str] = None,
    ) -> bool:
        """
        Cancel an existing reservation.
        Enforces cancellation deadline policy if specified.
        """
        reservation = self.get_reservation(reservation_id, business_id=business_id)
        if not reservation:
            return False

        if customer_phone:
            clean_input = "".join(filter(str.isdigit, customer_phone))
            clean_res = "".join(filter(str.isdigit, reservation.customer_phone))
            if clean_input and clean_res and not (clean_input in clean_res or clean_res in clean_input):
                logger.warning("Cancellation phone mismatch: %s vs %s", customer_phone, reservation.customer_phone)
                return False

        now = utcnow()
        # Enforce cancellation policy if requested
        if cancellation_deadline_hours is not None and cancellation_deadline_hours > 0:
            if reservation.start_time:
                res_start = reservation.start_time
                if res_start.tzinfo is None:
                    res_start = res_start.replace(tzinfo=timezone.utc)
                time_until_start = (res_start - now).total_seconds() / 3600.0
                if time_until_start < cancellation_deadline_hours:
                    if strict_cancellation:
                        raise CancellationPolicyViolation(
                            f"Cancellation deadline of {cancellation_deadline_hours} hours prior to start has passed "
                            f"(remaining: {time_until_start:.1f} hours)."
                        )
                    else:
                        meta = dict(reservation.metadata_json or {})
                        meta["late_cancellation"] = True
                        reservation.metadata_json = meta

        meta = dict(reservation.metadata_json or {})
        if reason:
            meta["cancellation_reason"] = reason
        meta["cancelled_at"] = now.isoformat()

        reservation.status = "cancelled"
        reservation.metadata_json = meta
        reservation.updated_at = now
        self.session.flush()
        return True

    def list_reservations(
        self,
        business_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        status: Optional[str] = None,
        resource_id: Optional[str] = None,
    ) -> List[Reservation]:
        """List reservations for business with optional date, status, and resource filters."""
        stmt = (
            select(Reservation)
            .where(Reservation.business_id == business_id)
            .order_by(Reservation.start_time.asc())
        )
        if start_date:
            stmt = stmt.where(Reservation.start_time >= start_date)
        if end_date:
            stmt = stmt.where(Reservation.start_time <= end_date)
        if status:
            stmt = stmt.where(Reservation.status == status)
        if resource_id:
            stmt = stmt.where(Reservation.resource_id == resource_id)

        return list(self.session.scalars(stmt).all())

    # ---------------------------------------------------------------------------
    # Waiting List Support
    # ---------------------------------------------------------------------------

    def add_to_waitlist(
        self,
        business_id: str,
        customer_name: str,
        customer_phone: str,
        requested_time: datetime,
        party_size: int = 2,
        resource_type: str = "table",
        section: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Reservation:
        """
        Add a customer to the waiting list when resources are fully booked.
        Maintains customer reference and queue order.
        """
        if requested_time.tzinfo is None:
            requested_time = requested_time.replace(tzinfo=timezone.utc)

        # Calculate current queue depth for this business
        q_count = self.session.scalar(
            select(func.count(Reservation.id))
            .where(
                Reservation.business_id == business_id,
                Reservation.status == "waitlisted",
            )
        ) or 0

        now = utcnow()
        booking_id = f"WL-{uuid.uuid4().hex[:8].upper()}"
        meta = {
            "waitlist_position": q_count + 1,
            "resource_type": resource_type,
            "section": section,
            "notes": notes,
        }

        entry = Reservation(
            id=booking_id,
            business_id=business_id,
            resource_id=None,
            customer_name=customer_name.strip(),
            customer_phone=customer_phone.strip(),
            party_size=party_size,
            start_time=requested_time,
            end_time=requested_time + timedelta(minutes=60),
            status="waitlisted",
            metadata_json=meta,
            special_requests=notes,
            created_at=now,
            updated_at=now,
        )
        self.session.add(entry)
        self.session.flush()
        return entry

    def get_waitlist(
        self,
        business_id: str,
        resource_type: Optional[str] = None,
    ) -> List[Reservation]:
        """Fetch active waitlist entries ordered chronologically."""
        stmt = (
            select(Reservation)
            .where(
                Reservation.business_id == business_id,
                Reservation.status == "waitlisted",
            )
            .order_by(Reservation.created_at.asc())
        )
        entries = list(self.session.scalars(stmt).all())
        if resource_type:
            entries = [
                e for e in entries
                if (e.metadata_json or {}).get("resource_type") == resource_type
            ]
        return entries
