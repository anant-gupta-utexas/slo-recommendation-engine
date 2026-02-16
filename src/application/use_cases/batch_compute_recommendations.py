"""Batch Compute SLO Recommendations Use Case (FR-2).

Computes recommendations for multiple services in batch mode (background job).
"""

import asyncio
import logging
import time
from typing import Any

from src.application.dtos.slo_recommendation_dto import (
    BatchComputeResult,
    GenerateRecommendationRequest,
)
from src.application.use_cases.generate_slo_recommendation import (
    GenerateSloRecommendationUseCase,
)
from src.domain.repositories.service_repository import ServiceRepositoryInterface

logger = logging.getLogger(__name__)

# Limit concurrent recommendation generation to avoid resource exhaustion
MAX_CONCURRENT_GENERATIONS = 20


class BatchComputeRecommendationsUseCase:
    """Batch compute SLO recommendations for multiple services.

    Typically run as a scheduled background task to keep recommendations fresh.
    Iterates non-discovered services and calls GenerateSloRecommendationUseCase
    for each service and SLI type.
    """

    def __init__(
        self,
        service_repo: ServiceRepositoryInterface,
        generate_use_case: GenerateSloRecommendationUseCase,
    ):
        """Initialize use case with dependencies.

        Args:
            service_repo: Repository for service lookups
            generate_use_case: Use case to generate recommendations per service
        """
        self._service_repo = service_repo
        self._generate_use_case = generate_use_case

    async def execute(
        self,
        sli_type: str = "all",
        lookback_days: int = 30,
        exclude_discovered_only: bool = True,
    ) -> BatchComputeResult:
        """Compute recommendations for all eligible services.

        Args:
            sli_type: "availability", "latency", or "all" (default: "all")
            lookback_days: Lookback window for telemetry (default: 30)
            exclude_discovered_only: Skip services with is_discovered=True (default: True)

        Returns:
            BatchComputeResult with counts and error details
        """
        logger.info(
            f"BatchComputeRecommendations.execute starting: "
            f"sli_type={sli_type}, lookback_days={lookback_days}, "
            f"exclude_discovered_only={exclude_discovered_only}"
        )
        start_time = time.time()

        # Step 1: Fetch all eligible services
        # Use large limit to get all services (10000 should be more than enough)
        all_services = await self._service_repo.list_all(skip=0, limit=10000)

        # Filter out discovered-only services if requested
        if exclude_discovered_only:
            eligible_services = [
                s for s in all_services if not getattr(s, "is_discovered", False)
            ]
            skipped_count = len(all_services) - len(eligible_services)
        else:
            eligible_services = all_services
            skipped_count = 0

        logger.info(
            f"Found {len(all_services)} total services, "
            f"{len(eligible_services)} eligible (skipped {skipped_count} discovered-only)"
        )

        # Step 2: Generate recommendations for each service
        tasks = []
        for service in eligible_services:
            task = self._generate_for_service(
                service.service_id, sli_type, lookback_days
            )
            tasks.append(task)

        # Step 3: Execute with concurrency control
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_GENERATIONS)
        results = await self._execute_with_semaphore(tasks, semaphore)

        # Step 4: Aggregate results
        successful = 0
        failed = 0
        failures: list[dict[str, str]] = []

        for service_id, result, error in results:
            if error:
                failed += 1
                failures.append({"service_id": service_id, "error": str(error)})
            else:
                successful += 1

        duration = time.time() - start_time

        logger.info(
            f"BatchComputeRecommendations.execute complete: "
            f"total={len(eligible_services)}, successful={successful}, "
            f"failed={failed}, skipped={skipped_count}, duration={duration:.2f}s"
        )

        return BatchComputeResult(
            total_services=len(eligible_services),
            successful=successful,
            failed=failed,
            skipped=skipped_count,
            duration_seconds=round(duration, 2),
            failures=failures,
        )

    async def _generate_for_service(
        self, service_id: str, sli_type: str, lookback_days: int
    ) -> tuple[str, Any | None, Exception | None]:
        """Generate recommendations for a single service.

        Args:
            service_id: Business ID of the service
            sli_type: "availability", "latency", or "all"
            lookback_days: Lookback window

        Returns:
            Tuple of (service_id, result, error)
        """
        try:
            request = GenerateRecommendationRequest(
                service_id=service_id,
                sli_type=sli_type,
                lookback_days=lookback_days,
            )
            result = await self._generate_use_case.execute(request)
            return (service_id, result, None)
        except Exception as e:
            logger.error(
                f"Failed to generate recommendation for {service_id}: {e}",
                exc_info=True,
            )
            return (service_id, None, e)

    async def _execute_with_semaphore(
        self,
        tasks: list,
        semaphore: asyncio.Semaphore,
    ) -> list[tuple[str, Any | None, Exception | None]]:
        """Execute tasks with semaphore-based concurrency control.

        Args:
            tasks: List of coroutines to execute
            semaphore: Semaphore for limiting concurrency

        Returns:
            List of results (service_id, result, error)
        """

        async def limited_task(coro):
            async with semaphore:
                return await coro

        wrapped_tasks = [limited_task(task) for task in tasks]
        return await asyncio.gather(*wrapped_tasks, return_exceptions=False)
