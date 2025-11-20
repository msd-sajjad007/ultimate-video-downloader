"""
security.py - Security Layer
"""
import hashlib
import hmac
import secrets
from urllib.parse import urlparse
from typing import List, Optional
import re

class SecurityValidator:
    """Security validation and sanitization."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.max_file_size = self.config.get('max_file_size', 10 * 1024 * 1024 * 1024)  # 10GB
        self.allowed_protocols = self.config.get('allowed_protocols', ['http', 'https'])
        self.blocked_domains = set(self.config.get('blocked_domains', []))
        self.allowed_domains = set(self.config.get('allowed_domains', []))  # Empty = all allowed

    def validate_url(self, url: str) -> tuple[bool, Optional[str]]:
        """Validate URL for security."""
        try:
            parsed = urlparse(url)

            # Check protocol
            if parsed.scheme not in self.allowed_protocols:
                return False, f"Protocol {parsed.scheme} not allowed"

            # Check domain blocklist
            if parsed.netloc in self.blocked_domains:
                return False, "Domain is blocked"

            # Check domain allowlist (if configured)
            if self.allowed_domains and parsed.netloc not in self.allowed_domains:
                return False, "Domain not in allowlist"

            # Check for local/private IPs
            if self._is_private_ip(parsed.netloc):
                return False, "Private IP addresses not allowed"

            return True, None

        except Exception as e:
            return False, f"Invalid URL: {str(e)}"

    def _is_private_ip(self, hostname: str) -> bool:
        """Check if hostname is a private IP."""
        private_patterns = [
            r'^127\.',
            r'^10\.',
            r'^172\.(1[6-9]|2[0-9]|3[0-1])\.',
            r'^192\.168\.',
            r'^localhost$',
            r'^::1$',
            r'^fc00:',
        ]
        return any(re.match(pattern, hostname) for pattern in private_patterns)

    def sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to prevent path traversal."""
        # Remove dangerous characters
        sanitized = re.sub(r'[<>:"/\|?* -]', '_', filename)

        # Remove path separators
        sanitized = sanitized.replace('..', '_').replace('/', '_').replace('\\', '_')

        # Limit length
        if len(sanitized) > 255:
            name, ext = sanitized.rsplit('.', 1) if '.' in sanitized else (sanitized, '')
            sanitized = name[:250] + ('.' + ext if ext else '')

        return sanitized or 'download'

    def validate_file_size(self, size: int) -> bool:
        """Validate file size."""
        return 0 < size <= self.max_file_size

    def generate_secure_token(self, length: int = 32) -> str:
        """Generate secure random token."""
        return secrets.token_urlsafe(length)

    def hash_password(self, password: str, salt: Optional[bytes] = None) -> tuple[str, str]:
        """Hash password with salt."""
        if salt is None:
            salt = secrets.token_bytes(32)

        hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
        return hashed.hex(), salt.hex()

    def verify_password(self, password: str, hashed: str, salt: str) -> bool:
        """Verify password hash."""
        computed_hash, _ = self.hash_password(password, bytes.fromhex(salt))
        return hmac.compare_digest(computed_hash, hashed)
