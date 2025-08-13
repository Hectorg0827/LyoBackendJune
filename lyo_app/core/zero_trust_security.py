"""
Zero-Trust Security Architecture Implementation
Comprehensive security framework with advanced threat detection
"""

import asyncio
import hashlib
import hmac
import secrets
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Union, Tuple
from enum import Enum
import json
import jwt
from cryptography.fernet import Fernet
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
import pyotp
from fastapi import HTTPException, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import geoip2.database
import user_agents
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.core.config import settings
from lyo_app.core.cache_manager import get_cache_manager

logger = structlog.get_logger(__name__)


class SecurityLevel(Enum):
    """Security levels for different operations"""
    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    VERIFIED = "verified"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


class ThreatLevel(Enum):
    """Threat detection levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AuthenticationMethod(Enum):
    """Available authentication methods"""
    PASSWORD = "password"
    TOTP = "totp"
    SMS = "sms"
    EMAIL = "email"
    HARDWARE_KEY = "hardware_key"
    BIOMETRIC = "biometric"


class ZeroTrustSecurityManager:
    """
    Comprehensive zero-trust security implementation
    """
    
    def __init__(self):
        self.ph = PasswordHasher(
            time_cost=3,      # Increased for production security
            memory_cost=65536, # 64 MB
            parallelism=1,
            hash_len=32,
            salt_len=16
        )
        
        # Encryption setup
        self.encryption_key = self._get_or_generate_encryption_key()
        self.fernet = Fernet(self.encryption_key)
        
        # JWT settings
        self.jwt_secret = getattr(settings, 'SECRET_KEY', secrets.token_urlsafe(32))
        self.jwt_algorithm = "HS256"
        self.access_token_expire = 900   # 15 minutes
        self.refresh_token_expire = 604800  # 7 days
        
        # Security thresholds
        self.max_failed_attempts = 5
        self.lockout_duration = 900  # 15 minutes
        self.suspicious_activity_threshold = 10
        
        # Threat detection patterns
        self.threat_patterns = {
            "sql_injection": [r"(\bunion\b|\bselect\b|\binsert\b|\bdelete\b|\bdrop\b)", "(?i)"],
            "xss": [r"<script|javascript:|onclick=|onerror=", "i"],
            "path_traversal": [r"\.\.\/|\.\.\\", ""],
            "command_injection": [r"[;&|`$]", ""]
        }
    
    def _get_or_generate_encryption_key(self) -> bytes:
        """Get or generate encryption key"""
        key = getattr(settings, 'ENCRYPTION_KEY', None)
        if key:
            return key.encode() if isinstance(key, str) else key
        
        # Generate new key for development
        new_key = Fernet.generate_key()
        logger.warning("Generated new encryption key. Set ENCRYPTION_KEY in production!")
        return new_key
    
    # Password Security
    async def hash_password(self, password: str) -> str:
        """Hash password with Argon2"""
        try:
            return self.ph.hash(password)
        except Exception as e:
            logger.error(f"Password hashing failed: {e}")
            raise HTTPException(500, "Authentication system error")
    
    async def verify_password(self, password: str, hashed: str) -> bool:
        """Verify password against hash"""
        try:
            self.ph.verify(hashed, password)
            return True
        except VerifyMismatchError:
            return False
        except Exception as e:
            logger.error(f"Password verification failed: {e}")
            return False
    
    async def validate_password_strength(self, password: str) -> Dict[str, Any]:
        """Validate password meets security requirements"""
        checks = {
            "length": len(password) >= 12,
            "uppercase": any(c.isupper() for c in password),
            "lowercase": any(c.islower() for c in password),
            "digits": any(c.isdigit() for c in password),
            "special": any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password),
            "no_common": password.lower() not in ["password123", "admin123", "12345678"]
        }
        
        score = sum(checks.values())
        strength = "weak" if score < 4 else "medium" if score < 6 else "strong"
        
        return {
            "valid": all(checks.values()),
            "score": score,
            "strength": strength,
            "checks": checks
        }
    
    # Multi-Factor Authentication
    async def setup_totp(self, user_id: int, email: str) -> Dict[str, str]:
        """Setup TOTP 2FA for user"""
        secret = pyotp.random_base32()
        
        # Encrypt and store secret
        encrypted_secret = self.fernet.encrypt(secret.encode()).decode()
        
        # Store in cache temporarily for verification
        cache_manager = get_cache_manager()
        await cache_manager.set(
            f"totp_setup:{user_id}",
            {"secret": encrypted_secret, "verified": False},
            ttl=600  # 10 minutes to verify
        )
        
        # Generate QR code URI
        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(
            name=email,
            issuer_name="LyoApp"
        )
        
        return {
            "secret": secret,
            "qr_uri": provisioning_uri,
            "backup_codes": self._generate_backup_codes()
        }
    
    async def verify_totp(self, user_id: int, token: str, secret: str = None) -> bool:
        """Verify TOTP token"""
        try:
            if not secret:
                # Get from user's stored secret (encrypted)
                # This would typically come from database
                cache_manager = get_cache_manager()
                setup_data = await cache_manager.get(f"totp_setup:{user_id}")
                if not setup_data:
                    return False
                
                encrypted_secret = setup_data["secret"]
                secret = self.fernet.decrypt(encrypted_secret.encode()).decode()
            
            totp = pyotp.TOTP(secret)
            return totp.verify(token, valid_window=1)  # Allow 30s window
            
        except Exception as e:
            logger.error(f"TOTP verification failed: {e}")
            return False
    
    def _generate_backup_codes(self, count: int = 10) -> List[str]:
        """Generate backup codes for 2FA"""
        return [secrets.token_hex(4).upper() for _ in range(count)]
    
    # JWT Token Management
    async def create_tokens(
        self,
        user_id: int,
        email: str,
        roles: List[str],
        permissions: List[str],
        device_info: Dict[str, Any] = None
    ) -> Dict[str, str]:
        """Create access and refresh tokens"""
        
        now = datetime.utcnow()
        jti = str(uuid.uuid4())  # JWT ID for token tracking
        
        # Access token payload
        access_payload = {
            "sub": str(user_id),
            "email": email,
            "roles": roles,
            "permissions": permissions,
            "iat": now.timestamp(),
            "exp": (now + timedelta(seconds=self.access_token_expire)).timestamp(),
            "type": "access",
            "jti": jti
        }
        
        # Refresh token payload (minimal data)
        refresh_payload = {
            "sub": str(user_id),
            "iat": now.timestamp(),
            "exp": (now + timedelta(seconds=self.refresh_token_expire)).timestamp(),
            "type": "refresh",
            "jti": jti
        }
        
        # Add device fingerprint if available
        if device_info:
            fingerprint = self._generate_device_fingerprint(device_info)
            access_payload["device"] = fingerprint
            refresh_payload["device"] = fingerprint
        
        access_token = jwt.encode(access_payload, self.jwt_secret, algorithm=self.jwt_algorithm)
        refresh_token = jwt.encode(refresh_payload, self.jwt_secret, algorithm=self.jwt_algorithm)
        
        # Store token metadata in cache for revocation
        cache_manager = get_cache_manager()
        token_metadata = {
            "user_id": user_id,
            "created_at": now.isoformat(),
            "device_info": device_info,
            "active": True
        }
        
        await cache_manager.set(
            f"token:{jti}",
            token_metadata,
            ttl=self.refresh_token_expire
        )
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": self.access_token_expire
        }
    
    async def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=[self.jwt_algorithm]
            )
            
            # Check if token is revoked
            jti = payload.get("jti")
            if jti:
                cache_manager = get_cache_manager()
                token_metadata = await cache_manager.get(f"token:{jti}")
                if not token_metadata or not token_metadata.get("active"):
                    return None
            
            return payload
            
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
    
    async def revoke_token(self, jti: str) -> bool:
        """Revoke a specific token"""
        cache_manager = get_cache_manager()
        token_metadata = await cache_manager.get(f"token:{jti}")
        
        if token_metadata:
            token_metadata["active"] = False
            await cache_manager.set(f"token:{jti}", token_metadata)
            return True
        
        return False
    
    async def revoke_all_user_tokens(self, user_id: int) -> int:
        """Revoke all tokens for a user"""
        # This would typically query all active tokens for the user
        # For now, we'll implement a simple blacklist approach
        cache_manager = get_cache_manager()
        
        # Add user to token blacklist
        await cache_manager.set(
            f"user_tokens_revoked:{user_id}",
            {"revoked_at": datetime.utcnow().isoformat()},
            ttl=self.refresh_token_expire
        )
        
        return 1  # Return count of revoked tokens
    
    # Device Fingerprinting
    def _generate_device_fingerprint(self, device_info: Dict[str, Any]) -> str:
        """Generate device fingerprint from request info"""
        fingerprint_data = {
            "user_agent": device_info.get("user_agent", ""),
            "ip_hash": hashlib.sha256(
                device_info.get("ip", "").encode()
            ).hexdigest()[:16],
            "accept_language": device_info.get("accept_language", ""),
            "timezone": device_info.get("timezone", "")
        }
        
        fingerprint_string = json.dumps(fingerprint_data, sort_keys=True)
        return hashlib.sha256(fingerprint_string.encode()).hexdigest()[:32]
    
    async def verify_device(
        self,
        user_id: int,
        current_fingerprint: str,
        request_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Verify device and detect suspicious activity"""
        cache_manager = get_cache_manager()
        
        # Get known devices for user
        known_devices = await cache_manager.get(f"user_devices:{user_id}") or {}
        
        # Check if device is known
        device_known = current_fingerprint in known_devices
        
        # Analyze for suspicious patterns
        threat_level = await self._analyze_request_threat(request_info)
        
        result = {
            "device_known": device_known,
            "threat_level": threat_level.value,
            "requires_additional_auth": not device_known or threat_level in [ThreatLevel.HIGH, ThreatLevel.CRITICAL],
            "device_fingerprint": current_fingerprint
        }
        
        # Log suspicious activity
        if not device_known or threat_level != ThreatLevel.LOW:
            await self._log_security_event(
                user_id,
                "device_verification",
                {
                    "device_fingerprint": current_fingerprint,
                    "device_known": device_known,
                    "threat_level": threat_level.value,
                    "request_info": request_info
                }
            )
        
        # Store new device if verified
        if device_known or threat_level == ThreatLevel.LOW:
            known_devices[current_fingerprint] = {
                "first_seen": datetime.utcnow().isoformat(),
                "last_seen": datetime.utcnow().isoformat(),
                "verified": device_known
            }
            
            await cache_manager.set(
                f"user_devices:{user_id}",
                known_devices,
                ttl=86400 * 30  # 30 days
            )
        
        return result
    
    # Threat Detection
    async def _analyze_request_threat(self, request_info: Dict[str, Any]) -> ThreatLevel:
        """Analyze request for threat indicators"""
        threat_score = 0
        
        # Check for malicious patterns in request
        for pattern_name, (pattern, flags) in self.threat_patterns.items():
            import re
            regex_flags = 0
            if "i" in flags.lower():
                regex_flags |= re.IGNORECASE
            
            # Check URL, headers, and body for patterns
            for field in ["url", "headers", "body"]:
                field_value = str(request_info.get(field, ""))
                if re.search(pattern, field_value, regex_flags):
                    threat_score += 3
                    logger.warning(f"Threat pattern {pattern_name} detected in {field}")
        
        # Check IP reputation (simplified)
        ip_address = request_info.get("ip", "")
        if await self._check_ip_reputation(ip_address):
            threat_score += 5
        
        # Check for unusual user agent
        user_agent = request_info.get("user_agent", "")
        if await self._check_unusual_user_agent(user_agent):
            threat_score += 2
        
        # Check request frequency (rate limiting related)
        request_frequency = request_info.get("request_frequency", 0)
        if request_frequency > 100:  # Requests per minute
            threat_score += 4
        
        # Determine threat level
        if threat_score >= 10:
            return ThreatLevel.CRITICAL
        elif threat_score >= 7:
            return ThreatLevel.HIGH
        elif threat_score >= 4:
            return ThreatLevel.MEDIUM
        else:
            return ThreatLevel.LOW
    
    async def _check_ip_reputation(self, ip_address: str) -> bool:
        """Check IP against threat intelligence (simplified)"""
        # In production, integrate with threat intelligence feeds
        # For now, check against a simple blocklist
        
        known_malicious_ranges = [
            "10.0.0.0/8",    # Private ranges (shouldn't be external)
            "172.16.0.0/12",
            "192.168.0.0/16"
        ]
        
        # Simple check - in production use proper CIDR matching
        for malicious_range in known_malicious_ranges:
            if ip_address.startswith(malicious_range.split('/')[0].rsplit('.', 1)[0]):
                return True
        
        return False
    
    async def _check_unusual_user_agent(self, user_agent: str) -> bool:
        """Check for unusual or suspicious user agents"""
        suspicious_patterns = [
            "curl", "wget", "python", "bot", "crawler", "scraper",
            "scanner", "test", "automated"
        ]
        
        user_agent_lower = user_agent.lower()
        return any(pattern in user_agent_lower for pattern in suspicious_patterns)
    
    async def _log_security_event(
        self,
        user_id: int,
        event_type: str,
        details: Dict[str, Any]
    ):
        """Log security events for analysis"""
        cache_manager = get_cache_manager()
        
        event = {
            "user_id": user_id,
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details
        }
        
        # Store in security log
        log_key = f"security_log:{datetime.utcnow().strftime('%Y%m%d')}"
        await cache_manager.redis_client.lpush(log_key, json.dumps(event))
        await cache_manager.redis_client.expire(log_key, 86400 * 7)  # Keep 7 days
        
        logger.warning(f"Security event: {event_type} for user {user_id}")
    
    # Data Encryption
    async def encrypt_sensitive_data(self, data: str) -> str:
        """Encrypt sensitive data (PII, passwords, etc.)"""
        try:
            encrypted_data = self.fernet.encrypt(data.encode())
            return encrypted_data.decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise HTTPException(500, "Encryption failed")
    
    async def decrypt_sensitive_data(self, encrypted_data: str) -> str:
        """Decrypt sensitive data"""
        try:
            decrypted_data = self.fernet.decrypt(encrypted_data.encode())
            return decrypted_data.decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise HTTPException(500, "Decryption failed")
    
    # Rate Limiting with Advanced Features
    async def check_advanced_rate_limit(
        self,
        identifier: str,
        endpoint: str,
        user_role: str = "user"
    ) -> Dict[str, Any]:
        """Advanced rate limiting with role-based limits"""
        
        # Define limits based on role and endpoint
        rate_limits = {
            "public": {"default": (100, 3600), "auth": (20, 3600)},      # 100/hour, 20 auth/hour
            "user": {"default": (1000, 3600), "ai": (50, 3600)},        # 1000/hour, 50 AI/hour
            "premium": {"default": (5000, 3600), "ai": (200, 3600)},    # 5000/hour, 200 AI/hour
            "admin": {"default": (10000, 3600), "ai": (1000, 3600)}     # 10000/hour, 1000 AI/hour
        }
        
        # Determine limit for this user/endpoint combination
        role_limits = rate_limits.get(user_role, rate_limits["user"])
        limit, window = role_limits.get(endpoint, role_limits["default"])
        
        cache_manager = get_cache_manager()
        return await cache_manager.check_rate_limit(
            f"{identifier}:{endpoint}",
            limit,
            window
        )


