"""External API adaptive buffer service for FR-3.

Implements the pessimistic adjustment strategy for external dependencies
per TRD 3.3.
"""

from uuid import UUID

from src.domain.entities.constraint_analysis import ExternalProviderProfile


class ExternalApiBufferService:
    """Computes effective availability for external dependencies.

    Applies the adaptive buffer strategy per TRD 3.3:
    - If both observed and published SLA are available:
      effective = min(observed, published_adjusted)
      where published_adjusted = 1 - (1-published) × 11
    - If only observed: use observed
    - If only published: use published_adjusted
    - If neither: default to 99.9%

    This service is deliberately simple and deterministic.
    """

    PESSIMISTIC_MULTIPLIER: int = 10  # Adds 10x unavailability margin (× 11 total)
    DEFAULT_EXTERNAL_AVAILABILITY: float = 0.999  # 99.9% conservative default

    def compute_effective_availability(
        self,
        profile: ExternalProviderProfile,
    ) -> float:
        """Compute effective availability for an external dependency.

        Args:
            profile: External provider profile with published SLA and observed data

        Returns:
            Effective availability ratio (0.0 to 1.0)
        """
        return profile.effective_availability

    def build_profile(
        self,
        service_id: str,
        service_uuid: UUID,
        published_sla: float | None,
        observed_availability: float | None,
        observation_window_days: int,
    ) -> ExternalProviderProfile:
        """Build an ExternalProviderProfile from raw inputs.

        Args:
            service_id: Business identifier
            service_uuid: Internal UUID
            published_sla: Published SLA as ratio (e.g., 0.9999)
            observed_availability: Measured availability ratio
            observation_window_days: Days of observation data

        Returns:
            Populated ExternalProviderProfile
        """
        return ExternalProviderProfile(
            service_id=service_id,
            service_uuid=service_uuid,
            published_sla=published_sla,
            observed_availability=observed_availability,
            observation_window_days=observation_window_days,
        )

    def generate_availability_note(
        self,
        profile: ExternalProviderProfile,
        effective: float,
    ) -> str:
        """Generate human-readable note explaining how effective availability was computed.

        Examples:
        - "Using min(observed 99.85%, published×adj 99.89%) = 99.85%"
        - "No monitoring data; using published SLA 99.99% adjusted to 99.89%"
        - "No published SLA or monitoring data; using conservative default 99.9%"

        Args:
            profile: External provider profile
            effective: Computed effective availability

        Returns:
            Human-readable explanation string
        """
        observed = profile.observed_availability
        published = profile.published_sla

        if observed is not None and published is not None:
            # Both available: explain min() selection
            published_adjusted = profile._compute_pessimistic_adjustment(published)
            return (
                f"Using min(observed {observed*100:.2f}%, "
                f"published×adj {published_adjusted*100:.2f}%) = {effective*100:.2f}%"
            )
        elif observed is not None:
            # Only observed
            return f"Using observed availability {effective*100:.2f}%"
        elif published is not None:
            # Only published
            return (
                f"No monitoring data; using published SLA {published*100:.2f}% "
                f"adjusted to {effective*100:.2f}%"
            )
        else:
            # Neither
            return (
                f"No published SLA or monitoring data; using conservative default "
                f"{effective*100:.1f}%"
            )
