"""
Enhanced base API client with rate limiting, retries, and caching.
Provides a robust foundation for external API integrations.
"""

import asyncio
import hashlib
import json
import time
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
import logging

from lyo_app.core.config import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token bucket rate limiter for API calls."""
    
    def __init__(self, rate: int, per: int):
        """
        Initialize rate limiter.
        
        Args:
            rate: Number of tokens allowed
            per: Time period in seconds
        """
        self.rate = rate
        self.per = per
        self.buckets = defaultdict(lambda: {"tokens": rate, "last_refill": time.time()})
    
    async def acquire(self, key: str = "default") -> bool:
        """
        Acquire a token from the bucket.
        
        Args:
            key: Bucket identifier for different rate limits
            
        Returns:
            bool: True if token acquired, False otherwise
        """
        bucket = self.buckets[key]
        current_time = time.time()
        
        # Refill tokens based on time passed
        time_passed = current_time - bucket["last_refill"]
        bucket["tokens"] = min(
            self.rate,
            bucket["tokens"] + (time_passed * self.rate / self.per)
        )
        bucket["last_refill"] = current_time
        
        if bucket["tokens"] >= 1:
            bucket["tokens"] -= 1
            return True
        
        # Calculate wait time for next token
        wait_time = (1 - bucket["tokens"]) * self.per / self.rate
        await asyncio.sleep(wait_time)
        return await self.acquire(key)
    
    def get_remaining_tokens(self, key: str = "default") -> float:
        """Get remaining tokens in bucket."""
        bucket = self.buckets[key]
        current_time = time.time()
        time_passed = current_time - bucket["last_refill"]
        
        return min(
            self.rate,
            bucket["tokens"] + (time_passed * self.rate / self.per)
        )


class APIClientError(Exception):
    """Base exception for API client errors."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict] = None):
        self.message = message
        self.status_code = status_code
        self.response_data = response_data or {}
        super().__init__(message)


class RateLimitError(APIClientError):
    """Rate limit exceeded error."""
    
    def __init__(self, retry_after: Optional[int] = None):
        message = f"Rate limit exceeded. Retry after {retry_after} seconds" if retry_after else "Rate limit exceeded"
        super().__init__(message, 429)
        self.retry_after = retry_after


class QuotaExceededError(APIClientError):
    """API quota exceeded error."""
    
    def __init__(self, service: str, quota_type: str = "daily"):
        super().__init__(f"{service} {quota_type} quota exceeded", 429)
        self.service = service
        self.quota_type = quota_type


