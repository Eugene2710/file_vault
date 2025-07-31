import os
import time
import pytest
from unittest.mock import patch

from src.services.rate_limiter_service import RateLimiterService


class TestRateLimiterServiceIntegration:
    """Integration tests for RateLimiterService"""

    @pytest.fixture
    def rate_limiter(self) -> RateLimiterService:
        """Create a fresh rate limiter instance for each test."""
        return RateLimiterService()

    @pytest.fixture
    def test_user_id(self) -> str:
        """Test user ID for isolation."""
        return "test_user_123"

    def test_initialization_with_default_values(
        self, rate_limiter: RateLimiterService
    ) -> None:
        """Test rate limiter initializes with default environment values."""
        assert rate_limiter.max_calls == 2
        assert rate_limiter.time_window == 1

    @patch.dict(os.environ, {"RATE_LIMIT_N_CALLS": "5", "RATE_LIMIT_X_SECONDS": "3"})
    def test_initialization_with_custom_env_values(self) -> None:
        """Test rate limiter initializes with custom environment values."""
        rate_limiter = RateLimiterService()
        assert rate_limiter.max_calls == 5
        assert rate_limiter.time_window == 3

    def test_add_request_within_limit(
        self, rate_limiter: RateLimiterService, test_user_id: str
    ) -> None:
        """Test adding requests within rate limit succeeds."""
        # Should be able to add up to max_calls requests
        for i in range(rate_limiter.max_calls):
            request_id, is_allowed = rate_limiter.add_request(test_user_id)
            assert is_allowed, f"Request {i+1} should be allowed"

    def test_add_request_exceeds_limit(
        self, rate_limiter: RateLimiterService, test_user_id: str
    ) -> None:
        """Test adding requests beyond rate limit fails."""
        # Fill up to the limit
        for _ in range(rate_limiter.max_calls):
            rate_limiter.add_request(test_user_id)

        # Next request should fail
        request_id, is_allowed = rate_limiter.add_request(test_user_id)
        assert not is_allowed, "Request beyond limit should be rejected"

    def test_get_current_request_count(
        self, rate_limiter: RateLimiterService, test_user_id: str
    ) -> None:
        """Test getting current request count for a user."""
        # Initially should be 0
        count = rate_limiter.get_current_request_count(test_user_id)
        assert count == 0

        # Add some requests and check count
        rate_limiter.add_request(test_user_id)
        count = rate_limiter.get_current_request_count(test_user_id)
        assert count == 1

        rate_limiter.add_request(test_user_id)
        count = rate_limiter.get_current_request_count(test_user_id)
        assert count == 2

    def test_clear_user_requests(
        self, rate_limiter: RateLimiterService, test_user_id: str
    ) -> None:
        """Test clearing all requests for a user."""
        # Add some requests
        rate_limiter.add_request(test_user_id)
        rate_limiter.add_request(test_user_id)

        # Verify they exist
        count = rate_limiter.get_current_request_count(test_user_id)
        assert count == 2

        # Clear requests
        rate_limiter.clear_user_requests(test_user_id)

        # Verify they're cleared
        count = rate_limiter.get_current_request_count(test_user_id)
        assert count == 0

    def test_is_allowed_method(
        self, rate_limiter: RateLimiterService, test_user_id: str
    ) -> None:
        """Test the is_allowed method functionality."""
        # First calls should be allowed
        for i in range(rate_limiter.max_calls):
            allowed, message, request_id = rate_limiter.is_allowed(test_user_id)
            assert allowed, f"Call {i+1} should be allowed"
            assert message == "", "Message should be empty for allowed calls"

        # Next call should be blocked
        allowed, message, request_id = rate_limiter.is_allowed(test_user_id)
        assert not allowed, "Call beyond limit should be blocked"
        assert message == "Call Limit Reached"

    def test_get_rate_limit_info(
        self, rate_limiter: RateLimiterService, test_user_id: str
    ) -> None:
        """Test getting rate limit information."""
        # Initially should show full limit available
        info = rate_limiter.get_rate_limit_info(test_user_id)
        assert info["remaining_calls"] == rate_limiter.max_calls
        assert info["limit"] == rate_limiter.max_calls
        assert info["window"] == rate_limiter.time_window
        assert info["reset_time"] == 0

        # Add a request and check info updates
        rate_limiter.add_request(test_user_id)
        info = rate_limiter.get_rate_limit_info(test_user_id)
        assert info["remaining_calls"] == rate_limiter.max_calls - 1
        assert info["reset_time"] > 0

    def test_sliding_window_behavior(
        self, rate_limiter: RateLimiterService, test_user_id: str
    ) -> None:
        """Test that the sliding window properly expires old requests."""
        # Fill up the rate limit
        for _ in range(rate_limiter.max_calls):
            rate_limiter.add_request(test_user_id)

        # Should be at limit
        request_id, is_allowed = rate_limiter.add_request(test_user_id)
        assert not is_allowed

        # Wait for window to expire
        time.sleep(rate_limiter.time_window + 0.1)

        # Should be able to add requests again
        request_id, is_allowed = rate_limiter.add_request(test_user_id)
        assert is_allowed, "Should be able to add request after window expires"

    def test_multiple_users_isolation(self, rate_limiter: RateLimiterService) -> None:
        """Test that rate limiting is isolated between different users."""
        user1 = "user1"
        user2 = "user2"

        # Fill up limit for user1
        for _ in range(rate_limiter.max_calls):
            rate_limiter.add_request(user1)

        # user1 should be blocked
        request_id, is_allowed = rate_limiter.add_request(user1)
        assert not is_allowed

        # user2 should still be allowed
        request_id, is_allowed = rate_limiter.add_request(user2)
        assert is_allowed, "Different user should not be affected by other user's limit"

    def test_thread_safety_simulation(
        self, rate_limiter: RateLimiterService, test_user_id: str
    ) -> None:
        """Test basic thread safety by rapid successive calls."""
        # Make rapid successive calls to test lock behavior
        results = []
        for _ in range(rate_limiter.max_calls + 2):  # Try more than limit
            request_id, is_allowed = rate_limiter.add_request(test_user_id)
            results.append(is_allowed)

        # First max_calls should succeed, rest should fail
        successful_calls = sum(results)
        assert successful_calls == rate_limiter.max_calls

    def test_expired_requests_cleanup(
        self, rate_limiter: RateLimiterService, test_user_id: str
    ) -> None:
        """Test that expired requests are properly cleaned up."""
        # Add a request
        rate_limiter.add_request(test_user_id)
        assert rate_limiter.get_current_request_count(test_user_id) == 1

        # Wait for expiration
        time.sleep(rate_limiter.time_window + 0.1)

        # Check count - should trigger cleanup
        count = rate_limiter.get_current_request_count(test_user_id)
        assert count == 0, "Expired requests should be cleaned up"

    def test_rate_limit_info_reset_time_calculation(
        self, rate_limiter: RateLimiterService, test_user_id: str
    ) -> None:
        """Test that reset time is calculated correctly."""
        # Add a request
        before_time = time.time()
        rate_limiter.add_request(test_user_id)
        after_time = time.time()

        info = rate_limiter.get_rate_limit_info(test_user_id)
        reset_time = info["reset_time"]

        # Reset time should be approximately current_time + time_window
        expected_min = int(before_time + rate_limiter.time_window)
        expected_max = (
            int(after_time + rate_limiter.time_window) + 1
        )  # Add 1 for rounding

        assert (
            expected_min <= reset_time <= expected_max
        ), f"Reset time {reset_time} not in expected range [{expected_min}, {expected_max}]"