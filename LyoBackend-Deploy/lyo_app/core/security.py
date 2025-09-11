"""
Enhanced password validation and security utilities for LyoApp.
Provides comprehensive password strength validation and security checks.
"""

import re
import hashlib
from typing import Tuple, List, Optional
from datetime import datetime, timedelta

from passlib.context import CryptContext
from passlib.hash import bcrypt
import secrets
import string

# Enhanced bcrypt configuration
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,  # Increased rounds for better security
    bcrypt__ident="2b"  # Use latest bcrypt variant
)


class PasswordValidator:
    """Enhanced password validation with comprehensive security checks."""
    
    # Minimum requirements
    MIN_LENGTH = 12
    MIN_UPPERCASE = 1
    MIN_LOWERCASE = 1
    MIN_DIGITS = 1
    MIN_SPECIAL = 1
    
    # Character sets
    UPPERCASE_CHARS = string.ascii_uppercase
    LOWERCASE_CHARS = string.ascii_lowercase
    DIGIT_CHARS = string.digits
    SPECIAL_CHARS = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    
    # Common passwords (subset - in production load from file)
    COMMON_PASSWORDS = {
        'password', '123456', '123456789', 'qwerty', 'abc123', 'password123',
        'admin', 'letmein', 'welcome', 'monkey', '1234567890', 'password1',
        'qwerty123', 'dragon', 'master', 'hello', 'login', 'passw0rd',
        'football', 'baseball', 'superman', 'access', 'shadow', 'trustno1'
    }
    
    # Keyboard patterns
    KEYBOARD_PATTERNS = [
        'qwerty', 'asdf', 'zxcv', '1234', '4321', 'qwertyuiop',
        'asdfghjkl', 'zxcvbnm', '1234567890', '0987654321'
    ]
    
    # Sequential patterns
    SEQUENTIAL_PATTERNS = [
        'abcd', 'bcde', 'cdef', '1234', '2345', '3456',
        'abcdefgh', '12345678'
    ]
    
    @classmethod
    def validate_password(cls, password: str, username: Optional[str] = None) -> Tuple[bool, List[str]]:
        """
        Comprehensive password validation.
        
        Args:
            password: Password to validate
            username: Username (to check for inclusion in password)
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        # Length check
        if len(password) < cls.MIN_LENGTH:
            errors.append(f"Password must be at least {cls.MIN_LENGTH} characters long")
        
        # Character composition checks
        uppercase_count = sum(1 for c in password if c in cls.UPPERCASE_CHARS)
        if uppercase_count < cls.MIN_UPPERCASE:
            errors.append(f"Password must contain at least {cls.MIN_UPPERCASE} uppercase letter(s)")
        
        lowercase_count = sum(1 for c in password if c in cls.LOWERCASE_CHARS)
        if lowercase_count < cls.MIN_LOWERCASE:
            errors.append(f"Password must contain at least {cls.MIN_LOWERCASE} lowercase letter(s)")
        
        digit_count = sum(1 for c in password if c in cls.DIGIT_CHARS)
        if digit_count < cls.MIN_DIGITS:
            errors.append(f"Password must contain at least {cls.MIN_DIGITS} digit(s)")
        
        special_count = sum(1 for c in password if c in cls.SPECIAL_CHARS)
        if special_count < cls.MIN_SPECIAL:
            errors.append(f"Password must contain at least {cls.MIN_SPECIAL} special character(s)")
        
        # Common password check
        if password.lower() in cls.COMMON_PASSWORDS:
            errors.append("Password is too common and easily guessable")
        
        # Username inclusion check
        if username and len(username) >= 3:
            if username.lower() in password.lower():
                errors.append("Password cannot contain your username")
        
        # Keyboard pattern check
        password_lower = password.lower()
        for pattern in cls.KEYBOARD_PATTERNS:
            if pattern in password_lower:
                errors.append("Password cannot contain keyboard patterns")
                break
        
        # Sequential pattern check
        for pattern in cls.SEQUENTIAL_PATTERNS:
            if pattern in password_lower:
                errors.append("Password cannot contain sequential characters")
                break
        
        # Repetitive character check
        if cls._has_repetitive_chars(password):
            errors.append("Password cannot contain repetitive character patterns")
        
        # Dictionary word check (simplified - in production use proper dictionary)
        if cls._contains_dictionary_words(password):
            errors.append("Password should not be based on dictionary words")
        
        # Calculate strength score
        strength_score = cls._calculate_strength_score(password)
        if strength_score < 70:  # Minimum strength threshold
            errors.append(f"Password strength is too low (score: {strength_score}/100)")
        
        return len(errors) == 0, errors
    
    @classmethod
    def _has_repetitive_chars(cls, password: str) -> bool:
        """Check for repetitive character patterns."""
        # Check for 3+ consecutive identical characters
        for i in range(len(password) - 2):
            if password[i] == password[i+1] == password[i+2]:
                return True
        
        # Check for repeated patterns (e.g., "123123", "abcabc")
        for length in range(2, len(password) // 2 + 1):
            for i in range(len(password) - length * 2 + 1):
                pattern = password[i:i+length]
                if password[i+length:i+length*2] == pattern:
                    return True
        
        return False
    
    @classmethod
    def _contains_dictionary_words(cls, password: str) -> bool:
        """Check if password contains common dictionary words."""
        # Simplified check - in production, use a proper dictionary
        common_words = {
            'password', 'welcome', 'hello', 'world', 'admin', 'user',
            'login', 'secret', 'private', 'public', 'system', 'computer',
            'internet', 'email', 'phone', 'address', 'name', 'birthday'
        }
        
        password_lower = password.lower()
        for word in common_words:
            if len(word) >= 4 and word in password_lower:
                return True
        
        return False
    
    @classmethod
    def _calculate_strength_score(cls, password: str) -> int:
        """Calculate password strength score (0-100)."""
        score = 0
        
        # Length bonus
        if len(password) >= 8:
            score += 10
        if len(password) >= 12:
            score += 10
        if len(password) >= 16:
            score += 10
        if len(password) >= 20:
            score += 10
        
        # Character diversity bonus
        char_types = 0
        if any(c in cls.UPPERCASE_CHARS for c in password):
            char_types += 1
        if any(c in cls.LOWERCASE_CHARS for c in password):
            char_types += 1
        if any(c in cls.DIGIT_CHARS for c in password):
            char_types += 1
        if any(c in cls.SPECIAL_CHARS for c in password):
            char_types += 1
        
        score += char_types * 10
        
        # Unique character bonus
        unique_chars = len(set(password))
        if unique_chars >= len(password) * 0.7:  # 70% unique characters
            score += 20
        
        # Pattern penalties
        if cls._has_repetitive_chars(password):
            score -= 20
        
        if password.lower() in cls.COMMON_PASSWORDS:
            score -= 30
        
        return max(0, min(100, score))
    
    @classmethod
    def generate_secure_password(cls, length: int = 16) -> str:
        """Generate a cryptographically secure password."""
        if length < cls.MIN_LENGTH:
            length = cls.MIN_LENGTH
        
        # Ensure we have at least one character from each required type
        password_chars = []
        
        # Add required characters
        password_chars.append(secrets.choice(cls.UPPERCASE_CHARS))
        password_chars.append(secrets.choice(cls.LOWERCASE_CHARS))
        password_chars.append(secrets.choice(cls.DIGIT_CHARS))
        password_chars.append(secrets.choice(cls.SPECIAL_CHARS))
        
        # Fill remaining length with random characters from all sets
        all_chars = cls.UPPERCASE_CHARS + cls.LOWERCASE_CHARS + cls.DIGIT_CHARS + cls.SPECIAL_CHARS
        for _ in range(length - 4):
            password_chars.append(secrets.choice(all_chars))
        
        # Shuffle the password
        secrets.SystemRandom().shuffle(password_chars)
        
        return ''.join(password_chars)


class PasswordHasher:
    """Enhanced password hashing utilities."""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password securely."""
        return pwd_context.hash(password)
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        try:
            return pwd_context.verify(plain_password, hashed_password)
        except Exception:
            return False
    
    @staticmethod
    def needs_update(hashed_password: str) -> bool:
        """Check if password hash needs to be updated."""
        return pwd_context.needs_update(hashed_password)
    
    @staticmethod
    def get_password_hash_info(hashed_password: str) -> dict:
        """Get information about a password hash."""
        try:
            hash_info = pwd_context.identify(hashed_password)
            return {
                "algorithm": hash_info,
                "needs_update": pwd_context.needs_update(hashed_password),
                "created_at": datetime.utcnow().isoformat()
            }
        except Exception:
            return {"algorithm": "unknown", "needs_update": True}


