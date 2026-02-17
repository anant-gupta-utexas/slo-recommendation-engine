"""In-memory store for active SLOs and audit log (demo-only).

This module provides a simple in-memory implementation for the FR-5 demo.
Data is cleared on application restart. For production, replace with
PostgreSQL-backed repositories using active_slos and slo_audit_log tables.
"""

from uuid import UUID

from src.domain.entities.active_slo import ActiveSlo, SloAuditEntry

# Global in-memory stores (cleared on restart)
_active_slos: dict[str, ActiveSlo] = {}  # service_id -> ActiveSlo
_audit_log: list[SloAuditEntry] = []  # append-only list


def get_active_slo(service_id: str) -> ActiveSlo | None:
    """Get the active SLO for a service.

    Args:
        service_id: Business identifier of the service

    Returns:
        ActiveSlo if one exists, None otherwise
    """
    return _active_slos.get(service_id)


def set_active_slo(slo: ActiveSlo) -> None:
    """Set or replace the active SLO for a service.

    Args:
        slo: The active SLO to store
    """
    _active_slos[slo.service_id] = slo


def remove_active_slo(service_id: str) -> bool:
    """Remove the active SLO for a service.

    Args:
        service_id: Business identifier of the service

    Returns:
        True if an SLO was removed, False if none existed
    """
    if service_id in _active_slos:
        del _active_slos[service_id]
        return True
    return False


def list_all_active_slos() -> list[ActiveSlo]:
    """List all active SLOs.

    Returns:
        List of all active SLOs currently stored
    """
    return list(_active_slos.values())


def append_audit_entry(entry: SloAuditEntry) -> None:
    """Append an audit log entry (immutable, append-only).

    Args:
        entry: The audit entry to append
    """
    _audit_log.append(entry)


def get_audit_log(service_id: str | None = None) -> list[SloAuditEntry]:
    """Get audit log entries, optionally filtered by service.

    Args:
        service_id: If provided, filter entries to this service only

    Returns:
        List of audit entries, newest first
    """
    if service_id:
        entries = [e for e in _audit_log if e.service_id == service_id]
    else:
        entries = list(_audit_log)
    return sorted(entries, key=lambda e: e.timestamp, reverse=True)


def clear_all() -> None:
    """Clear all data (for testing)."""
    _active_slos.clear()
    _audit_log.clear()
