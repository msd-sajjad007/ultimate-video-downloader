"""
logger.py - Enterprise Logging & Monitoring System
"""
import logging
import logging.handlers
import json
import traceback
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional
from dataclasses import dataclass, asdict
from enum import Enum
import threading

class LogLevel(Enum):
    """Log levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

@dataclass
class LogEntry:
    """Structured log entry."""
    timestamp: str
    level: str
    message: str
    module: str
    function: str
    line_number: int
    thread_id: int
    extra: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())


class StructuredLogger:
    """Enterprise-grade structured logger."""

    def __init__(self, name: str, config: Optional[Dict] = None):
        self.name = name
        self.config = config or {}
        self.logger = self._setup_logger()
        self._metrics = {
            'total_logs': 0,
            'errors': 0,
            'warnings': 0,
            'downloads_started': 0,
            'downloads_completed': 0,
            'downloads_failed': 0,
        }
        self._lock = threading.Lock()

    def _setup_logger(self) -> logging.Logger:
        """Setup logger with handlers."""
        logger = logging.getLogger(self.name)
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()

        # Console handler
        if self.config.get('enable_console', True):
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)

        # File handler with rotation
        if self.config.get('enable_file', True):
            log_dir = Path(self.config.get('log_dir', Path.home() / '.ultimate_downloader' / 'logs'))
            log_dir.mkdir(parents=True, exist_ok=True)

            log_file = log_dir / f'{self.name}.log'
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=self.config.get('max_file_size', 10 * 1024 * 1024),  # 10MB
                backupCount=self.config.get('backup_count', 5)
            )
            file_handler.setLevel(logging.DEBUG)

            if self.config.get('structured_logging', True):
                file_formatter = logging.Formatter('%(message)s')
            else:
                file_formatter = logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S'
                )

            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)

        return logger

    def _create_log_entry(self, level: str, message: str, **kwargs) -> LogEntry:
        """Create structured log entry."""
        frame = traceback.extract_stack()[-3]

        return LogEntry(
            timestamp=datetime.utcnow().isoformat() + 'Z',
            level=level,
            message=message,
            module=frame.filename,
            function=frame.name,
            line_number=frame.lineno,
            thread_id=threading.get_ident(),
            extra=kwargs
        )

    def _log(self, level: str, message: str, **kwargs):
        """Internal logging method."""
        with self._lock:
            self._metrics['total_logs'] += 1
            if level == 'ERROR':
                self._metrics['errors'] += 1
            elif level == 'WARNING':
                self._metrics['warnings'] += 1

        if self.config.get('structured_logging', True):
            entry = self._create_log_entry(level, message, **kwargs)
            log_message = entry.to_json()
        else:
            log_message = message
            if kwargs:
                log_message += f" | Extra: {kwargs}"

        getattr(self.logger, level.lower())(log_message)

    def debug(self, message: str, **kwargs):
        """Log debug message."""
        self._log('DEBUG', message, **kwargs)

    def info(self, message: str, **kwargs):
        """Log info message."""
        self._log('INFO', message, **kwargs)

    def warning(self, message: str, **kwargs):
        """Log warning message."""
        self._log('WARNING', message, **kwargs)

    def error(self, message: str, exc_info: bool = False, **kwargs):
        """Log error message."""
        if exc_info:
            kwargs['traceback'] = traceback.format_exc()
        self._log('ERROR', message, **kwargs)

    def critical(self, message: str, exc_info: bool = False, **kwargs):
        """Log critical message."""
        if exc_info:
            kwargs['traceback'] = traceback.format_exc()
        self._log('CRITICAL', message, **kwargs)

    def download_started(self, url: str, quality: str = 'best', **kwargs):
        """Log download start event."""
        with self._lock:
            self._metrics['downloads_started'] += 1
        self.info('Download started', url=url, quality=quality, event='download_started', **kwargs)

    def download_completed(self, url: str, file_path: str, size_bytes: int, duration_sec: float, **kwargs):
        """Log download completion event."""
        with self._lock:
            self._metrics['downloads_completed'] += 1
        self.info(
            'Download completed',
            url=url,
            file_path=file_path,
            size_bytes=size_bytes,
            size_mb=round(size_bytes / (1024 * 1024), 2),
            duration_sec=round(duration_sec, 2),
            speed_mbps=round((size_bytes / (1024 * 1024)) / duration_sec, 2) if duration_sec > 0 else 0,
            event='download_completed',
            **kwargs
        )

    def download_failed(self, url: str, error: str, **kwargs):
        """Log download failure event."""
        with self._lock:
            self._metrics['downloads_failed'] += 1
        self.error('Download failed', url=url, error=error, event='download_failed', **kwargs)

    def get_metrics(self) -> Dict[str, int]:
        """Get logger metrics."""
        with self._lock:
            return self._metrics.copy()

    def reset_metrics(self):
        """Reset metrics."""
        with self._lock:
            for key in self._metrics:
                self._metrics[key] = 0


class LoggerFactory:
    """Factory for creating loggers."""
    _loggers: Dict[str, StructuredLogger] = {}
    _lock = threading.Lock()

    @classmethod
    def get_logger(cls, name: str, config: Optional[Dict] = None) -> StructuredLogger:
        """Get or create logger instance."""
        with cls._lock:
            if name not in cls._loggers:
                cls._loggers[name] = StructuredLogger(name, config)
            return cls._loggers[name]

    @classmethod
    def get_all_metrics(cls) -> Dict[str, Dict[str, int]]:
        """Get metrics from all loggers."""
        with cls._lock:
            return {name: logger.get_metrics() for name, logger in cls._loggers.items()}


# Performance monitoring decorator
def monitor_performance(func):
    """Decorator to monitor function performance."""
    def wrapper(*args, **kwargs):
        logger = LoggerFactory.get_logger('performance')
        start_time = datetime.now()

        try:
            result = func(*args, **kwargs)
            duration = (datetime.now() - start_time).total_seconds()

            logger.info(
                f'Function executed: {func.__name__}',
                function=func.__name__,
                duration_sec=round(duration, 4),
                status='success'
            )
            return result
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(
                f'Function failed: {func.__name__}',
                function=func.__name__,
                duration_sec=round(duration, 4),
                status='failed',
                error=str(e),
                exc_info=True
            )
            raise

    return wrapper
