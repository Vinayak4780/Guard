"""
Admin routes for user management and system administration
ADMIN role only - manage supervisors, guards, and system configuration
Updated with specific email patterns: admin@lh.io.in, {area}supervisor@lh.io.in
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query
from fastapi.responses import FileResponse
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
from bson import ObjectId

# Import services and dependencies
from services.auth_service import get_current_admin
from services.google_drive_excel_service import google_drive_excel_service
from database import (
    get_users_collection, get_supervisors_collection, get_guards_collection,
    get_scan_events_collection, get_qr_locations_collection, get_database_health
)
from config import settings

# Import models
from models import (
    UserCreate, UserResponse, UserRole, SupervisorCreate, SupervisorResponse,
    GuardCreate, GuardResponse, ScanEventResponse, AreaReportRequest,
    ScanReportResponse, SuccessResponse, SystemConfig, SystemConfigUpdate,
    generate_supervisor_email, generate_guard_email
)

logger = logging.getLogger(__name__)

# Create router
admin_router = APIRouter()


@admin_router.get("/dashboard")
async def get_admin_dashboard(current_admin: Dict[str, Any] = Depends(get_current_admin)):
    """
    Admin dashboard with system statistics
    """
    try:
        users_collection = get_users_collection()
        supervisors_collection = get_supervisors_collection()
        guards_collection = get_guards_collection()
        scan_events_collection = get_scan_events_collection()
        
        if not all([users_collection, supervisors_collection, guards_collection, scan_events_collection]):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Get basic counts
        total_users = await users_collection.count_documents({})
        total_supervisors = await supervisors_collection.count_documents({})
        total_guards = await guards_collection.count_documents({})
        total_scans_today = await scan_events_collection.count_documents({
            "scannedAt": {"$gte": datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)}
        })
        
        # Get recent activity
        recent_scans = await scan_events_collection.find({}) \
            .sort("scannedAt", -1) \
            .limit(10) \
            .to_list(10)
        
        return {
            "stats": {
                "totalUsers": total_users,
                "totalSupervisors": total_supervisors,
                "totalGuards": total_guards,
                "scansToday": total_scans_today
            },
            "recentActivity": recent_scans,
            "adminInfo": {
                "email": current_admin["email"],
                "name": current_admin.get("name", "Admin")
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load dashboard"
        )


@admin_router.get("/users", response_model=List[UserResponse])
async def list_users(
    role: Optional[UserRole] = Query(None, description="Filter by user role"),
    active: Optional[bool] = Query(None, description="Filter by active status"),
    current_admin: Dict[str, Any] = Depends(get_current_admin)
):
    """
    List all users with optional filtering
    """
    try:
        users_collection = get_users_collection()
        if not users_collection:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Build filter query
        filter_query = {}
        if role:
            filter_query["role"] = role.value
        if active is not None:
            filter_query["isActive"] = active
        
        users = await users_collection.find(filter_query).sort("createdAt", -1).to_list(100)
        
        user_responses = []
        for user in users:
            response = UserResponse(
                id=str(user["_id"]),
                email=user["email"],
                name=user["name"],
                role=user["role"],
                isActive=user["isActive"],
                isEmailVerified=user.get("isEmailVerified", False),
                createdAt=user["createdAt"],
                updatedAt=user["updatedAt"]
            )
            user_responses.append(response)
        
        return user_responses
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"List users error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list users"
        )


@admin_router.post("/supervisors", response_model=SupervisorResponse)
async def create_supervisor(
    supervisor_data: SupervisorCreate,
    current_admin: Dict[str, Any] = Depends(get_current_admin)
):
    """
    Create a new supervisor with area-based email: {area}supervisor@lh.io.in
    """
    try:
        from services.jwt_service import jwt_service
        
        users_collection = get_users_collection()
        supervisors_collection = get_supervisors_collection()
        
        if not all([users_collection, supervisors_collection]):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Generate email if not provided correctly
        expected_email = generate_supervisor_email(supervisor_data.areaCity)
        if supervisor_data.email.lower() != expected_email:
            logger.info(f"Auto-correcting supervisor email from {supervisor_data.email} to {expected_email}")
            supervisor_data.email = expected_email
        
        # Check if user already exists
        existing_user = await users_collection.find_one({"email": supervisor_data.email})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )
        
        # Check if supervisor already exists for this area
        existing_supervisor = await supervisors_collection.find_one({
            "areaCity": supervisor_data.areaCity.lower()
        })
        if existing_supervisor:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Supervisor already exists for area: {supervisor_data.areaCity}"
            )
        
        # Create user account first
        user_data = {
            "email": supervisor_data.email,
            "passwordHash": jwt_service.hash_password("Supervisor@123"),  # Default password
            "name": supervisor_data.name,
            "role": "SUPERVISOR",
            "isActive": True,
            "isEmailVerified": True,  # Auto-verify supervisor emails
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
        
        user_result = await users_collection.insert_one(user_data)
        user_id = str(user_result.inserted_id)
        
        # Create supervisor profile
        supervisor_code = f"SUP_{supervisor_data.areaCity.upper()[:3]}_{datetime.utcnow().strftime('%Y%m')}"
        
        supervisor_profile = {
            "userId": user_id,
            "code": supervisor_code,
            "email": supervisor_data.email,
            "name": supervisor_data.name,
            "areaCity": supervisor_data.areaCity.lower(),
            "areaState": supervisor_data.areaState,
            "areaCountry": supervisor_data.areaCountry,
            "sheetId": supervisor_data.sheetId,
            "isActive": True,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
        
        supervisor_result = await supervisors_collection.insert_one(supervisor_profile)
        
        logger.info(f"✅ Supervisor created: {supervisor_data.email} for area {supervisor_data.areaCity}")
        logger.info(f"🔑 Default password: Supervisor@123 (should be changed on first login)")
        
        return SupervisorResponse(
            id=str(supervisor_result.inserted_id),
            userId=user_id,
            email=supervisor_data.email,
            name=supervisor_data.name,
            areaCity=supervisor_data.areaCity,
            areaState=supervisor_data.areaState,
            areaCountry=supervisor_data.areaCountry,
            sheetId=supervisor_data.sheetId,
            isActive=True,
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create supervisor error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create supervisor"
        )


@admin_router.post("/guards", response_model=GuardResponse)
async def create_guard(
    guard_data: GuardCreate,
    current_admin: Dict[str, Any] = Depends(get_current_admin)
):
    """
    Create a new guard with email validation: must end with @lh.io.in
    """
    try:
        from services.jwt_service import jwt_service
        
        users_collection = get_users_collection()
        guards_collection = get_guards_collection()
        supervisors_collection = get_supervisors_collection()
        
        if not all([users_collection, guards_collection, supervisors_collection]):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Verify supervisor exists
        supervisor = await supervisors_collection.find_one({"_id": ObjectId(guard_data.supervisorId)})
        if not supervisor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Supervisor not found"
            )
        
        # Check if user already exists
        existing_user = await users_collection.find_one({"email": guard_data.email})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )
        
        # Create user account first
        user_data = {
            "email": guard_data.email,
            "passwordHash": jwt_service.hash_password("Guard@123"),  # Default password
            "name": guard_data.name,
            "role": "GUARD",
            "isActive": True,
            "isEmailVerified": True,  # Auto-verify guard emails
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
        
        user_result = await users_collection.insert_one(user_data)
        user_id = str(user_result.inserted_id)
        
        # Create guard profile
        guard_code = f"GRD_{supervisor['areaCity'].upper()[:3]}_{datetime.utcnow().strftime('%Y%m%d')}{len(await guards_collection.find().to_list(1000)) + 1:03d}"
        
        guard_profile = {
            "userId": user_id,
            "supervisorId": guard_data.supervisorId,
            "employeeCode": guard_code,
            "email": guard_data.email,
            "name": guard_data.name,
            "areaCity": supervisor["areaCity"],
            "shift": guard_data.shift,
            "phoneNumber": guard_data.phoneNumber,
            "emergencyContact": guard_data.emergencyContact,
            "isActive": True,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
        
        guard_result = await guards_collection.insert_one(guard_profile)
        
        logger.info(f"✅ Guard created: {guard_data.email} under supervisor {supervisor['email']}")
        logger.info(f"🔑 Default password: Guard@123 (should be changed on first login)")
        
        return GuardResponse(
            id=str(guard_result.inserted_id),
            userId=user_id,
            supervisorId=guard_data.supervisorId,
            email=guard_data.email,
            name=guard_data.name,
            areaCity=supervisor["areaCity"],
            shift=guard_data.shift,
            phoneNumber=guard_data.phoneNumber,
            emergencyContact=guard_data.emergencyContact,
            isActive=True,
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create guard error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create guard"
        )


@admin_router.get("/supervisors", response_model=List[SupervisorResponse])
async def list_supervisors(
    current_admin: Dict[str, Any] = Depends(get_current_admin)
):
    """
    List all supervisors
    """
    try:
        supervisors_collection = get_supervisors_collection()
        if not supervisors_collection:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        supervisors = await supervisors_collection.find({}).sort("createdAt", -1).to_list(100)
        
        supervisor_responses = []
        for supervisor in supervisors:
            response = SupervisorResponse(
                id=str(supervisor["_id"]),
                userId=supervisor["userId"],
                email=supervisor["email"],
                name=supervisor["name"],
                areaCity=supervisor["areaCity"],
                areaState=supervisor["areaState"],
                areaCountry=supervisor["areaCountry"],
                sheetId=supervisor.get("sheetId"),
                isActive=supervisor["isActive"],
                createdAt=supervisor["createdAt"],
                updatedAt=supervisor["updatedAt"]
            )
            supervisor_responses.append(response)
        
        return supervisor_responses
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"List supervisors error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list supervisors"
        )


@admin_router.delete("/supervisors/{supervisor_id}")
async def remove_supervisor(
    supervisor_id: str,
    current_admin: Dict[str, Any] = Depends(get_current_admin)
):
    """
    Remove/Deactivate a supervisor and handle all associated data
    """
    try:
        users_collection = get_users_collection()
        supervisors_collection = get_supervisors_collection()
        guards_collection = get_guards_collection()
        qr_locations_collection = get_qr_locations_collection()
        
        if not all([users_collection, supervisors_collection, guards_collection, qr_locations_collection]):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Validate supervisor exists
        try:
            supervisor_obj_id = ObjectId(supervisor_id)
        except:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid supervisor ID format"
            )
        
        supervisor = await supervisors_collection.find_one({"_id": supervisor_obj_id})
        if not supervisor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Supervisor not found"
            )
        
        supervisor_user_id = supervisor.get("userId")
        supervisor_name = supervisor.get("name", "Unknown")
        supervisor_area = supervisor.get("areaCity", "Unknown")
        
        # Get count of associated guards
        guards_count = await guards_collection.count_documents({"supervisorId": supervisor_id})
        
        # Get QR location
        qr_location = await qr_locations_collection.find_one({"supervisorId": supervisor_id})
        
        # Option 1: Soft delete (recommended) - just deactivate
        # Update supervisor status
        await supervisors_collection.update_one(
            {"_id": supervisor_obj_id},
            {
                "$set": {
                    "isActive": False,
                    "deactivatedAt": datetime.utcnow(),
                    "deactivatedBy": current_admin["_id"]
                }
            }
        )
        
        # Deactivate associated user account
        if supervisor_user_id:
            await users_collection.update_one(
                {"_id": ObjectId(supervisor_user_id)},
                {
                    "$set": {
                        "isActive": False,
                        "deactivatedAt": datetime.utcnow(),
                        "deactivatedBy": current_admin["_id"]
                    }
                }
            )
        
        # Deactivate associated guards (but keep their data)
        if guards_count > 0:
            # Get all guards under this supervisor
            guards_cursor = guards_collection.find({"supervisorId": supervisor_id})
            deactivated_guards = []
            
            async for guard in guards_cursor:
                guard_user_id = guard.get("userId")
                
                # Deactivate guard profile
                await guards_collection.update_one(
                    {"_id": guard["_id"]},
                    {
                        "$set": {
                            "isActive": False,
                            "deactivatedAt": datetime.utcnow(),
                            "deactivatedBy": current_admin["_id"],
                            "deactivationReason": f"Supervisor {supervisor_name} removed"
                        }
                    }
                )
                
                # Deactivate guard user account
                if guard_user_id:
                    await users_collection.update_one(
                        {"_id": ObjectId(guard_user_id)},
                        {
                            "$set": {
                                "isActive": False,
                                "deactivatedAt": datetime.utcnow(),
                                "deactivatedBy": current_admin["_id"]
                            }
                        }
                    )
                
                deactivated_guards.append({
                    "guard_id": str(guard["_id"]),
                    "name": guard.get("name", "Unknown"),
                    "employeeCode": guard.get("employeeCode", "")
                })
        
        # Deactivate QR location (but keep for historical data)
        if qr_location:
            await qr_locations_collection.update_one(
                {"_id": qr_location["_id"]},
                {
                    "$set": {
                        "active": False,
                        "deactivatedAt": datetime.utcnow(),
                        "deactivatedBy": current_admin["_id"]
                    }
                }
            )
        
        logger.info(f"Admin {current_admin.get('email')} removed supervisor {supervisor_name} ({supervisor_area})")
        
        return {
            "message": "Supervisor removed successfully",
            "supervisor": {
                "id": supervisor_id,
                "name": supervisor_name,
                "area": supervisor_area,
                "email": supervisor.get("email", "")
            },
            "affected_data": {
                "guards_deactivated": len(deactivated_guards) if guards_count > 0 else 0,
                "qr_location_deactivated": qr_location is not None,
                "guards_list": deactivated_guards if guards_count > 0 else []
            },
            "note": "All data has been soft-deleted (deactivated) and preserved for historical records",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Remove supervisor error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove supervisor"
        )


@admin_router.post("/supervisors/{supervisor_id}/reactivate")
async def reactivate_supervisor(
    supervisor_id: str,
    current_admin: Dict[str, Any] = Depends(get_current_admin)
):
    """
    Reactivate a previously removed supervisor
    """
    try:
        users_collection = get_users_collection()
        supervisors_collection = get_supervisors_collection()
        
        if not all([users_collection, supervisors_collection]):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Validate supervisor exists
        try:
            supervisor_obj_id = ObjectId(supervisor_id)
        except:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid supervisor ID format"
            )
        
        supervisor = await supervisors_collection.find_one({"_id": supervisor_obj_id})
        if not supervisor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Supervisor not found"
            )
        
        if supervisor.get("isActive", True):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Supervisor is already active"
            )
        
        supervisor_user_id = supervisor.get("userId")
        supervisor_name = supervisor.get("name", "Unknown")
        
        # Reactivate supervisor
        await supervisors_collection.update_one(
            {"_id": supervisor_obj_id},
            {
                "$set": {
                    "isActive": True,
                    "reactivatedAt": datetime.utcnow(),
                    "reactivatedBy": current_admin["_id"]
                },
                "$unset": {
                    "deactivatedAt": "",
                    "deactivatedBy": ""
                }
            }
        )
        
        # Reactivate associated user account
        if supervisor_user_id:
            await users_collection.update_one(
                {"_id": ObjectId(supervisor_user_id)},
                {
                    "$set": {
                        "isActive": True,
                        "reactivatedAt": datetime.utcnow(),
                        "reactivatedBy": current_admin["_id"]
                    },
                    "$unset": {
                        "deactivatedAt": "",
                        "deactivatedBy": ""
                    }
                }
            )
        
        logger.info(f"Admin {current_admin.get('email')} reactivated supervisor {supervisor_name}")
        
        return {
            "message": "Supervisor reactivated successfully",
            "supervisor": {
                "id": supervisor_id,
                "name": supervisor_name,
                "area": supervisor.get("areaCity", "Unknown"),
                "email": supervisor.get("email", "")
            },
            "note": "Guards and QR locations need to be reactivated separately if needed",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reactivate supervisor error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reactivate supervisor"
        )


@admin_router.get("/guards", response_model=List[GuardResponse])
async def list_guards(
    supervisor_id: Optional[str] = Query(None, description="Filter by supervisor ID"),
    current_admin: Dict[str, Any] = Depends(get_current_admin)
):
    """
    List all guards with optional supervisor filtering
    """
    try:
        guards_collection = get_guards_collection()
        if not guards_collection:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Build filter query
        filter_query = {}
        if supervisor_id:
            filter_query["supervisorId"] = supervisor_id
        
        guards = await guards_collection.find(filter_query).sort("createdAt", -1).to_list(100)
        
        guard_responses = []
        for guard in guards:
            response = GuardResponse(
                id=str(guard["_id"]),
                userId=guard["userId"],
                supervisorId=guard["supervisorId"],
                email=guard["email"],
                name=guard["name"],
                areaCity=guard["areaCity"],
                shift=guard["shift"],
                phoneNumber=guard["phoneNumber"],
                emergencyContact=guard["emergencyContact"],
                isActive=guard["isActive"],
                createdAt=guard["createdAt"],
                updatedAt=guard["updatedAt"]
            )
            guard_responses.append(response)
        
        return guard_responses
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"List guards error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list guards"
        )


@admin_router.get("/system/health")
async def get_system_health(current_admin: Dict[str, Any] = Depends(get_current_admin)):
    """
    Get system health status
    """
    try:
        database_health = await get_database_health()
        
        return {
            "status": "healthy" if database_health["connected"] else "degraded",
            "database": database_health,
            "services": {
                "email": bool(settings.SMTP_USERNAME and settings.SMTP_PASSWORD),
                "tomtom": bool(settings.TOMTOM_API_KEY),
                "google_drive_excel": bool(settings.GOOGLE_DRIVE_CREDENTIALS_FILE)
            },
            "timestamp": datetime.utcnow()
        }
        
    except Exception as e:
        logger.error(f"System health check error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check system health"
        )


# =============================================================================
# EXCEL MANAGEMENT ENDPOINTS - AREA-WISE GOOGLE DRIVE INTEGRATION
# =============================================================================

@admin_router.get("/excel/areas")
async def get_excel_areas(current_admin: Dict[str, Any] = Depends(get_current_admin)):
    """
    Get all areas/supervisors with their Excel worksheet information
    """
    try:
        supervisors_collection = get_supervisors_collection()
        scan_events_collection = get_scan_events_collection()
        
        if not all([supervisors_collection, scan_events_collection]):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Get all supervisors with their areas
        supervisors_cursor = supervisors_collection.find({"isActive": True})
        areas_data = []
        
        async for supervisor in supervisors_cursor:
            area_city = supervisor.get("areaCity", "Unknown")
            supervisor_name = supervisor.get("name", "Unknown")
            supervisor_email = supervisor.get("email", "")
            
            # Get scan count for this supervisor
            scan_count = await scan_events_collection.count_documents({
                "supervisorId": supervisor["_id"]
            })
            
            # Get latest scan
            latest_scan = await scan_events_collection.find_one(
                {"supervisorId": supervisor["_id"]},
                sort=[("scannedAt", -1)]
            )
            
            worksheet_name = f"{area_city}_Scans"
            
            area_info = {
                "supervisor_id": str(supervisor["_id"]),
                "supervisor_name": supervisor_name,
                "supervisor_email": supervisor_email,
                "area_city": area_city,
                "worksheet_name": worksheet_name,
                "total_scans": scan_count,
                "latest_scan_date": latest_scan.get("scannedAt").isoformat() if latest_scan and latest_scan.get("scannedAt") else None,
                "has_data": scan_count > 0
            }
            
            areas_data.append(area_info)
        
        # Get Excel service health
        excel_health = google_drive_excel_service.get_service_health()
        
        return {
            "areas": areas_data,
            "total_areas": len(areas_data),
            "excel_service": excel_health,
            "google_drive_file": {
                "file_name": settings.EXCEL_FILE_NAME,
                "file_id": excel_health.get("file_id"),
                "update_interval": settings.UPDATE_INTERVAL_SECONDS
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting Excel areas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get Excel areas"
        )


@admin_router.get("/excel/area/{area_name}")
async def get_area_excel_data(
    area_name: str,
    current_admin: Dict[str, Any] = Depends(get_current_admin),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
    skip: int = Query(0, ge=0, description="Number of records to skip")
):
    """
    Get Excel data for a specific area/supervisor
    """
    try:
        supervisors_collection = get_supervisors_collection()
        scan_events_collection = get_scan_events_collection()
        
        if not all([supervisors_collection, scan_events_collection]):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Find supervisor by area
        supervisor = await supervisors_collection.find_one({
            "areaCity": area_name,
            "isActive": True
        })
        
        if not supervisor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No active supervisor found for area: {area_name}"
            )
        
        # Get scan events for this supervisor
        scans_cursor = scan_events_collection.find(
            {"supervisorId": supervisor["_id"]}
        ).sort("scannedAt", -1).skip(skip).limit(limit)
        
        scans = []
        async for scan in scans_cursor:
            scan_data = {
                "scan_id": str(scan["_id"]),
                "timestamp": scan.get("scannedAt"),
                "guard_name": scan.get("guardName", "Unknown"),
                "guard_email": scan.get("guardEmail", ""),
                "qr_location": scan.get("qrLocation", ""),
                "latitude": scan.get("latitude", 0),
                "longitude": scan.get("longitude", 0),
                "address": scan.get("address", ""),
                "status": scan.get("status", "SUCCESS"),
                "distance_meters": scan.get("distanceMeters", 0),
                "within_radius": scan.get("withinRadius", True)
            }
            scans.append(scan_data)
        
        # Get total count
        total_scans = await scan_events_collection.count_documents({
            "supervisorId": supervisor["_id"]
        })
        
        return {
            "area_name": area_name,
            "supervisor": {
                "id": str(supervisor["_id"]),
                "name": supervisor.get("name", "Unknown"),
                "email": supervisor.get("email", "")
            },
            "worksheet_name": f"{area_name}_Scans",
            "scans": scans,
            "pagination": {
                "total": total_scans,
                "limit": limit,
                "skip": skip,
                "returned": len(scans)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting area Excel data: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get area Excel data"
        )


@admin_router.get("/excel/download")
async def download_excel_file(current_admin: Dict[str, Any] = Depends(get_current_admin)):
    """
    Get download link for the complete Excel file from Google Drive
    """
    try:
        excel_health = google_drive_excel_service.get_service_health()
        
        if excel_health.get("status") != "healthy":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Excel service not available"
            )
        
        file_id = excel_health.get("file_id")
        if not file_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Excel file not found in Google Drive"
            )
        
        # Generate Google Drive download link
        download_link = f"https://drive.google.com/file/d/{file_id}/view"
        direct_download_link = f"https://drive.google.com/uc?export=download&id={file_id}"
        
        return {
            "file_name": settings.EXCEL_FILE_NAME,
            "file_id": file_id,
            "view_link": download_link,
            "download_link": direct_download_link,
            "last_updated": datetime.utcnow().isoformat(),
            "excel_service": excel_health
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting Excel download link: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get Excel download link"
        )


@admin_router.post("/excel/force-update")
async def force_excel_update(current_admin: Dict[str, Any] = Depends(get_current_admin)):
    """
    Force an immediate update of the Google Drive Excel file
    """
    try:
        # Process any pending updates immediately
        success = await google_drive_excel_service.process_update_queue()
        
        if success:
            excel_health = google_drive_excel_service.get_service_health()
            return {
                "message": "Excel file updated successfully",
                "timestamp": datetime.utcnow().isoformat(),
                "queue_processed": True,
                "excel_service": excel_health
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update Excel file"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error forcing Excel update: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to force Excel update"
        )