# Authentication middleware
class ZeroTrustAuthMiddleware:
    """Middleware implementing zero-trust authentication"""
    
    def __init__(self, security_manager: ZeroTrustSecurityManager):
        self.security_manager = security_manager
        self.bearer = HTTPBearer(auto_error=False)
    
    async def authenticate_request(
        self,
        request: Request,
        required_level: SecurityLevel = SecurityLevel.AUTHENTICATED
    ) -> Optional[Dict[str, Any]]:
        """Authenticate and authorize request"""
        
        # Extract device and request information
        device_info = {
            "ip": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("user-agent", ""),
            "accept_language": request.headers.get("accept-language", ""),
            "timezone": request.headers.get("x-timezone", "")
        }
        
        request_info = {
            "url": str(request.url),
            "method": request.method,
            "headers": dict(request.headers),
            "ip": device_info["ip"],
            "user_agent": device_info["user_agent"]
        }
        
        # Check for public endpoints
        if required_level == SecurityLevel.PUBLIC:
            # Still perform threat analysis for public endpoints
            threat_level = await self.security_manager._analyze_request_threat(request_info)
            if threat_level == ThreatLevel.CRITICAL:
                raise HTTPException(403, "Request blocked due to security threat")
            return {"level": "public", "threat_level": threat_level.value}
        
        # Extract and verify token
        authorization = request.headers.get("Authorization")
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "Missing or invalid authorization header")
        
        token = authorization.split(" ")[1]
        payload = await self.security_manager.verify_token(token)
        
        if not payload:
            raise HTTPException(401, "Invalid or expired token")
        
        user_id = int(payload["sub"])
        
        # Check if user tokens are revoked
        cache_manager = get_cache_manager()
        revoked_info = await cache_manager.get(f"user_tokens_revoked:{user_id}")
        if revoked_info:
            raise HTTPException(401, "Token has been revoked")
        
        # Device verification
        device_fingerprint = self.security_manager._generate_device_fingerprint(device_info)
        device_verification = await self.security_manager.verify_device(
            user_id,
            device_fingerprint,
            request_info
        )
        
        # Check if additional authentication is required
        if device_verification["requires_additional_auth"]:
            if device_verification["threat_level"] in ["high", "critical"]:
                raise HTTPException(403, "Additional authentication required")
        
        # Role-based access control
        user_roles = payload.get("roles", [])
        user_permissions = payload.get("permissions", [])
        
        if not self._check_access_level(required_level, user_roles):
            raise HTTPException(403, "Insufficient privileges")
        
        # Rate limiting
        rate_limit_result = await self.security_manager.check_advanced_rate_limit(
            f"user:{user_id}",
            request.url.path.split("/")[2] if len(request.url.path.split("/")) > 2 else "default",
            user_roles[0] if user_roles else "user"
        )
        
        if not rate_limit_result["allowed"]:
            raise HTTPException(429, "Rate limit exceeded")
        
        # Return authenticated user context
        return {
            "user_id": user_id,
            "email": payload.get("email"),
            "roles": user_roles,
            "permissions": user_permissions,
            "device_fingerprint": device_fingerprint,
            "threat_level": device_verification["threat_level"],
            "rate_limit_remaining": rate_limit_result["limit"] - rate_limit_result["current_requests"]
        }
    
    def _check_access_level(
        self,
        required_level: SecurityLevel,
        user_roles: List[str]
    ) -> bool:
        """Check if user roles meet required security level"""
        
        role_hierarchy = {
            SecurityLevel.PUBLIC: [],
            SecurityLevel.AUTHENTICATED: ["user", "premium", "admin", "super_admin"],
            SecurityLevel.VERIFIED: ["verified", "premium", "admin", "super_admin"],
            SecurityLevel.ADMIN: ["admin", "super_admin"],
            SecurityLevel.SUPER_ADMIN: ["super_admin"]
        }
        
        required_roles = role_hierarchy.get(required_level, [])
        if not required_roles:  # Public access
            return True
        
        return any(role in user_roles for role in required_roles)


# Global security manager instance
_security_manager: Optional[ZeroTrustSecurityManager] = None


def get_security_manager() -> ZeroTrustSecurityManager:
    """Get global security manager instance"""
    global _security_manager
    if _security_manager is None:
        _security_manager = ZeroTrustSecurityManager()
    return _security_manager
