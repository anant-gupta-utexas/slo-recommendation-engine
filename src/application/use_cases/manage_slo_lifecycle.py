"""Use case for FR-5: SLO Recommendation Lifecycle (accept/modify/reject).

Orchestrates the accept/modify/reject workflow for SLO recommendations,
storing active SLOs and maintaining an audit trail.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from src.application.dtos.slo_lifecycle_dto import (
    ActiveSloResponse,
    AuditEntryResponse,
    AuditHistoryResponse,
    ManageSloRequest,
    ManageSloResponse,
)
from src.domain.entities.active_slo import ActiveSlo, SloAction, SloAuditEntry, SloSource
from src.infrastructure.stores import in_memory_slo_store as store

logger = logging.getLogger(__name__)


class ManageSloLifecycleUseCase:
    """Manage the lifecycle of SLO recommendations.

    Supports accept, modify, and reject actions. Stores active SLOs
    in-memory and maintains an append-only audit trail.
    """

    async def execute(self, request: ManageSloRequest) -> ManageSloResponse:
        """Execute the SLO lifecycle action.

        Args:
            request: The lifecycle action request

        Returns:
            ManageSloResponse with the result

        Raises:
            ValueError: If action is invalid or required fields are missing
        """
        action = request.action.lower()
        if action not in ("accept", "modify", "reject"):
            raise ValueError(f"Invalid action: {action}. Must be accept, modify, or reject.")

        if action == "accept":
            return await self._handle_accept(request)
        elif action == "modify":
            return await self._handle_modify(request)
        else:
            return await self._handle_reject(request)

    async def _handle_accept(self, request: ManageSloRequest) -> ManageSloResponse:
        """Accept a recommendation as-is at the selected tier."""
        previous_slo = store.get_active_slo(request.service_id)
        previous_snapshot = self._snapshot_slo(previous_slo) if previous_slo else None

        # For demo: derive targets from tier selection
        targets = self._get_tier_targets(request.selected_tier)

        active_slo = ActiveSlo(
            service_id=request.service_id,
            availability_target=targets["availability"],
            latency_p99_target_ms=targets["latency_p99_ms"],
            latency_p95_target_ms=targets["latency_p95_ms"],
            source=SloSource.RECOMMENDATION_ACCEPTED,
            recommendation_id=UUID(request.recommendation_id) if request.recommendation_id else None,
            selected_tier=request.selected_tier,
            activated_by=request.actor,
        )

        store.set_active_slo(active_slo)
        new_snapshot = self._snapshot_slo(active_slo)

        audit = SloAuditEntry(
            service_id=request.service_id,
            action=SloAction.ACCEPT,
            actor=request.actor,
            recommendation_id=active_slo.recommendation_id,
            previous_slo=previous_snapshot,
            new_slo=new_snapshot,
            selected_tier=request.selected_tier,
            rationale=request.rationale,
        )
        store.append_audit_entry(audit)

        logger.info(f"SLO accepted for {request.service_id} by {request.actor} (tier={request.selected_tier})")

        return ManageSloResponse(
            service_id=request.service_id,
            status="active",
            action="accept",
            active_slo=self._to_active_slo_response(active_slo),
            message=f"SLO accepted for {request.service_id} at {request.selected_tier} tier.",
        )

    async def _handle_modify(self, request: ManageSloRequest) -> ManageSloResponse:
        """Accept a recommendation with modifications."""
        previous_slo = store.get_active_slo(request.service_id)
        previous_snapshot = self._snapshot_slo(previous_slo) if previous_slo else None

        # Start from tier targets, apply modifications
        targets = self._get_tier_targets(request.selected_tier)
        delta: dict = {}

        if request.modifications:
            if request.modifications.availability_target is not None:
                original = targets["availability"]
                targets["availability"] = request.modifications.availability_target
                delta["availability"] = f"{request.modifications.availability_target} (was {original} from {request.selected_tier} tier)"
            if request.modifications.latency_p95_target_ms is not None:
                targets["latency_p95_ms"] = request.modifications.latency_p95_target_ms
                delta["latency_p95_ms"] = request.modifications.latency_p95_target_ms
            if request.modifications.latency_p99_target_ms is not None:
                targets["latency_p99_ms"] = request.modifications.latency_p99_target_ms
                delta["latency_p99_ms"] = request.modifications.latency_p99_target_ms

        active_slo = ActiveSlo(
            service_id=request.service_id,
            availability_target=targets["availability"],
            latency_p99_target_ms=targets["latency_p99_ms"],
            latency_p95_target_ms=targets["latency_p95_ms"],
            source=SloSource.RECOMMENDATION_MODIFIED,
            recommendation_id=UUID(request.recommendation_id) if request.recommendation_id else None,
            selected_tier=request.selected_tier,
            activated_by=request.actor,
        )

        store.set_active_slo(active_slo)
        new_snapshot = self._snapshot_slo(active_slo)

        audit = SloAuditEntry(
            service_id=request.service_id,
            action=SloAction.MODIFY,
            actor=request.actor,
            recommendation_id=active_slo.recommendation_id,
            previous_slo=previous_snapshot,
            new_slo=new_snapshot,
            selected_tier=request.selected_tier,
            rationale=request.rationale,
            modification_delta=delta if delta else None,
        )
        store.append_audit_entry(audit)

        logger.info(f"SLO modified for {request.service_id} by {request.actor} (delta={delta})")

        return ManageSloResponse(
            service_id=request.service_id,
            status="active",
            action="modify",
            active_slo=self._to_active_slo_response(active_slo),
            modification_delta=delta if delta else None,
            message=f"SLO modified for {request.service_id}. Changes: {delta}",
        )

    async def _handle_reject(self, request: ManageSloRequest) -> ManageSloResponse:
        """Reject a recommendation."""
        audit = SloAuditEntry(
            service_id=request.service_id,
            action=SloAction.REJECT,
            actor=request.actor,
            recommendation_id=UUID(request.recommendation_id) if request.recommendation_id else None,
            selected_tier=request.selected_tier,
            rationale=request.rationale,
        )
        store.append_audit_entry(audit)

        logger.info(f"SLO recommendation rejected for {request.service_id} by {request.actor}: {request.rationale}")

        return ManageSloResponse(
            service_id=request.service_id,
            status="rejected",
            action="reject",
            message=f"Recommendation rejected for {request.service_id}. Rationale: {request.rationale}",
        )

    async def get_active_slo(self, service_id: str) -> ActiveSloResponse | None:
        """Get the current active SLO for a service."""
        slo = store.get_active_slo(service_id)
        if slo is None:
            return None
        return self._to_active_slo_response(slo)

    async def get_audit_history(self, service_id: str) -> AuditHistoryResponse:
        """Get the audit trail for a service."""
        entries = store.get_audit_log(service_id)
        return AuditHistoryResponse(
            service_id=service_id,
            entries=[
                AuditEntryResponse(
                    id=str(e.id),
                    service_id=e.service_id,
                    action=e.action.value,
                    actor=e.actor,
                    timestamp=e.timestamp.isoformat(),
                    selected_tier=e.selected_tier,
                    rationale=e.rationale,
                    recommendation_id=str(e.recommendation_id) if e.recommendation_id else None,
                    previous_slo=e.previous_slo,
                    new_slo=e.new_slo,
                    modification_delta=e.modification_delta,
                )
                for e in entries
            ],
            total_count=len(entries),
        )

    @staticmethod
    def _get_tier_targets(tier: str) -> dict:
        """Get default targets for a tier (demo mock data).

        In production, these would come from the actual recommendation.
        """
        tier_defaults = {
            "conservative": {"availability": 99.5, "latency_p95_ms": 300, "latency_p99_ms": 1200},
            "balanced": {"availability": 99.9, "latency_p95_ms": 200, "latency_p99_ms": 800},
            "aggressive": {"availability": 99.95, "latency_p95_ms": 150, "latency_p99_ms": 500},
        }
        return tier_defaults.get(tier, tier_defaults["balanced"]).copy()

    @staticmethod
    def _snapshot_slo(slo: ActiveSlo) -> dict:
        """Create a snapshot dict of an active SLO for audit purposes."""
        return {
            "availability_target": slo.availability_target,
            "latency_p95_target_ms": slo.latency_p95_target_ms,
            "latency_p99_target_ms": slo.latency_p99_target_ms,
            "source": slo.source.value,
            "selected_tier": slo.selected_tier,
            "activated_by": slo.activated_by,
            "activated_at": slo.activated_at.isoformat(),
        }

    @staticmethod
    def _to_active_slo_response(slo: ActiveSlo) -> ActiveSloResponse:
        """Convert an ActiveSlo entity to a response DTO."""
        return ActiveSloResponse(
            service_id=slo.service_id,
            availability_target=slo.availability_target,
            latency_p95_target_ms=slo.latency_p95_target_ms,
            latency_p99_target_ms=slo.latency_p99_target_ms,
            source=slo.source.value,
            recommendation_id=str(slo.recommendation_id) if slo.recommendation_id else None,
            selected_tier=slo.selected_tier,
            activated_at=slo.activated_at.isoformat(),
            activated_by=slo.activated_by,
            slo_id=str(slo.id),
        )
