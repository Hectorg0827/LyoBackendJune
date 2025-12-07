"""
Input validation and security utilities.
Provides functions to sanitize input and prevent common security vulnerabilities.
"""

import re
import hashlib
from typing import Any, Dict, List, Union
import bleach
from pydantic import field_validator


def sanitize_input(data: Any) -> Any:
    """
    Sanitize input data to prevent XSS and injection attacks.
    
    Args:
        data: Input data of any type
        
    Returns:
        Sanitized data
    """
    if isinstance(data, str):
        # Remove HTML tags and scripts, allow only safe content
        return bleach.clean(data, tags=[], strip=True).strip()
    elif isinstance(data, dict):
        return {key: sanitize_input(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [sanitize_input(item) for item in data]
    else:
        return data


def validate_sql_query(query: str) -> bool:
    """
    Validate SQL query for potential injection attempts.
    
    Args:
        query: SQL query string to validate
        
    Returns:
        True if query appears safe, False otherwise
    """
    if not query or not isinstance(query, str):
        return False
        
    # Dangerous SQL patterns that could indicate injection
    dangerous_patterns = [
        r';.*--',           # SQL comment injection
        r'union.*select',   # Union-based injection
        r'drop.*table',     # Drop table attempts
        r'delete.*from',    # Delete injection
        r'insert.*into',    # Insert injection
        r'update.*set',     # Update injection
        r'exec.*\(',        # Stored procedure execution
        r'script.*>',       # Script injection
        r'<.*script',       # Script tag injection
    ]
    
    query_lower = query.lower()
    for pattern in dangerous_patterns:
        if re.search(pattern, query_lower):
            return False
    
    return True


def get_safe_token_for_logging(token: str) -> str:
    """
    Get a safe version of token for logging purposes.
    
    Args:
        token: Sensitive token string
        
    Returns:
        Hashed version safe for logging
    """
    if not token:
        return "empty_token"
    
    return hashlib.sha256(token.encode()).hexdigest()[:12]


def validate_email_format(email: str) -> bool:
    """
    Validate email format using regex.
    
    Args:
        email: Email address to validate
        
    Returns:
        True if email format is valid
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_password_strength(password: str) -> Dict[str, Union[bool, List[str]]]:
    """
    Validate password strength and return detailed feedback.
    
    Args:
        password: Password to validate
        
    Returns:
        Dictionary with validation results and issues
    """
    issues = []
    
    if len(password) < 8:
        issues.append("Password must be at least 8 characters long")
    
    if not re.search(r'[A-Z]', password):
        issues.append("Password must contain at least one uppercase letter")
    
    if not re.search(r'[a-z]', password):
        issues.append("Password must contain at least one lowercase letter")
    
    if not re.search(r'\d', password):
        issues.append("Password must contain at least one digit")
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        issues.append("Password must contain at least one special character")
    
    return {
        "is_valid": len(issues) == 0,
        "issues": issues
    }


def validate_username(username: str) -> Dict[str, Union[bool, str]]:
    """
    Validate username format and length.
    
    Args:
        username: Username to validate
        
    Returns:
        Dictionary with validation results
    """
    if not username:
        return {"is_valid": False, "message": "Username cannot be empty"}
    
    if len(username) < 3:
        return {"is_valid": False, "message": "Username must be at least 3 characters long"}
    
    if len(username) > 50:
        return {"is_valid": False, "message": "Username must be less than 50 characters"}
    
    if not re.match(r'^[a-zA-Z0-9_.-]+$', username):
        return {"is_valid": False, "message": "Username can only contain letters, numbers, dots, dashes, and underscores"}
    
    return {"is_valid": True, "message": "Username is valid"}


class SecurityValidators:
    """Pydantic validators for security."""
    
    @field_validator('password')
    def validate_password(cls, v):
        """Validate password strength."""
        if not v:
            raise ValueError("Password cannot be empty")
        
        validation = validate_password_strength(v)
        if not validation["is_valid"]:
            raise ValueError(f"Password validation failed: {', '.join(validation['issues'])}")
        
        return v
    
    @field_validator('email')
    def validate_email(cls, v):
        """Validate email format."""
        if not validate_email_format(v):
            raise ValueError("Invalid email format")
        return v.lower()
    
    @field_validator('username')
    def validate_username_field(cls, v):
        """Validate username."""
        validation = validate_username(v)
        if not validation["is_valid"]:
            raise ValueError(validation["message"])
        return v


def rate_limit_key(user_id: str, endpoint: str) -> str:
    """
    Generate a rate limiting key for Redis.
    
    Args:
        user_id: User identifier
        endpoint: API endpoint being accessed
        
    Returns:
        Rate limiting key
    """
    return f"rate_limit:{user_id}:{endpoint}"


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal attacks.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    if not filename:
        return "unnamed_file"
    
    # Remove path separators and dangerous characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    filename = re.sub(r'\.\.', '', filename)  # Remove path traversal
    filename = filename.strip('. ')  # Remove leading/trailing dots and spaces
    
    if not filename:
        return "unnamed_file"
    
    return filename[:255]  # Limit length
