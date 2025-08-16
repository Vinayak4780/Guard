"""
Authentication routes for Email-OTP signup, login, and JWT token management
Supports signup with email verification, login with JWT tokens, and password reset
"""

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from typing import Dict, Any
from datetime import datetime, timedelta
import logging
from bson import ObjectId

# Import services and dependencies
from services.jwt_service import jwt_service
from services.email_service import email_service
from services.auth_service import get_current_user, revoke_user_tokens, create_access_token_data
from database import (
    get_users_collection, get_supervisors_collection, get_guards_collection,
    get_otp_tokens_collection, get_refresh_tokens_collection
)
from config import settings

# Import models
from models import (
    SignupRequest, VerifyOTPRequest, LoginRequest, 
    ResetPasswordRequest, ResetPasswordConfirmRequest,
    LoginResponse, TokenResponse, UserResponse, SuccessResponse,
    UserRole, OTPPurpose
)

logger = logging.getLogger(__name__)

# Create router
auth_router = APIRouter()


async def generate_and_send_otp(email: str, purpose: OTPPurpose) -> bool:
    """
    Generate OTP, store hash in database, and send email
    
    Args:
        email: User email address
        purpose: OTP purpose (SIGNUP or RESET)
        
    Returns:
        True if OTP sent successfully, False otherwise
    """
    try:
        # Check rate limiting - allow one OTP per minute per email
        otp_collection = get_otp_tokens_collection()
        if not otp_collection:
            return False
        
        # Check for recent OTP requests
        recent_otp = await otp_collection.find_one({
            "email": email,
            "purpose": purpose.value,
            "createdAt": {"$gte": datetime.utcnow() - timedelta(minutes=settings.OTP_RATE_LIMIT_MINUTES)}
        })
        
        if recent_otp:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {settings.OTP_RATE_LIMIT_MINUTES} minute(s) before requesting another OTP"
            )
        
        # Generate OTP
        otp = jwt_service.generate_otp()
        otp_hash = jwt_service.hash_otp(otp)
        
        # Store OTP in database
        expires_at = datetime.utcnow() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)
        
        otp_data = {
            "email": email,
            "otpHash": otp_hash,
            "purpose": purpose.value,
            "expiresAt": expires_at,
            "attempts": 0,
            "createdAt": datetime.utcnow()
        }
        
        # Remove any existing OTP for this email and purpose
        await otp_collection.delete_many({"email": email, "purpose": purpose.value})
        
        # Insert new OTP
        await otp_collection.insert_one(otp_data)
        
        # Send email
        purpose_text = "verification" if purpose == OTPPurpose.SIGNUP else "reset"
        email_sent = await email_service.send_otp_email(email, otp, purpose_text)
        
        if not email_sent:
            # Clean up if email failed
            await otp_collection.delete_one({"email": email, "purpose": purpose.value})
            return False
        
        logger.info(f"OTP sent for {purpose.value} to {email}")
        return True
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate and send OTP: {e}")
        return False


async def verify_otp_code(email: str, otp: str, purpose: OTPPurpose) -> bool:
    """
    Verify OTP code against stored hash
    
    Args:
        email: User email address
        otp: OTP code to verify
        purpose: OTP purpose (SIGNUP or RESET)
        
    Returns:
        True if OTP is valid, False otherwise
    """
    try:
        otp_collection = get_otp_tokens_collection()
        if not otp_collection:
            return False
        
        # Find OTP record
        otp_record = await otp_collection.find_one({
            "email": email,
            "purpose": purpose.value
        })
        
        if not otp_record:
            return False
        
        # Check if OTP has expired
        if datetime.utcnow() > otp_record["expiresAt"]:
            await otp_collection.delete_one({"_id": otp_record["_id"]})
            return False
        
        # Check attempt limit
        if otp_record["attempts"] >= settings.OTP_MAX_ATTEMPTS:
            await otp_collection.delete_one({"_id": otp_record["_id"]})
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Maximum OTP attempts exceeded. Please request a new OTP."
            )
        
        # Verify OTP
        if jwt_service.verify_otp(otp, otp_record["otpHash"]):
            # OTP is valid - remove it
            await otp_collection.delete_one({"_id": otp_record["_id"]})
            return True
        else:
            # Increment attempt counter
            await otp_collection.update_one(
                {"_id": otp_record["_id"]},
                {"$inc": {"attempts": 1}}
            )
            return False
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to verify OTP: {e}")
        return False


