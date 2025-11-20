"""
error_handling.py - Enterprise Error Handling & Retry System
"""
import time
import functools
from typing import Callable, Optional, Tuple, Type, Any
from enum import Enum
from dataclasses import dataclass
import threading

class ErrorSeverity(Enum):
    """Error severity levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class ErrorCategory(Enum):
    """Error categories."""
    NETWORK = "NETWORK"
    FILESYSTEM = "FILESYSTEM"
    DATABASE = "DATABASE"
    VALIDATION = "VALIDATION"
    AUTHENTICATION = "AUTHENTICATION"
    RATE_LIMIT = "RATE_LIMIT"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"

@dataclass
class ErrorContext:
    """Error context information."""
    error_type: str
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    retry_able: bool
    recovery_action: Optional[str] = None

    def to_dict(self):
        return {
            'error_type': self.error_type,
            'category': self.category.value,
            'severity': self.severity.value,
            'message': self.message,
            'retry_able': self.retry_able,
            'recovery_action': self.recovery_action
        }

class DownloadError(Exception):
    """Base download error."""
    def __init__(self, message: str, context: Optional[ErrorContext] = None):
        super().__init__(message)
        self.context = context or ErrorContext(
            error_type=self.__class__.__name__,
            category=ErrorCategory.UNKNOWN,
            severity=ErrorSeverity.MEDIUM,
            message=message,
            retry_able=True
        )

class NetworkError(DownloadError):
    """Network-related errors."""
    def __init__(self, message: str):
        context = ErrorContext(
            error_type="NetworkError",
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.HIGH,
            message=message,
            retry_able=True,
            recovery_action="Check internet connection and retry"
        )
        super().__init__(message, context)

class RateLimitError(DownloadError):
    """Rate limit errors."""
    def __init__(self, message: str, retry_after: int = 60):
        self.retry_after = retry_after
        context = ErrorContext(
            error_type="RateLimitError",
            category=ErrorCategory.RATE_LIMIT,
            severity=ErrorSeverity.MEDIUM,
            message=f"{message} (retry after {retry_after}s)",
            retry_able=True,
            recovery_action=f"Wait {retry_after} seconds and retry"
        )
        super().__init__(message, context)

class FileSystemError(DownloadError):
    """File system errors."""
    def __init__(self, message: str):
        context = ErrorContext(
            error_type="FileSystemError",
            category=ErrorCategory.FILESYSTEM,
            severity=ErrorSeverity.HIGH,
            message=message,
            retry_able=False,
            recovery_action="Check disk space and permissions"
        )
        super().__init__(message, context)

class ValidationError(DownloadError):
    """Validation errors."""
    def __init__(self, message: str):
        context = ErrorContext(
            error_type="ValidationError",
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.MEDIUM,
            message=message,
            retry_able=False,
            recovery_action="Correct the input and try again"
        )
        super().__init__(message, context)


class RetryStrategy:
    """Retry strategy configuration."""

    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt."""
        delay = min(
            self.initial_delay * (self.exponential_base ** attempt),
            self.max_delay
        )

        if self.jitter:
            import random
            delay = delay * (0.5 + random.random())

        return delay


