"""Unit tests for WeightedAttributionService."""

import pytest

from src.domain.entities.slo_recommendation import SliType
from src.domain.services.weighted_attribution_service import (
    AttributionWeights,
    WeightedAttributionService,
)


class TestAttributionWeights:
    """Test AttributionWeights configuration."""

    def test_availability_weights_sum_to_one(self):
        """Should have availability weights that sum to 1.0."""
        weights = AttributionWeights()
        total = sum(weights.AVAILABILITY_WEIGHTS.values())
        assert total == pytest.approx(1.0, abs=1e-9)

    def test_latency_weights_sum_to_one(self):
        """Should have latency weights that sum to 1.0."""
        weights = AttributionWeights()
        total = sum(weights.LATENCY_WEIGHTS.values())
        assert total == pytest.approx(1.0, abs=1e-9)

    def test_availability_weight_coverage(self):
        """Should define all expected availability features."""
        weights = AttributionWeights()
        expected_features = {
            "historical_availability_mean",
            "downstream_dependency_risk",
            "external_api_reliability",
            "deployment_frequency",
        }
        assert set(weights.AVAILABILITY_WEIGHTS.keys()) == expected_features

    def test_latency_weight_coverage(self):
        """Should define all expected latency features."""
        weights = AttributionWeights()
        expected_features = {
            "p99_latency_historical",
            "call_chain_depth",
            "noisy_neighbor_margin",
            "traffic_seasonality",
        }
        assert set(weights.LATENCY_WEIGHTS.keys()) == expected_features

    def test_availability_weight_values(self):
        """Should have correct availability weight values."""
        weights = AttributionWeights()
        assert weights.AVAILABILITY_WEIGHTS["historical_availability_mean"] == 0.40
        assert weights.AVAILABILITY_WEIGHTS["downstream_dependency_risk"] == 0.30
        assert weights.AVAILABILITY_WEIGHTS["external_api_reliability"] == 0.15
        assert weights.AVAILABILITY_WEIGHTS["deployment_frequency"] == 0.15

    def test_latency_weight_values(self):
        """Should have correct latency weight values."""
        weights = AttributionWeights()
        assert weights.LATENCY_WEIGHTS["p99_latency_historical"] == 0.50
        assert weights.LATENCY_WEIGHTS["call_chain_depth"] == 0.22
        assert weights.LATENCY_WEIGHTS["noisy_neighbor_margin"] == 0.15
        assert weights.LATENCY_WEIGHTS["traffic_seasonality"] == 0.13