@auth_router.post("/signup", response_model=SuccessResponse)
async def signup(signup_data: SignupRequest):
    """
    Email signup with OTP verification
    User account is created but remains inactive until email is verified
    """
    try:
        users_collection = get_users_collection()
        if not users_collection:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Check if user already exists
        existing_user = await users_collection.find_one({"email": signup_data.email})
        if existing_user:
            # If user exists but is inactive, allow re-signup (resend OTP)
            if existing_user.get("isActive", False):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="User with this email already exists and is active"
                )
            else:
                # Delete inactive user to allow fresh signup
                await users_collection.delete_one({"email": signup_data.email})
        
        # Create user record (inactive)
        user_data = {
            "email": signup_data.email,
            "passwordHash": jwt_service.hash_password(signup_data.password),
            "name": signup_data.name,
            "role": signup_data.role.value,
            "areaCity": signup_data.areaCity,
            "isActive": False,  # Inactive until email verified
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
        
        result = await users_collection.insert_one(user_data)
        
        # Generate and send OTP
        otp_sent = await generate_and_send_otp(signup_data.email, OTPPurpose.SIGNUP)
        
        if not otp_sent:
            # Cleanup user if OTP failed
            await users_collection.delete_one({"_id": result.inserted_id})
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send verification email. Please try again."
            )
        
        return SuccessResponse(
            message=f"Signup successful! Please check your email for verification code. OTP expires in {settings.OTP_EXPIRE_MINUTES} minutes.",
            data={"email": signup_data.email}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signup error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during signup"
        )


