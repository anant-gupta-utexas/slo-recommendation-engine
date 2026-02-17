"""Counterfactual analysis service for FR-7 Explainability.

Generates "what-if" counterfactual statements by perturbing the top contributing
features and observing how the recommended target changes.
"""

import logging
from dataclasses import dataclass

from src.domain.entities.slo_recommendation import FeatureAttribution

logger = logging.getLogger(__name__)


@dataclass
class Counterfactual:
    """A single counterfactual statement.

    Attributes:
        condition: Human-readable condition (e.g., "If external-payment-api improved to 99.99%")
        result: Human-readable result (e.g., "Recommended target would increase to 99.95%")
        feature: The feature that was perturbed
        original_value: Original feature value
        perturbed_value: Perturbed feature value
    """

    condition: str
    result: str
    feature: str = ""
    original_value: float = 0.0
    perturbed_value: float = 0.0


@dataclass
class DataProvenance:
    """Data provenance metadata for a recommendation.

    Attributes:
        dependency_graph_version: Timestamp of the graph snapshot used
        telemetry_window_start: Start of the telemetry window (ISO 8601)
        telemetry_window_end: End of the telemetry window (ISO 8601)
        data_completeness: Data completeness score (0.0-1.0)
        computation_method: Algorithm used for computation
        telemetry_source: Source of telemetry data
    """

    dependency_graph_version: str = ""
    telemetry_window_start: str = ""
    telemetry_window_end: str = ""
    data_completeness: float = 0.0
    computation_method: str = "composite_reliability_math_v1"
    telemetry_source: str = "mock_prometheus"


class CounterfactualService:
    """Generates counterfactual "what-if" analysis for recommendations.

    For each top-N feature attribution, perturbs the feature value and
    estimates how the recommended target would change.

    This is a heuristic MVP implementation. In Phase 5, counterfactuals
    will be computed by re-running the ML model with perturbed inputs.
    """

    MAX_COUNTERFACTUALS = 3

    # Perturbation steps per feature (how much to improve the feature)
    PERTURBATION_STEPS = {
        "historical_availability_mean": 0.005,    # +0.5% availability
        "downstream_dependency_risk": -0.005,     # Reduce risk by 0.5%
        "external_api_reliability": 0.005,        # +0.5% reliability
        "deployment_frequency": -0.1,             # Reduce deploys by 10%
        "p99_latency_historical": -50.0,          # Reduce p99 by 50ms
        "call_chain_depth": -1.0,                 # Reduce depth by 1
        "noisy_neighbor_margin": -0.02,           # Reduce margin by 2%
        "traffic_seasonality": -0.1,              # Reduce seasonality by 10%
    }

    # Human-readable descriptions for conditions
    FEATURE_DESCRIPTIONS = {
        "historical_availability_mean": "historical availability improved by 0.5%",
        "downstream_dependency_risk": "downstream dependency risk reduced by 0.5%",
        "external_api_reliability": "external API reliability improved to {value:.2f}%",
        "deployment_frequency": "deployment frequency reduced by 10%",
        "p99_latency_historical": "p99 latency reduced by 50ms to {value:.0f}ms",
        "call_chain_depth": "call chain depth reduced by 1 hop",
        "noisy_neighbor_margin": "infrastructure noise margin reduced by 2%",
        "traffic_seasonality": "traffic seasonality variance reduced by 10%",
    }

    def generate_counterfactuals(
        self,
        sli_type: str,
        current_target: float,
        feature_attributions: list[FeatureAttribution],
        feature_values: dict[str, float],
    ) -> list[Counterfactual]:
        """Generate counterfactual statements for the top contributing features.

        Args:
            sli_type: "availability" or "latency"
            current_target: The current recommended target (e.g., 99.9 or 800ms)
            feature_attributions: Sorted list of feature attributions
            feature_values: Map of feature name to actual value

        Returns:
            List of up to MAX_COUNTERFACTUALS counterfactual statements
        """
        counterfactuals = []

        # Take top-N features by contribution
        top_features = sorted(
            feature_attributions,
            key=lambda fa: fa.contribution,
            reverse=True,
        )[:self.MAX_COUNTERFACTUALS]

        for fa in top_features:
            step = self.PERTURBATION_STEPS.get(fa.feature, 0.005)
            original_value = feature_values.get(fa.feature, 0.0)
            perturbed_value = original_value + step

            # Estimate impact on target (heuristic: proportional to contribution)
            if sli_type == "availability":
                target_delta = abs(step) * fa.contribution * 100  # Scale to percentage
                new_target = min(99.999, current_target + target_delta)
                result_str = f"Recommended target would increase to {new_target:.2f}%"
            else:
                target_delta = abs(step) * fa.contribution * 10
                new_target = max(50, current_target - target_delta)
                result_str = f"Recommended latency target would decrease to {new_target:.0f}ms"

            # Build condition string
            desc_template = self.FEATURE_DESCRIPTIONS.get(
                fa.feature, f"{fa.feature} improved"
            )
            try:
                condition_str = f"If {desc_template.format(value=perturbed_value * 100 if sli_type == 'availability' else perturbed_value)}"
            except (KeyError, IndexError):
                condition_str = f"If {desc_template}"

            counterfactuals.append(Counterfactual(
                condition=condition_str,
                result=result_str,
                feature=fa.feature,
                original_value=original_value,
                perturbed_value=perturbed_value,
            ))

        return counterfactuals