def retry_on_error(
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    max_attempts: int = 3,
    strategy: Optional[RetryStrategy] = None,
    on_retry: Optional[Callable] = None
):
    """
    Decorator for retrying functions on specific exceptions.

    Args:
        exceptions: Tuple of exception types to retry on
        max_attempts: Maximum number of retry attempts
        strategy: Custom retry strategy
        on_retry: Callback function called on each retry
    """
    if strategy is None:
        strategy = RetryStrategy(max_attempts=max_attempts)

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(strategy.max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt < strategy.max_attempts - 1:
                        delay = strategy.get_delay(attempt)

                        if on_retry:
                            on_retry(attempt + 1, strategy.max_attempts, delay, e)

                        time.sleep(delay)
                    else:
                        # Last attempt failed
                        break

            # All attempts failed
            raise last_exception

        return wrapper
    return decorator


class CircuitBreaker:
    """
    Circuit breaker pattern implementation.
    Prevents cascading failures by stopping requests when failure rate is high.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: float = 60.0,
        expected_exception: Type[Exception] = Exception
    ):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.expected_exception = expected_exception

        self._failure_count = 0
        self._last_failure_time = None
        self._state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
        self._lock = threading.Lock()

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function through circuit breaker."""
        with self._lock:
            if self._state == 'OPEN':
                if time.time() - self._last_failure_time >= self.timeout:
                    self._state = 'HALF_OPEN'
                    self._failure_count = 0
                else:
                    raise Exception("Circuit breaker is OPEN")

        try:
            result = func(*args, **kwargs)
            with self._lock:
                self._failure_count = 0
                self._state = 'CLOSED'
            return result

        except self.expected_exception as e:
            with self._lock:
                self._failure_count += 1
                self._last_failure_time = time.time()

                if self._failure_count >= self.failure_threshold:
                    self._state = 'OPEN'

            raise e

    def reset(self):
        """Reset circuit breaker."""
        with self._lock:
            self._failure_count = 0
            self._last_failure_time = None
            self._state = 'CLOSED'

    @property
    def state(self) -> str:
        """Get current circuit breaker state."""
        return self._state


class ErrorHandler:
    """Centralized error handler."""

    def __init__(self, logger=None):
        self.logger = logger
        self._error_counts = {}
        self._lock = threading.Lock()

    def handle_error(self, error: Exception, context: Optional[dict] = None) -> ErrorContext:
        """Handle error and return error context."""
        # Track error
        error_type = type(error).__name__
        with self._lock:
            self._error_counts[error_type] = self._error_counts.get(error_type, 0) + 1

        # Get or create error context
        if isinstance(error, DownloadError) and error.context:
            error_context = error.context
        else:
            error_context = self._classify_error(error)

        # Log error
        if self.logger:
            self.logger.error(
                f"Error handled: {error_context.message}",
                error_type=error_context.error_type,
                category=error_context.category.value,
                severity=error_context.severity.value,
                retry_able=error_context.retry_able,
                context=context or {},
                exc_info=True
            )

        return error_context

    def _classify_error(self, error: Exception) -> ErrorContext:
        """Classify unknown errors."""
        error_str = str(error).lower()
        error_type = type(error).__name__

        # Network errors
        if any(keyword in error_str for keyword in ['connection', 'network', 'timeout', 'unreachable']):
            return ErrorContext(
                error_type=error_type,
                category=ErrorCategory.NETWORK,
                severity=ErrorSeverity.HIGH,
                message=str(error),
                retry_able=True,
                recovery_action="Check network connection"
            )

        # File system errors
        if any(keyword in error_str for keyword in ['permission', 'disk', 'file', 'directory']):
            return ErrorContext(
                error_type=error_type,
                category=ErrorCategory.FILESYSTEM,
                severity=ErrorSeverity.HIGH,
                message=str(error),
                retry_able=False,
                recovery_action="Check file permissions and disk space"
            )

        # Rate limit
        if any(keyword in error_str for keyword in ['rate', 'limit', 'throttle', '429']):
            return ErrorContext(
                error_type=error_type,
                category=ErrorCategory.RATE_LIMIT,
                severity=ErrorSeverity.MEDIUM,
                message=str(error),
                retry_able=True,
                recovery_action="Wait and retry"
            )

        # Default
        return ErrorContext(
            error_type=error_type,
            category=ErrorCategory.UNKNOWN,
            severity=ErrorSeverity.MEDIUM,
            message=str(error),
            retry_able=True
        )

    def get_error_statistics(self) -> dict:
        """Get error statistics."""
        with self._lock:
            return self._error_counts.copy()

    def reset_statistics(self):
        """Reset error statistics."""
        with self._lock:
            self._error_counts.clear()