class PasswordPolicy:
    """Password policy enforcement."""
    
    def __init__(self):
        self.max_age_days = 90  # Password expires after 90 days
        self.history_count = 5  # Remember last 5 passwords
        self.lockout_attempts = 5  # Lock account after 5 failed attempts
        self.lockout_duration_minutes = 30  # Lock for 30 minutes
    
    def is_password_expired(self, password_created_at: datetime) -> bool:
        """Check if password has expired."""
        if not password_created_at:
            return True
        
        expiry_date = password_created_at + timedelta(days=self.max_age_days)
        return datetime.utcnow() > expiry_date
    
    def can_reuse_password(self, new_password: str, password_history: List[str]) -> bool:
        """Check if password can be reused based on history."""
        for old_hash in password_history[-self.history_count:]:
            if PasswordHasher.verify_password(new_password, old_hash):
                return False
        return True
    
    def should_lock_account(self, failed_attempts: int, last_attempt: Optional[datetime]) -> bool:
        """Check if account should be locked due to failed attempts."""
        if failed_attempts < self.lockout_attempts:
            return False
        
        if not last_attempt:
            return True
        
        # Check if lockout period has expired
        lockout_expiry = last_attempt + timedelta(minutes=self.lockout_duration_minutes)
        return datetime.utcnow() < lockout_expiry


# Global instances
password_validator = PasswordValidator()
password_hasher = PasswordHasher()
password_policy = PasswordPolicy()
