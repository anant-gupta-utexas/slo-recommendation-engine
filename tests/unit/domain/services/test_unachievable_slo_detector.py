"""Unit tests for UnachievableSloDetector."""

import pytest

from src.domain.services.unachievable_slo_detector import UnachievableSloDetector


@pytest.fixture
def detector() -> UnachievableSloDetector:
    """Fixture providing UnachievableSloDetector instance."""
    return UnachievableSloDetector()


class TestCheck:
    """Test check method."""

    def test_achievable_target_returns_none(self, detector: UnachievableSloDetector):
        """Test that achievable target returns None (no warning)."""
        # Target: 99.9%, Composite bound: 99.95% → achievable (bound > target)
        result = detector.check(
            desired_target_pct=99.9,
            composite_bound=0.9995,
            hard_dependency_count=3,
        )
        assert result is None

    def test_unachievable_target_returns_warning(
        self, detector: UnachievableSloDetector
    ):
        """Test that unachievable target returns UnachievableWarning."""
        # Target: 99.99%, Composite bound: 99.7% → unachievable
        result = detector.check(
            desired_target_pct=99.99,
            composite_bound=0.997,
            hard_dependency_count=3,
        )

        assert result is not None
        assert result.desired_target == 99.99
        assert result.composite_bound == pytest.approx(99.7, abs=1e-6)
        assert result.gap == pytest.approx(0.29, abs=1e-2)

    def test_exactly_at_boundary_is_achievable(
        self, detector: UnachievableSloDetector
    ):
        """Test that composite bound exactly at target is achievable."""
        result = detector.check(
            desired_target_pct=99.9,
            composite_bound=0.999,
            hard_dependency_count=2,
        )
        assert result is None

    def test_tiny_gap_still_flagged(self, detector: UnachievableSloDetector):
        """Test that tiny gap (<0.01%) is still flagged as unachievable."""
        result = detector.check(
            desired_target_pct=99.9,
            composite_bound=0.998999,  # 99.8999% (0.0001% below target)
            hard_dependency_count=1,
        )

        assert result is not None
        assert result.gap == pytest.approx(0.0001, abs=1e-6)

    def test_large_gap(self, detector: UnachievableSloDetector):
        """Test unachievable target with large gap."""
        result = detector.check(
            desired_target_pct=99.99,
            composite_bound=0.95,  # 95% (4.99% below target)
            hard_dependency_count=5,
        )

        assert result is not None
        assert result.gap == pytest.approx(4.99, rel=1e-2)

    def test_perfect_composite_bound_is_achievable(
        self, detector: UnachievableSloDetector
    ):
        """Test that perfect (100%) composite bound is achievable for any target."""
        result = detector.check(
            desired_target_pct=99.999,
            composite_bound=1.0,
            hard_dependency_count=10,
        )
        assert result is None


class TestComputeRequiredDepAvailability:
    """Test compute_required_dep_availability method."""

    def test_9999_with_3_deps_gives_999975(self, detector: UnachievableSloDetector):
        """Test 99.99% with 3 deps → 99.9975% (10x rule)."""
        required = detector.compute_required_dep_availability(
            desired_target_pct=99.99,
            hard_dependency_count=3,
        )
        assert required == pytest.approx(99.9975, abs=1e-6)

    def test_999_with_2_deps_gives_99967(self, detector: UnachievableSloDetector):
        """Test 99.9% with 2 deps → 99.967%."""
        required = detector.compute_required_dep_availability(
            desired_target_pct=99.9,
            hard_dependency_count=2,
        )
        # 0.001 / 3 = 0.0003333, 1 - 0.0003333 = 0.9996667 = 99.96667%
        assert required == pytest.approx(99.96667, abs=1e-4)

    def test_0_deps_returns_target_itself(self, detector: UnachievableSloDetector):
        """Test 0 deps → required = target itself."""
        required = detector.compute_required_dep_availability(
            desired_target_pct=99.9,
            hard_dependency_count=0,
        )
        assert required == pytest.approx(99.9, abs=1e-6)

    def test_single_dependency(self, detector: UnachievableSloDetector):
        """Test 99.9% with 1 dep → 99.95%."""
        required = detector.compute_required_dep_availability(
            desired_target_pct=99.9,
            hard_dependency_count=1,
        )
        # 0.001 / 2 = 0.0005, 1 - 0.0005 = 0.9995 = 99.95%
        assert required == pytest.approx(99.95, abs=1e-6)

    def test_high_availability_target(self, detector: UnachievableSloDetector):
        """Test 99.999% (five nines) with 4 deps."""
        required = detector.compute_required_dep_availability(
            desired_target_pct=99.999,
            hard_dependency_count=4,
        )
        # 0.00001 / 5 = 0.000002, 1 - 0.000002 = 0.999998 = 99.9998%
        assert required == pytest.approx(99.9998, abs=1e-6)

    def test_many_dependencies(self, detector: UnachievableSloDetector):
        """Test 99.9% with 9 deps → 99.99%."""
        required = detector.compute_required_dep_availability(
            desired_target_pct=99.9,
            hard_dependency_count=9,
        )
        # 0.001 / 10 = 0.0001, 1 - 0.0001 = 0.9999 = 99.99%
        assert required == pytest.approx(99.99, abs=1e-6)


