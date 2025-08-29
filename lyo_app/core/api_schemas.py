"""
Standardized API Response Schema Module
--------------------------------------
Provides consistent API response structures and serialization helpers.
This ensures that all API endpoints return responses in a consistent format
with proper metadata, pagination, and error handling.
"""

from enum import Enum
from typing import Any, Dict, Generic, List, Optional, TypeVar, Union, Sequence
from datetime import datetime

from fastapi import status
from pydantic import BaseModel, Field, model_validator


# Generic type for data content
T = TypeVar('T')


class ResponseStatus(str, Enum):
    """Status codes for API responses."""
    
    SUCCESS = "success"
    ERROR = "error"
    PARTIAL = "partial"


class ErrorDetail(BaseModel):
    """Detailed error information."""
    
    message: str = Field(..., description="Error message")
    code: str = Field(..., description="Error code")
    field: Optional[str] = Field(None, description="Field that caused the error")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")


class PaginationMeta(BaseModel):
    """Pagination metadata."""
    
    page: int = Field(..., description="Current page number")
    size: int = Field(..., description="Items per page")
    total: int = Field(..., description="Total number of items")
    pages: int = Field(..., description="Total number of pages")
    has_next: bool = Field(..., description="Whether there is a next page")
    has_prev: bool = Field(..., description="Whether there is a previous page")
    next_page: Optional[int] = Field(None, description="Next page number")
    prev_page: Optional[int] = Field(None, description="Previous page number")


class ResponseMeta(BaseModel):
    """Common response metadata."""
    
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")
    code: int = Field(..., description="HTTP status code")
    request_id: Optional[str] = Field(None, description="Request ID for tracking")
    pagination: Optional[PaginationMeta] = Field(None, description="Pagination metadata")
    
    @model_validator(mode="after")
    def set_defaults(self):
        """Set defaults for timestamps."""
        if not self.timestamp:
            self.timestamp = datetime.utcnow()
        return self


class APIResponse(BaseModel, Generic[T]):
    """Standard API response structure."""
    
    status: ResponseStatus = Field(ResponseStatus.SUCCESS, description="Response status")
    meta: ResponseMeta = Field(..., description="Response metadata")
    data: Optional[T] = Field(None, description="Response data")
    errors: Optional[List[ErrorDetail]] = Field(None, description="Error details")
    
    @classmethod
    def success(
        cls,
        data: T,
        code: int = status.HTTP_200_OK,
        request_id: Optional[str] = None,
        pagination: Optional[PaginationMeta] = None,
    ) -> "APIResponse[T]":
        """Create a success response."""
        return cls(
            status=ResponseStatus.SUCCESS,
            meta=ResponseMeta(
                code=code,
                request_id=request_id,
                pagination=pagination,
            ),
            data=data,
        )
    
    @classmethod
    def error(
        cls,
        errors: Union[List[ErrorDetail], ErrorDetail],
        code: int = status.HTTP_400_BAD_REQUEST,
        request_id: Optional[str] = None,
    ) -> "APIResponse[None]":
        """Create an error response."""
        if isinstance(errors, ErrorDetail):
            errors = [errors]
            
        return cls(
            status=ResponseStatus.ERROR,
            meta=ResponseMeta(
                code=code,
                request_id=request_id,
            ),
            errors=errors,
        )
    
    @classmethod
    def partial(
        cls,
        data: T,
        errors: List[ErrorDetail],
        code: int = status.HTTP_207_MULTI_STATUS,
        request_id: Optional[str] = None,
    ) -> "APIResponse[T]":
        """Create a partial success response."""
        return cls(
            status=ResponseStatus.PARTIAL,
            meta=ResponseMeta(
                code=code,
                request_id=request_id,
            ),
            data=data,
            errors=errors,
        )


class PaginatedResponse(APIResponse, Generic[T]):
    """Paginated API response."""
    
    @classmethod
    def create(
        cls,
        items: Sequence[T],
        total: int,
        page: int,
        size: int,
        request_id: Optional[str] = None,
    ) -> "PaginatedResponse[List[T]]":
        """Create a paginated response."""
        pages = (total + size - 1) // size if size > 0 else 0
        has_next = page < pages
        has_prev = page > 1
        
        pagination = PaginationMeta(
            page=page,
            size=size,
            total=total,
            pages=pages,
            has_next=has_next,
            has_prev=has_prev,
            next_page=page + 1 if has_next else None,
            prev_page=page - 1 if has_prev else None,
        )
        
        return cls(
            status=ResponseStatus.SUCCESS,
            meta=ResponseMeta(
                code=status.HTTP_200_OK,
                request_id=request_id,
                pagination=pagination,
            ),
            data=list(items),
        )


def create_success_response(
    data: Any,
    code: int = status.HTTP_200_OK,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a success response dictionary."""
    return APIResponse.success(
        data=data,
        code=code,
        request_id=request_id,
    ).model_dump()


def create_error_response(
    message: str,
    error_code: str,
    status_code: int = status.HTTP_400_BAD_REQUEST,
    field: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create an error response dictionary."""
    error = ErrorDetail(
        message=message,
        code=error_code,
        field=field,
        details=details,
    )
    
    return APIResponse.error(
        errors=[error],
        code=status_code,
        request_id=request_id,
    ).model_dump()


def create_paginated_response(
    items: Sequence[Any],
    total: int,
    page: int,
    size: int,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a paginated response dictionary."""
    return PaginatedResponse.create(
        items=items,
        total=total,
        page=page,
        size=size,
        request_id=request_id,
    ).model_dump()


__all__ = [
    "ResponseStatus",
    "ErrorDetail",
    "PaginationMeta",
    "ResponseMeta",
    "APIResponse",
    "PaginatedResponse",
    "create_success_response",
    "create_error_response",
    "create_paginated_response",
]