class TestWeightedAttributionService:
    """Test WeightedAttributionService."""

    @pytest.fixture
    def service(self):
        """Fixture for WeightedAttributionService."""
        return WeightedAttributionService()

    # Availability Attribution

    def test_availability_attribution_basic(self, service):
        """Should compute availability attribution with correct normalization."""
        feature_values = {
            "historical_availability_mean": 0.999,
            "downstream_dependency_risk": 0.995,
            "external_api_reliability": 0.998,
            "deployment_frequency": 0.990,
        }
        result = service.compute_attribution(SliType.AVAILABILITY, feature_values)

        # Check we got all features back
        assert len(result) == 4

        # Check contributions sum to 1.0
        total_contribution = sum(attr.contribution for attr in result)
        assert total_contribution == pytest.approx(1.0, abs=1e-9)

        # Check sorted by contribution descending
        for i in range(len(result) - 1):
            assert result[i].contribution >= result[i + 1].contribution

        # Check descriptions are populated
        for attr in result:
            assert attr.feature in feature_values

    def test_availability_attribution_weights_applied(self, service):
        """Should correctly apply weights to feature values."""
        # Use simple values to verify weight application
        feature_values = {
            "historical_availability_mean": 1.0,
            "downstream_dependency_risk": 1.0,
            "external_api_reliability": 1.0,
            "deployment_frequency": 1.0,
        }
        result = service.compute_attribution(SliType.AVAILABILITY, feature_values)

        # When all features are 1.0, contributions should equal weights (normalized)
        result_map = {attr.feature: attr.contribution for attr in result}
        assert result_map["historical_availability_mean"] == pytest.approx(0.40)
        assert result_map["downstream_dependency_risk"] == pytest.approx(0.30)
        assert result_map["external_api_reliability"] == pytest.approx(0.15)
        assert result_map["deployment_frequency"] == pytest.approx(0.15)

    def test_availability_attribution_sorting(self, service):
        """Should sort attributions by contribution descending."""
        feature_values = {
            "historical_availability_mean": 0.50,  # weight 0.40 -> contrib 0.20
            "downstream_dependency_risk": 1.00,    # weight 0.30 -> contrib 0.30
            "external_api_reliability": 0.80,      # weight 0.15 -> contrib 0.12
            "deployment_frequency": 0.60,          # weight 0.15 -> contrib 0.09
        }
        result = service.compute_attribution(SliType.AVAILABILITY, feature_values)

        # Raw contributions: 0.20, 0.30, 0.12, 0.09 -> total = 0.71
        # Normalized: 0.282, 0.423, 0.169, 0.127
        # Sorted: downstream (0.423), historical (0.282), external (0.169), deployment (0.127)
        assert result[0].feature == "downstream_dependency_risk"
        assert result[1].feature == "historical_availability_mean"
        assert result[2].feature == "external_api_reliability"
        assert result[3].feature == "deployment_frequency"

    # Latency Attribution

    def test_latency_attribution_basic(self, service):
        """Should compute latency attribution with correct normalization."""
        feature_values = {
            "p99_latency_historical": 120.5,
            "call_chain_depth": 5.0,
            "noisy_neighbor_margin": 15.2,
            "traffic_seasonality": 0.8,
        }
        result = service.compute_attribution(SliType.LATENCY, feature_values)

        # Check we got all features back
        assert len(result) == 4

        # Check contributions sum to 1.0
        total_contribution = sum(attr.contribution for attr in result)
        assert total_contribution == pytest.approx(1.0, abs=1e-9)

        # Check sorted by contribution descending
        for i in range(len(result) - 1):
            assert result[i].contribution >= result[i + 1].contribution

    def test_latency_attribution_weights_applied(self, service):
        """Should correctly apply weights to latency features."""
        # Use uniform values
        feature_values = {
            "p99_latency_historical": 1.0,
            "call_chain_depth": 1.0,
            "noisy_neighbor_margin": 1.0,
            "traffic_seasonality": 1.0,
        }
        result = service.compute_attribution(SliType.LATENCY, feature_values)

        # Contributions should equal weights
        result_map = {attr.feature: attr.contribution for attr in result}
        assert result_map["p99_latency_historical"] == pytest.approx(0.50)
        assert result_map["call_chain_depth"] == pytest.approx(0.22)
        assert result_map["noisy_neighbor_margin"] == pytest.approx(0.15)
        assert result_map["traffic_seasonality"] == pytest.approx(0.13)

    def test_latency_attribution_sorting(self, service):
        """Should sort latency attributions by contribution descending."""
        feature_values = {
            "p99_latency_historical": 200.0,  # weight 0.50 -> contrib 100.0
            "call_chain_depth": 10.0,         # weight 0.22 -> contrib 2.2
            "noisy_neighbor_margin": 50.0,    # weight 0.15 -> contrib 7.5
            "traffic_seasonality": 5.0,       # weight 0.13 -> contrib 0.65
        }
        result = service.compute_attribution(SliType.LATENCY, feature_values)

        # p99 should dominate
        assert result[0].feature == "p99_latency_historical"
        assert result[1].feature == "noisy_neighbor_margin"
        assert result[2].feature == "call_chain_depth"
        assert result[3].feature == "traffic_seasonality"

    # Edge Cases

    def test_all_zero_features(self, service):
        """Should handle all zero feature values with uniform distribution."""
        feature_values = {
            "historical_availability_mean": 0.0,
            "downstream_dependency_risk": 0.0,
            "external_api_reliability": 0.0,
            "deployment_frequency": 0.0,
        }
        result = service.compute_attribution(SliType.AVAILABILITY, feature_values)

        # Should distribute uniformly when all values are zero
        for attr in result:
            assert attr.contribution == pytest.approx(0.25, abs=1e-9)

    def test_single_dominant_feature(self, service):
        """Should handle case where one feature dominates."""
        feature_values = {
            "historical_availability_mean": 1.0,
            "downstream_dependency_risk": 0.001,
            "external_api_reliability": 0.001,
            "deployment_frequency": 0.001,
        }
        result = service.compute_attribution(SliType.AVAILABILITY, feature_values)

        # Historical should dominate
        historical = next(
            attr for attr in result if attr.feature == "historical_availability_mean"
        )
        # Weight is 0.40, others total ~0.0006, so normalized ~99.8%
        assert historical.contribution > 0.99

    def test_very_small_feature_values(self, service):
        """Should handle very small but positive feature values."""
        feature_values = {
            "historical_availability_mean": 0.001,
            "downstream_dependency_risk": 0.001,
            "external_api_reliability": 0.001,
            "deployment_frequency": 0.001,
        }
        result = service.compute_attribution(SliType.AVAILABILITY, feature_values)

        # Should still normalize correctly
        total_contribution = sum(attr.contribution for attr in result)
        assert total_contribution == pytest.approx(1.0, abs=1e-9)

        # Contributions should match weights when all values are equal
        result_map = {attr.feature: attr.contribution for attr in result}
        assert result_map["historical_availability_mean"] == pytest.approx(0.40)
        assert result_map["downstream_dependency_risk"] == pytest.approx(0.30)

    # Error Cases

    def test_unknown_sli_type(self, service):
        """Should reject unknown SLI type."""
        with pytest.raises(ValueError, match="Unknown SLI type"):
            service.compute_attribution(
                sli_type="invalid",  # type: ignore
                feature_values={},
            )

    def test_missing_feature_keys(self, service):
        """Should reject when feature keys don't match weight keys."""
        feature_values = {
            "historical_availability_mean": 0.999,
            # Missing: downstream_dependency_risk, external_api_reliability, deployment_frequency
        }
        with pytest.raises(ValueError, match="Missing features"):
            service.compute_attribution(SliType.AVAILABILITY, feature_values)

    def test_extra_feature_keys(self, service):
        """Should reject when extra features are provided."""
        feature_values = {
            "historical_availability_mean": 0.999,
            "downstream_dependency_risk": 0.995,
            "external_api_reliability": 0.998,
            "deployment_frequency": 0.990,
            "unknown_feature": 1.0,  # Extra
        }
        with pytest.raises(ValueError, match="Unknown features"):
            service.compute_attribution(SliType.AVAILABILITY, feature_values)

    def test_mismatched_feature_keys(self, service):
        """Should reject when both missing and extra features."""
        feature_values = {
            "historical_availability_mean": 0.999,
            "unknown_feature": 1.0,
        }
        with pytest.raises(ValueError, match="Missing features.*Unknown features"):
            service.compute_attribution(SliType.AVAILABILITY, feature_values)

    # Utility Methods

    def test_get_available_features_availability(self, service):
        """Should return available features for availability SLI."""
        features = service.get_available_features(SliType.AVAILABILITY)
        assert set(features) == {
            "historical_availability_mean",
            "downstream_dependency_risk",
            "external_api_reliability",
            "deployment_frequency",
        }

    def test_get_available_features_latency(self, service):
        """Should return available features for latency SLI."""
        features = service.get_available_features(SliType.LATENCY)
        assert set(features) == {
            "p99_latency_historical",
            "call_chain_depth",
            "noisy_neighbor_margin",
            "traffic_seasonality",
        }

    def test_get_available_features_unknown_type(self, service):
        """Should reject unknown SLI type for get_available_features."""
        with pytest.raises(ValueError, match="Unknown SLI type"):
            service.get_available_features("invalid")  # type: ignore

    def test_get_feature_weight_availability(self, service):
        """Should return correct weight for availability feature."""
        weight = service.get_feature_weight(
            SliType.AVAILABILITY, "historical_availability_mean"
        )
        assert weight == 0.40

    def test_get_feature_weight_latency(self, service):
        """Should return correct weight for latency feature."""
        weight = service.get_feature_weight(
            SliType.LATENCY, "p99_latency_historical"
        )
        assert weight == 0.50

    def test_get_feature_weight_unknown_feature(self, service):
        """Should reject unknown feature name."""
        with pytest.raises(ValueError, match="Unknown feature"):
            service.get_feature_weight(SliType.AVAILABILITY, "nonexistent_feature")

    def test_get_feature_weight_unknown_sli_type(self, service):
        """Should reject unknown SLI type for get_feature_weight."""
        with pytest.raises(ValueError, match="Unknown SLI type"):
            service.get_feature_weight("invalid", "some_feature")  # type: ignore

    # Integration-style Tests

    def test_full_availability_workflow(self, service):
        """Should handle complete availability attribution workflow."""
        # Realistic feature values
        feature_values = {
            "historical_availability_mean": 0.9995,
            "downstream_dependency_risk": 0.9980,
            "external_api_reliability": 0.9990,
            "deployment_frequency": 0.9985,
        }
        result = service.compute_attribution(SliType.AVAILABILITY, feature_values)

        # Verify all properties
        assert len(result) == 4
        assert all(0.0 <= attr.contribution <= 1.0 for attr in result)
        assert sum(attr.contribution for attr in result) == pytest.approx(1.0)
        assert all(attr.feature in feature_values.keys() for attr in result)

        # Check ordering is correct
        for i in range(len(result) - 1):
            assert result[i].contribution >= result[i + 1].contribution

        # Check descriptions are populated
        for attr in result:
            assert attr.description != ""

    def test_full_latency_workflow(self, service):
        """Should handle complete latency attribution workflow."""
        feature_values = {
            "p99_latency_historical": 145.8,
            "call_chain_depth": 3.5,
            "noisy_neighbor_margin": 12.4,
            "traffic_seasonality": 0.75,
        }
        result = service.compute_attribution(SliType.LATENCY, feature_values)

        # Verify all properties
        assert len(result) == 4
        assert all(0.0 <= attr.contribution <= 1.0 for attr in result)
        assert sum(attr.contribution for attr in result) == pytest.approx(1.0)

        # p99_latency_historical should dominate (50% weight, high value)
        assert result[0].feature == "p99_latency_historical"
        assert result[0].contribution > 0.5
