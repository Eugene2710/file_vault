import os
import time
import uuid
from collections import defaultdict, deque
from threading import Lock
from dataclasses import dataclass


@dataclass
class RequestInfo:
    request_id: str
    timestamp: float
    user_id: str


class RateLimiterService:
    def __init__(self):
        self.max_calls = int(os.environ.get("RATE_LIMIT_N_CALLS", 2))
        self.time_window = int(os.environ.get("RATE_LIMIT_X_SECONDS", 1))
        self.user_requests: dict[str, deque[RequestInfo]] = defaultdict(deque)
        self.lock = Lock()

    def is_allowed(self, user_id: str) -> tuple[bool, str, str | None]:
        request_id, is_allowed = self.add_request(user_id)
        if is_allowed:
            return True, "", request_id
        else:
            return False, "Call Limit Reached", request_id

    def get_rate_limit_info(self, user_id: str) -> dict[str, int]:
        current_count = self.get_current_request_count(user_id)

        with self.lock:
            user_queue = self.user_requests[user_id]
            next_reset = user_queue[0].timestamp + self.time_window if user_queue else 0
            return {
                "remaining_calls": max(0, self.max_calls - current_count),
                "reset_time": int(next_reset) if user_queue else 0,
                "limit": self.max_calls,
                "window": self.time_window,
            }

    def _clean_expired_requests(self, user_id: str, current_time: float) -> None:
        """Remove expired requests from user's queue."""
        user_queue = self.user_requests[user_id]
        while user_queue and current_time - user_queue[0].timestamp >= self.time_window:
            user_queue.popleft()

    def add_request(self, user_id: str) -> tuple[str, bool]:
        """Add a request to the user's queue if allowed by rate limit."""
        current_time = time.time()
        request_id = str(uuid.uuid4())

        with self.lock:
            self._clean_expired_requests(user_id, current_time)
            user_queue = self.user_requests[user_id]

            if len(user_queue) >= self.max_calls:
                return request_id, False

            request_info = RequestInfo(
                request_id=request_id, timestamp=current_time, user_id=user_id
            )
            user_queue.append(request_info)
            return request_id, True

    def get_current_request_count(self, user_id: str) -> int:
        """Get the current number of active requests for a user."""
        current_time = time.time()

        with self.lock:
            self._clean_expired_requests(user_id, current_time)
            return len(self.user_requests[user_id])

    def clear_user_requests(self, user_id: str) -> None:
        """Clear all requests for a specific user."""
        with self.lock:
            if user_id in self.user_requests:
                self.user_requests[user_id].clear()