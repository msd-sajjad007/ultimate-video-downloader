"""
config.py - Enterprise Configuration Management (COMPLETE FIX)
"""
import os
import json
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass, asdict, field

@dataclass
class DatabaseConfig:
    """Database configuration."""
    path: str = str(Path.home() / ".ultimate_downloader" / "data.db")
    timeout: int = 30
    journal_mode: str = "WAL"
    cache_size: int = -64000
    connection_pool_size: int = 5

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

@dataclass
class DownloadConfig:
    """Download configuration."""
    default_quality: str = "best"
    default_path: str = str(Path.home() / "Downloads")
    max_concurrent_downloads: int = 3
    retry_attempts: int = 5
    retry_delay: int = 3
    socket_timeout: int = 30
    fragment_retries: int = 10
    rate_limit: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

@dataclass
class BrowserConfig:
    """Browser capture configuration."""
    headless: bool = True
    timeout: int = 300
    viewport_width: int = 1920
    viewport_height: int = 1080
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    auto_install_browser: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

@dataclass
class SecurityConfig:
    """Security configuration."""
    enable_ssl_verification: bool = True
    allowed_domains: list = field(default_factory=list)
    blocked_domains: list = field(default_factory=list)
    max_file_size: int = 10 * 1024 * 1024 * 1024  # 10GB
    enable_virus_scan: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    log_dir: str = str(Path.home() / ".ultimate_downloader" / "logs")
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5
    enable_console: bool = True
    enable_file: bool = True
    structured_logging: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

@dataclass
class PerformanceConfig:
    """Performance configuration."""
    enable_caching: bool = True
    cache_ttl: int = 3600
    max_memory_usage: int = 1024
    enable_compression: bool = True
    thread_pool_size: int = 10

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

@dataclass
class AppConfig:
    """Main application configuration."""
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    download: DownloadConfig = field(default_factory=DownloadConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)

    app_name: str = "Ultimate Video Downloader"
    version: str = "2.0.0"
    environment: str = "production"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    def save(self, path: Optional[str] = None):
        """Save configuration to file."""
        if path is None:
            config_dir = Path.home() / ".ultimate_downloader"
            config_dir.mkdir(parents=True, exist_ok=True)
            path = str(config_dir / "config.json")
        else:
            # Ensure directory exists
            config_path = Path(path)
            config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Optional[str] = None) -> 'AppConfig':
        """Load configuration from file."""
        if path is None:
            path = str(Path.home() / ".ultimate_downloader" / "config.json")

        if not os.path.exists(path):
            # Create default config
            config = cls()
            config.save(path)
            return config

        with open(path, 'r') as f:
            data = json.load(f)

        return cls(
            database=DatabaseConfig(**data.get('database', {})),
            download=DownloadConfig(**data.get('download', {})),
            browser=BrowserConfig(**data.get('browser', {})),
            security=SecurityConfig(**data.get('security', {})),
            logging=LoggingConfig(**data.get('logging', {})),
            performance=PerformanceConfig(**data.get('performance', {})),
            app_name=data.get('app_name', 'Ultimate Video Downloader'),
            version=data.get('version', '2.0.0'),
            environment=data.get('environment', 'production')
        )

    def validate(self) -> tuple[bool, list[str]]:
        """Validate configuration."""
        errors = []

        if self.database.timeout < 1:
            errors.append("Database timeout must be >= 1")

        if self.download.max_concurrent_downloads < 1:
            errors.append("Max concurrent downloads must be >= 1")

        if self.security.max_file_size < 1024 * 1024:
            errors.append("Max file size must be >= 1MB")

        return len(errors) == 0, errors


class ConfigManager:
    """Singleton configuration manager."""
    _instance: Optional[AppConfig] = None

    @classmethod
    def get_config(cls) -> AppConfig:
        """Get global configuration instance."""
        if cls._instance is None:
            cls._instance = AppConfig.load()
        return cls._instance

    @classmethod
    def reload_config(cls):
        """Reload configuration from file."""
        cls._instance = AppConfig.load()

    @classmethod
    def update_config(cls, **kwargs):
        """Update configuration values."""
        if cls._instance is None:
            cls._instance = AppConfig.load()

        for key, value in kwargs.items():
            if hasattr(cls._instance, key):
                setattr(cls._instance, key, value)

        cls._instance.save()


# Test the config on import
if __name__ == "__main__":
    print("Testing configuration...")
    config = ConfigManager.get_config()
    print(f"✅ Config loaded: {config.app_name} v{config.version}")
    print(f"✅ Database path: {config.database.path}")
    print(f"✅ Logging to_dict works: {bool(config.logging.to_dict())}")
    print("✅ Configuration module is working correctly!")