@auth_router.post("/verify-otp", response_model=LoginResponse)
async def verify_otp(verify_data: VerifyOTPRequest):
    """
    Verify OTP and activate user account
    Returns JWT tokens upon successful verification
    """
    try:
        # Verify OTP
        otp_valid = await verify_otp_code(verify_data.email, verify_data.otp, OTPPurpose.SIGNUP)
        
        if not otp_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired OTP"
            )
        
        users_collection = get_users_collection()
        if not users_collection:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Activate user account
        user = await users_collection.find_one_and_update(
            {"email": verify_data.email, "isActive": False},
            {
                "$set": {
                    "isActive": True,
                    "updatedAt": datetime.utcnow(),
                    "lastLogin": datetime.utcnow()
                }
            },
            return_document=True
        )
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found or already activated"
            )
        
        # Create supervisor/guard record if needed
        await create_role_specific_record(user)
        
        # Generate JWT tokens
        token_data = create_access_token_data(user)
        access_token = jwt_service.create_access_token(token_data)
        refresh_token = jwt_service.create_refresh_token(str(user["_id"]))
        
        # Store refresh token in database
        await store_refresh_token(str(user["_id"]), refresh_token)
        
        # Send welcome email
        await email_service.send_welcome_email(user["email"], user["name"], user["role"])
        
        # Prepare response
        user_response = UserResponse(
            id=str(user["_id"]),
            email=user["email"],
            name=user["name"],
            role=UserRole(user["role"]),
            areaCity=user.get("areaCity"),
            isActive=user["isActive"],
            createdAt=user["createdAt"],
            updatedAt=user["updatedAt"],
            lastLogin=user.get("lastLogin")
        )
        
        tokens = TokenResponse(
            accessToken=access_token,
            refreshToken=refresh_token,
            expiresIn=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
        
        return LoginResponse(
            user=user_response,
            tokens=tokens,
            message="Email verified successfully! Welcome to Guard Management System."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OTP verification error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during verification"
        )


@auth_router.post("/login", response_model=LoginResponse)
async def login(login_data: LoginRequest):
    """
    Login with email and password
    Returns JWT tokens for authenticated users
    """
    try:
        users_collection = get_users_collection()
        if not users_collection:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Find user by email
        user = await users_collection.find_one({"email": login_data.email})
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        # Check password
        if not jwt_service.verify_password(login_data.password, user["passwordHash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        # Check if user is active
        if not user.get("isActive", False):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account not activated. Please verify your email first."
            )
        
        # Update last login
        await users_collection.update_one(
            {"_id": user["_id"]},
            {"$set": {"lastLogin": datetime.utcnow()}}
        )
        user["lastLogin"] = datetime.utcnow()
        
        # Generate JWT tokens
        token_data = create_access_token_data(user)
        access_token = jwt_service.create_access_token(token_data)
        refresh_token = jwt_service.create_refresh_token(str(user["_id"]))
        
        # Store refresh token in database
        await store_refresh_token(str(user["_id"]), refresh_token)
        
        # Prepare response
        user_response = UserResponse(
            id=str(user["_id"]),
            email=user["email"],
            name=user["name"],
            role=UserRole(user["role"]),
            areaCity=user.get("areaCity"),
            isActive=user["isActive"],
            createdAt=user["createdAt"],
            updatedAt=user["updatedAt"],
            lastLogin=user.get("lastLogin")
        )
        
        tokens = TokenResponse(
            accessToken=access_token,
            refreshToken=refresh_token,
            expiresIn=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
        
        return LoginResponse(
            user=user_response,
            tokens=tokens,
            message="Login successful"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during login"
        )


@auth_router.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    OAuth2 compatible login endpoint for Swagger UI Authorize button
    Use your email as username and your password
    """
    try:
        users_collection = get_users_collection()
        if not users_collection:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Find user by email (form_data.username contains the email)
        user = await users_collection.find_one({"email": form_data.username})
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Check password
        if not jwt_service.verify_password(form_data.password, user["passwordHash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Check if user is active
        if not user.get("isActive", False):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account not activated. Please verify your email first.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Update last login
        await users_collection.update_one(
            {"_id": user["_id"]},
            {"$set": {"lastLogin": datetime.utcnow()}}
        )
        
        # Generate JWT token
        token_data = create_access_token_data(user)
        access_token = jwt_service.create_access_token(token_data)
        
        # Return OAuth2 compatible response
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user_role": user.get("role"),
            "user_email": user.get("email")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth2 login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during login"
        )


@auth_router.post("/logout", response_model=SuccessResponse)
async def logout(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Logout user by revoking all refresh tokens
    """
    try:
        user_id = str(current_user["_id"])
        success = await revoke_user_tokens(user_id)
        
        if success:
            return SuccessResponse(message="Logout successful")
        else:
            return SuccessResponse(message="Logout completed (some tokens may still be valid until expiry)")
            
    except Exception as e:
        logger.error(f"Logout error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during logout"
        )


@auth_router.post("/refresh", response_model=TokenResponse)
async def refresh_token(refresh_token: str):
    """
    Refresh access token using refresh token
    """
    try:
        # Verify refresh token
        payload = jwt_service.verify_token(refresh_token, "refresh")
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token"
            )
        
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload"
            )
        
        # Check if refresh token is valid in database
        refresh_tokens_collection = get_refresh_tokens_collection()
        if refresh_tokens_collection:
            token_hash = jwt_service.generate_refresh_token_hash(refresh_token)
            stored_token = await refresh_tokens_collection.find_one({
                "tokenHash": token_hash,
                "userId": user_id,
                "revoked": False
            })
            
            if not stored_token:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token has been revoked"
                )
        
        # Get user data
        users_collection = get_users_collection()
        if not users_collection:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        user = await users_collection.find_one({"_id": ObjectId(user_id)})
        if not user or not user.get("isActive", False):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )
        
        # Generate new access token
        token_data = create_access_token_data(user)
        new_access_token = jwt_service.create_access_token(token_data)
        
        return TokenResponse(
            accessToken=new_access_token,
            refreshToken=refresh_token,  # Keep same refresh token
            expiresIn=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during token refresh"
        )


@auth_router.post("/reset-password", response_model=SuccessResponse)
async def reset_password(reset_data: ResetPasswordRequest):
    """
    Request password reset via email OTP
    """
    try:
        users_collection = get_users_collection()
        if not users_collection:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Check if user exists and is active
        user = await users_collection.find_one({
            "email": reset_data.email,
            "isActive": True
        })
        
        if not user:
            # Don't reveal if email exists or not for security
            return SuccessResponse(
                message="If the email exists, a password reset code has been sent."
            )
        
        # Generate and send OTP
        otp_sent = await generate_and_send_otp(reset_data.email, OTPPurpose.RESET)
        
        if not otp_sent:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send reset email. Please try again."
            )
        
        return SuccessResponse(
            message=f"Password reset code sent! Please check your email. Code expires in {settings.OTP_EXPIRE_MINUTES} minutes."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password reset request error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during password reset request"
        )