class TestGenerateWarningMessage:
    """Test generate_warning_message method."""

    def test_message_format_matches_trd(self, detector: UnachievableSloDetector):
        """Test warning message matches TRD format."""
        message = detector.generate_warning_message(
            desired_target_pct=99.99,
            composite_bound_pct=99.70,
        )

        expected = (
            "The desired target of 99.99% is unachievable. "
            "Composite availability bound is 99.70% "
            "given current dependency chain."
        )
        assert message == expected

    def test_message_with_high_precision_values(
        self, detector: UnachievableSloDetector
    ):
        """Test message formatting with high-precision values."""
        message = detector.generate_warning_message(
            desired_target_pct=99.999,
            composite_bound_pct=99.8523,
        )

        assert "99.999%" in message
        assert "99.85%" in message  # Formatted to 2 decimal places

    def test_message_with_large_gap(self, detector: UnachievableSloDetector):
        """Test message with large availability gap."""
        message = detector.generate_warning_message(
            desired_target_pct=99.9,
            composite_bound_pct=95.0,
        )

        assert "99.9%" in message
        assert "95.00%" in message


class TestGenerateRemediationGuidance:
    """Test generate_remediation_guidance method."""

    def test_guidance_contains_three_suggestions(
        self, detector: UnachievableSloDetector
    ):
        """Test that remediation guidance contains 3 concrete suggestions."""
        guidance = detector.generate_remediation_guidance(
            desired_target_pct=99.99,
            required_pct=99.9975,
            n_hard_deps=3,
        )

        assert "1. Add redundant paths" in guidance
        assert "2. Convert to async" in guidance
        assert "3. Relax target" in guidance

    def test_guidance_includes_required_availability(
        self, detector: UnachievableSloDetector
    ):
        """Test that guidance mentions required dependency availability."""
        guidance = detector.generate_remediation_guidance(
            desired_target_pct=99.99,
            required_pct=99.9975,
            n_hard_deps=3,
        )

        assert "99.9975%" in guidance

    def test_guidance_mentions_dependency_count(
        self, detector: UnachievableSloDetector
    ):
        """Test that guidance mentions number of hard dependencies."""
        guidance = detector.generate_remediation_guidance(
            desired_target_pct=99.9,
            required_pct=99.95,
            n_hard_deps=5,
        )

        assert "5 hard" in guidance

    def test_guidance_mentions_redundant_paths(
        self, detector: UnachievableSloDetector
    ):
        """Test that guidance suggests redundant paths."""
        guidance = detector.generate_remediation_guidance(
            desired_target_pct=99.9,
            required_pct=99.95,
            n_hard_deps=2,
        )

        assert "replicas" in guidance.lower()
        assert "parallel" in guidance.lower()

    def test_guidance_mentions_async_conversion(
        self, detector: UnachievableSloDetector
    ):
        """Test that guidance suggests async conversion."""
        guidance = detector.generate_remediation_guidance(
            desired_target_pct=99.9,
            required_pct=99.95,
            n_hard_deps=2,
        )

        assert "async" in guidance.lower() or "queue" in guidance.lower()

    def test_guidance_mentions_target_relaxation(
        self, detector: UnachievableSloDetector
    ):
        """Test that guidance suggests relaxing the target."""
        guidance = detector.generate_remediation_guidance(
            desired_target_pct=99.9,
            required_pct=99.95,
            n_hard_deps=2,
        )

        assert "relax" in guidance.lower() or "achievable" in guidance.lower()


class TestEndToEndWarningCreation:
    """Test end-to-end warning creation flow."""

    def test_complete_warning_object(self, detector: UnachievableSloDetector):
        """Test that check() creates a complete UnachievableWarning with all fields."""
        warning = detector.check(
            desired_target_pct=99.99,
            composite_bound=0.997,
            hard_dependency_count=3,
        )

        assert warning is not None

        # Check all fields are populated
        assert warning.desired_target == 99.99
        assert warning.composite_bound == pytest.approx(99.7, abs=1e-6)
        assert warning.gap == pytest.approx(0.29, abs=1e-2)
        assert warning.required_dep_availability == pytest.approx(99.9975, abs=1e-6)

        # Check message and guidance are non-empty
        assert len(warning.message) > 50
        assert len(warning.remediation_guidance) > 100
        assert "unachievable" in warning.message.lower()

    def test_warning_fields_consistent(self, detector: UnachievableSloDetector):
        """Test that warning fields are mathematically consistent."""
        warning = detector.check(
            desired_target_pct=99.9,
            composite_bound=0.995,
            hard_dependency_count=2,
        )

        assert warning is not None

        # Gap should equal desired - composite
        expected_gap = warning.desired_target - warning.composite_bound
        assert warning.gap == pytest.approx(expected_gap, abs=1e-6)