class BaseAPIClient:
    """
    Enhanced base API client with rate limiting, retries, and error handling.
    """
    
    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        rate_limit: Tuple[int, int] = (60, 60),  # 60 requests per 60 seconds
        timeout: int = 30,
        max_retries: int = 3,
        user_agent: str = "LyoApp/1.0"
    ):
        """
        Initialize API client.
        
        Args:
            base_url: Base URL for the API
            api_key: API key for authentication
            rate_limit: Tuple of (requests, seconds) for rate limiting
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries
            user_agent: User agent string
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.rate_limiter = RateLimiter(*rate_limit)
        self.timeout = timeout
        self.max_retries = max_retries
        self.user_agent = user_agent
        self._client = None
        self._session_stats = {
            "requests_made": 0,
            "requests_failed": 0,
            "cache_hits": 0,
            "rate_limit_hits": 0
        }
    
    async def __aenter__(self):
        """Async context manager entry."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers=self._get_default_headers()
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            
        # Log session statistics
        logger.info(
            f"API client session ended. Stats: {self._session_stats}"
        )
    
    def _get_default_headers(self) -> Dict[str, str]:
        """Get default headers for requests."""
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        if self.api_key:
            # Common API key header patterns
            if "youtube" in self.base_url.lower():
                # YouTube uses query parameter, not header
                pass
            elif "openai" in self.base_url.lower():
                headers["Authorization"] = f"Bearer {self.api_key}"
            elif "anthropic" in self.base_url.lower():
                headers["x-api-key"] = self.api_key
            else:
                # Default to Authorization header
                headers["Authorization"] = f"Bearer {self.api_key}"
        
        return headers
    
    def _cache_key(self, method: str, endpoint: str, **params) -> str:
        """Generate cache key for request."""
        cache_data = {
            "method": method,
            "endpoint": endpoint,
            "params": params
        }
        key_string = json.dumps(cache_data, sort_keys=True)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> httpx.Response:
        """
        Make HTTP request with retry logic and rate limiting.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            headers: Additional headers
            **kwargs: Additional request parameters
            
        Returns:
            httpx.Response: HTTP response
            
        Raises:
            APIClientError: For various API errors
        """
        # Rate limiting
        await self.rate_limiter.acquire()
        
        # Merge headers
        request_headers = self._get_default_headers()
        if headers:
            request_headers.update(headers)
        
        # Prepare full URL
        url = endpoint if endpoint.startswith('http') else f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            self._session_stats["requests_made"] += 1
            
            response = await self._client.request(
                method,
                url,
                headers=request_headers,
                **kwargs
            )
            
            # Handle rate limiting
            if response.status_code == 429:
                self._session_stats["rate_limit_hits"] += 1
                retry_after = int(response.headers.get("Retry-After", 60))
                logger.warning(f"Rate limit hit for {url}. Retry after {retry_after} seconds")
                raise RateLimitError(retry_after)
            
            # Handle quota exceeded (YouTube returns 403 for quota)
            if response.status_code == 403 and "quota" in response.text.lower():
                service_name = self.base_url.split("//")[1].split(".")[0]
                raise QuotaExceededError(service_name)
            
            # Handle other HTTP errors
            if response.status_code >= 400:
                error_data = {}
                try:
                    error_data = response.json()
                except:
                    error_data = {"detail": response.text}
                
                raise APIClientError(
                    f"API request failed: {response.status_code}",
                    response.status_code,
                    error_data
                )
            
            return response
            
        except httpx.RequestError as e:
            self._session_stats["requests_failed"] += 1
            logger.error(f"Request error for {url}: {e}")
            raise APIClientError(f"Request failed: {str(e)}")
        except httpx.HTTPStatusError as e:
            self._session_stats["requests_failed"] += 1
            logger.error(f"HTTP error for {url}: {e}")
            raise APIClientError(f"HTTP error: {e.response.status_code}")
    
    async def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        cache_ttl: Optional[timedelta] = None
    ) -> Dict[str, Any]:
        """
        Make GET request.
        
        Args:
            endpoint: API endpoint
            params: Query parameters
            headers: Additional headers
            cache_ttl: Cache time-to-live
            
        Returns:
            Dict: JSON response data
        """
        response = await self._make_request(
            "GET",
            endpoint,
            headers=headers,
            params=params
        )
        return response.json()
    
    async def post(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Make POST request.
        
        Args:
            endpoint: API endpoint
            data: Form data
            json_data: JSON data
            headers: Additional headers
            
        Returns:
            Dict: JSON response data
        """
        kwargs = {}
        if data:
            kwargs["data"] = data
        if json_data:
            kwargs["json"] = json_data
        
        response = await self._make_request(
            "POST",
            endpoint,
            headers=headers,
            **kwargs
        )
        return response.json()
    
    async def put(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Make PUT request."""
        kwargs = {}
        if data:
            kwargs["data"] = data
        if json_data:
            kwargs["json"] = json_data
        
        response = await self._make_request(
            "PUT",
            endpoint,
            headers=headers,
            **kwargs
        )
        return response.json()
    
    async def delete(
        self,
        endpoint: str,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Make DELETE request."""
        response = await self._make_request(
            "DELETE",
            endpoint,
            headers=headers
        )
        
        # Handle empty responses
        try:
            return response.json()
        except:
            return {"status": "deleted"}
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client session statistics."""
        return {
            **self._session_stats,
            "rate_limit_remaining": self.rate_limiter.get_remaining_tokens(),
            "base_url": self.base_url
        }