@auth_router.post("/reset-password-confirm", response_model=SuccessResponse)
async def reset_password_confirm(reset_data: ResetPasswordConfirmRequest):
    """
    Confirm password reset with OTP and new password
    """
    try:
        # Verify OTP
        otp_valid = await verify_otp_code(reset_data.email, reset_data.otp, OTPPurpose.RESET)
        
        if not otp_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired OTP"
            )
        
        users_collection = get_users_collection()
        if not users_collection:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Update password
        new_password_hash = jwt_service.hash_password(reset_data.newPassword)
        
        result = await users_collection.update_one(
            {"email": reset_data.email, "isActive": True},
            {
                "$set": {
                    "passwordHash": new_password_hash,
                    "updatedAt": datetime.utcnow()
                }
            }
        )
        
        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Revoke all refresh tokens for security
        user = await users_collection.find_one({"email": reset_data.email})
        if user:
            await revoke_user_tokens(str(user["_id"]))
        
        return SuccessResponse(
            message="Password reset successful! Please login with your new password."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password reset confirmation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during password reset"
        )


@auth_router.post("/resend-otp", response_model=SuccessResponse)
async def resend_otp(email: str, purpose: str = "signup"):
    """
    Resend OTP for signup or password reset
    """
    try:
        otp_purpose = OTPPurpose.SIGNUP if purpose.lower() == "signup" else OTPPurpose.RESET
        
        # For signup, check if user exists and is inactive
        if otp_purpose == OTPPurpose.SIGNUP:
            users_collection = get_users_collection()
            if users_collection:
                user = await users_collection.find_one({"email": email})
                if not user:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="No pending signup found for this email"
                    )
                if user.get("isActive", False):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Email already verified"
                    )
        
        # Generate and send OTP
        otp_sent = await generate_and_send_otp(email, otp_purpose)
        
        if not otp_sent:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send OTP. Please try again."
            )
        
        purpose_text = "verification" if otp_purpose == OTPPurpose.SIGNUP else "password reset"
        return SuccessResponse(
            message=f"New {purpose_text} code sent! Please check your email."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Resend OTP error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during OTP resend"
        )


# Helper functions

async def create_role_specific_record(user: Dict[str, Any]):
    """Create supervisor or guard record based on user role"""
    try:
        if user["role"] == UserRole.SUPERVISOR:
            supervisors_collection = get_supervisors_collection()
            if supervisors_collection:
                # Generate supervisor code
                count = await supervisors_collection.count_documents({})
                supervisor_code = f"SUP{str(count + 1).zfill(3)}"
                
                supervisor_data = {
                    "userId": str(user["_id"]),
                    "code": supervisor_code,
                    "areaCity": user.get("areaCity", ""),
                    "createdAt": datetime.utcnow(),
                    "updatedAt": datetime.utcnow()
                }
                
                await supervisors_collection.insert_one(supervisor_data)
                logger.info(f"Created supervisor record: {supervisor_code}")
        
        elif user["role"] == UserRole.GUARD:
            guards_collection = get_guards_collection()
            if guards_collection:
                # Note: supervisorId should be set when admin assigns guard to supervisor
                # For now, create basic record without supervisor assignment
                count = await guards_collection.count_documents({})
                employee_code = f"GRD{str(count + 1).zfill(3)}"
                
                guard_data = {
                    "userId": str(user["_id"]),
                    "supervisorId": "",  # To be assigned by admin
                    "employeeCode": employee_code,
                    "createdAt": datetime.utcnow(),
                    "updatedAt": datetime.utcnow()
                }
                
                await guards_collection.insert_one(guard_data)
                logger.info(f"Created guard record: {employee_code}")
                
    except Exception as e:
        logger.error(f"Failed to create role-specific record: {e}")


async def store_refresh_token(user_id: str, refresh_token: str):
    """Store refresh token in database"""
    try:
        refresh_tokens_collection = get_refresh_tokens_collection()
        if not refresh_tokens_collection:
            return
        
        token_hash = jwt_service.generate_refresh_token_hash(refresh_token)
        expires_at = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        
        token_data = {
            "userId": user_id,
            "tokenHash": token_hash,
            "expiresAt": expires_at,
            "revoked": False,
            "createdAt": datetime.utcnow()
        }
        
        await refresh_tokens_collection.insert_one(token_data)
        
    except Exception as e:
        logger.error(f"Failed to store refresh token: {e}")
