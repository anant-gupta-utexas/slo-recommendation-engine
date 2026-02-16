"""Weighted feature attribution service for recommendation explainability.

This service computes weighted feature attributions using fixed domain weights (heuristic MVP).
In Phase 5, these will be replaced by ML-derived SHAP values.
"""

from dataclasses import dataclass

from src.domain.entities.slo_recommendation import FeatureAttribution, SliType


@dataclass
class AttributionWeights:
    """Predefined weights for feature importance.

    These are domain-expert heuristic weights for the MVP.
    In production, these would be derived from SHAP analysis on trained models.
    """

    # Availability feature weights
    AVAILABILITY_WEIGHTS: dict[str, float] = None  # type: ignore
    # Latency feature weights
    LATENCY_WEIGHTS: dict[str, float] = None  # type: ignore

    def __post_init__(self):
        """Initialize default weight mappings."""
        self.AVAILABILITY_WEIGHTS = {
            "historical_availability_mean": 0.40,
            "downstream_dependency_risk": 0.30,
            "external_api_reliability": 0.15,
            "deployment_frequency": 0.15,
        }
        self.LATENCY_WEIGHTS = {
            "p99_latency_historical": 0.50,
            "call_chain_depth": 0.22,
            "noisy_neighbor_margin": 0.15,
            "traffic_seasonality": 0.13,
        }


class WeightedAttributionService:
    """Computes weighted feature attribution for recommendation explainability.

    MVP heuristic weights (to be replaced by ML-derived SHAP values in Phase 5):

    Availability:
    - historical_availability_mean:   0.40  (primary driver)
    - downstream_dependency_risk:     0.30  (dependency constraint)
    - external_api_reliability:       0.15  (external risk)
    - deployment_frequency:           0.15  (stability signal)

    Latency:
    - p99_latency_historical:         0.50  (primary driver)
    - call_chain_depth:               0.22  (cascading delay)
    - noisy_neighbor_margin:          0.15  (infrastructure noise)
    - traffic_seasonality:            0.13  (load patterns)
    """

    def __init__(self):
        """Initialize with default attribution weights."""
        self.weights = AttributionWeights()

    def compute_attribution(
        self,
        sli_type: SliType,
        feature_values: dict[str, float],
    ) -> list[FeatureAttribution]:
        """Compute weighted feature attributions.

        Algorithm:
        1. Select weight mapping based on SLI type
        2. For each feature, multiply value by weight
        3. Normalize contributions so they sum to 1.0
        4. Sort by absolute contribution descending
        5. Return as FeatureAttribution objects

        Args:
            sli_type: Type of SLI (availability or latency)
            feature_values: Map of feature names to their values

        Returns:
            List of FeatureAttribution objects, sorted by contribution descending

        Raises:
            ValueError: If unknown SLI type or feature keys don't match weight keys
        """
        # Select weight mapping
        if sli_type == SliType.AVAILABILITY:
            weight_mapping = self.weights.AVAILABILITY_WEIGHTS
        elif sli_type == SliType.LATENCY:
            weight_mapping = self.weights.LATENCY_WEIGHTS
        else:
            raise ValueError(f"Unknown SLI type: {sli_type}")

        # Validate feature keys match weight keys
        feature_keys = set(feature_values.keys())
        weight_keys = set(weight_mapping.keys())
        if feature_keys != weight_keys:
            missing = weight_keys - feature_keys
            extra = feature_keys - weight_keys
            error_parts = []
            if missing:
                error_parts.append(f"Missing features: {sorted(missing)}")
            if extra:
                error_parts.append(f"Unknown features: {sorted(extra)}")
            raise ValueError(
                f"Feature keys must match weight keys. {', '.join(error_parts)}"
            )

        # Compute raw weighted contributions
        raw_contributions: dict[str, float] = {}
        for feature_name, feature_value in feature_values.items():
            weight = weight_mapping[feature_name]
            raw_contributions[feature_name] = feature_value * weight

        # Normalize to sum = 1.0
        total = sum(raw_contributions.values())
        if total == 0.0:
            # Edge case: all features are zero, distribute uniformly
            normalized_contributions = {
                name: 1.0 / len(raw_contributions)
                for name in raw_contributions.keys()
            }
        else:
            normalized_contributions = {
                name: contrib / total
                for name, contrib in raw_contributions.items()
            }

        # Convert to FeatureAttribution objects
        attributions = [
            FeatureAttribution(
                feature=name,
                contribution=normalized_contributions[name],
                description=f"{name}: {feature_values[name]:.4f}",
            )
            for name in feature_values.keys()
        ]

        # Sort by absolute contribution descending
        attributions.sort(key=lambda attr: abs(attr.contribution), reverse=True)

        return attributions

    def get_available_features(self, sli_type: SliType) -> list[str]:
        """Get list of available feature names for a given SLI type.

        Args:
            sli_type: Type of SLI (availability or latency)

        Returns:
            List of feature names

        Raises:
            ValueError: If unknown SLI type
        """
        if sli_type == SliType.AVAILABILITY:
            return list(self.weights.AVAILABILITY_WEIGHTS.keys())
        elif sli_type == SliType.LATENCY:
            return list(self.weights.LATENCY_WEIGHTS.keys())
        else:
            raise ValueError(f"Unknown SLI type: {sli_type}")

    def get_feature_weight(self, sli_type: SliType, feature_name: str) -> float:
        """Get the weight for a specific feature.

        Args:
            sli_type: Type of SLI (availability or latency)
            feature_name: Name of the feature

        Returns:
            Weight value (0.0-1.0)

        Raises:
            ValueError: If unknown SLI type or feature name
        """
        if sli_type == SliType.AVAILABILITY:
            weight_mapping = self.weights.AVAILABILITY_WEIGHTS
        elif sli_type == SliType.LATENCY:
            weight_mapping = self.weights.LATENCY_WEIGHTS
        else:
            raise ValueError(f"Unknown SLI type: {sli_type}")

        if feature_name not in weight_mapping:
            raise ValueError(
                f"Unknown feature '{feature_name}' for {sli_type.value} SLI. "
                f"Available: {sorted(weight_mapping.keys())}"
            )

        return weight_mapping[feature_name]
