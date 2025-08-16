"""
Authentication dependencies and middleware for FastAPI
Handles JWT token validation and role-based access control
"""

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any
import logging
from datetime import datetime

from services.jwt_service import jwt_service
from database import get_users_collection, get_guards_collection, get_supervisors_collection
from models import UserRole, UserResponse

logger = logging.getLogger(__name__)

# Security scheme for JWT Bearer tokens
security = HTTPBearer(auto_error=False)


class AuthenticationError(HTTPException):
    """Custom authentication error"""
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"}
        )


class AuthorizationError(HTTPException):
    """Custom authorization error"""
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail
        )


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """
    Get current authenticated user from JWT token
    
    Args:
        credentials: HTTP Authorization credentials
        
    Returns:
        User document from database
        
    Raises:
        AuthenticationError: If token is invalid or user not found
    """
    if not credentials:
        raise AuthenticationError("Authentication required")
    
    token = credentials.credentials
    
    # Verify JWT token
    payload = jwt_service.verify_token(token, "access")
    if not payload:
        raise AuthenticationError("Invalid or expired token")
    
    user_id = payload.get("user_id")
    if not user_id:
        raise AuthenticationError("Invalid token payload")
    
    # Get user from database
    users_collection = get_users_collection()
    if not users_collection:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not available"
        )
    
    user = await users_collection.find_one({"_id": user_id})
    if not user:
        raise AuthenticationError("User not found")
    
    # Check if user is active
    if not user.get("isActive", False):
        raise AuthenticationError("Account is not active")
    
    return user


async def get_current_active_user(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Get current active user (alias for get_current_user for clarity)
    """
    return current_user


async def get_current_admin(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Require current user to be an ADMIN
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        User document if user is admin
        
    Raises:
        AuthorizationError: If user is not admin
    """
    if current_user.get("role") != UserRole.ADMIN:
        raise AuthorizationError("Admin access required")
    
    return current_user


async def get_current_supervisor(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Require current user to be a SUPERVISOR
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        User document if user is supervisor
        
    Raises:
        AuthorizationError: If user is not supervisor
    """
    if current_user.get("role") != UserRole.SUPERVISOR:
        raise AuthorizationError("Supervisor access required")
    
    return current_user


async def get_current_guard(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Require current user to be a GUARD
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        User document if user is guard
        
    Raises:
        AuthorizationError: If user is not guard
    """
    if current_user.get("role") != UserRole.GUARD:
        raise AuthorizationError("Guard access required")
    
    return current_user


async def get_admin_or_supervisor(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Require current user to be either ADMIN or SUPERVISOR
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        User document if user is admin or supervisor
        
    Raises:
        AuthorizationError: If user is neither admin nor supervisor
    """
    if current_user.get("role") not in [UserRole.ADMIN, UserRole.SUPERVISOR]:
        raise AuthorizationError("Admin or Supervisor access required")
    
    return current_user


async def get_supervisor_with_details(current_user: Dict[str, Any] = Depends(get_current_supervisor)) -> Dict[str, Any]:
    """
    Get supervisor with complete details including supervisor record
    
    Args:
        current_user: Current authenticated supervisor user
        
    Returns:
        User document with supervisor details
    """
    supervisors_collection = get_supervisors_collection()
    if not supervisors_collection:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not available"
        )
    
    supervisor_record = await supervisors_collection.find_one({"userId": str(current_user["_id"])})
    if not supervisor_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supervisor record not found"
        )
    
    # Add supervisor details to user object
    current_user["supervisor"] = supervisor_record
    return current_user


async def get_guard_with_details(current_user: Dict[str, Any] = Depends(get_current_guard)) -> Dict[str, Any]:
    """
    Get guard with complete details including guard record
    
    Args:
        current_user: Current authenticated guard user
        
    Returns:
        User document with guard details
    """
    guards_collection = get_guards_collection()
    if not guards_collection:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not available"
        )
    
    guard_record = await guards_collection.find_one({"userId": str(current_user["_id"])})
    if not guard_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Guard record not found"
        )
    
    # Add guard details to user object
    current_user["guard"] = guard_record
    return current_user


# Optional authentication (for some endpoints that work with or without auth)
async def get_current_user_optional(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Optional[Dict[str, Any]]:
    """
    Get current user if token is provided, otherwise return None
    
    Args:
        credentials: Optional HTTP Authorization credentials
        
    Returns:
        User document if authenticated, None otherwise
    """
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


def require_roles(*allowed_roles: UserRole):
    """
    Create a dependency that requires one of the specified roles
    
    Args:
        allowed_roles: List of allowed user roles
        
    Returns:
        FastAPI dependency function
    """
    async def role_checker(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        user_role = current_user.get("role")
        if user_role not in allowed_roles:
            role_names = [role.value for role in allowed_roles]
            raise AuthorizationError(f"Access denied. Required roles: {', '.join(role_names)}")
        return current_user
    
    return role_checker


# Rate limiting helper (can be used with slowapi)
async def get_client_ip(request: Request) -> str:
    """
    Get client IP address for rate limiting
    
    Args:
        request: FastAPI request object
        
    Returns:
        Client IP address
    """
    # Check for forwarded headers first (for reverse proxies)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    
    # Fallback to direct client IP
    return request.client.host if request.client else "unknown"


# Utility functions for token management
async def revoke_user_tokens(user_id: str) -> bool:
    """
    Revoke all refresh tokens for a user (used for logout)
    
    Args:
        user_id: User ID to revoke tokens for
        
    Returns:
        True if successful, False otherwise
    """
    try:
        from database import get_refresh_tokens_collection
        
        refresh_tokens_collection = get_refresh_tokens_collection()
        if not refresh_tokens_collection:
            return False
        
        # Mark all user's refresh tokens as revoked
        result = await refresh_tokens_collection.update_many(
            {"userId": user_id, "revoked": False},
            {"$set": {"revoked": True, "updatedAt": datetime.utcnow()}}
        )
        
        logger.info(f"Revoked {result.modified_count} refresh tokens for user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to revoke tokens for user {user_id}: {e}")
        return False


def create_access_token_data(user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create token payload data for a user
    
    Args:
        user: User document from database
        
    Returns:
        Token payload data
    """
    return {
        "user_id": str(user["_id"]),
        "email": user["email"],
        "role": user["role"],
        "name": user["name"]
    }
