"""
Admin routes for user management and system administration
ADMIN role only - manage supervisors, guards, and system configuration
Updated with specific email patterns: admin@lh.io.in, {area}supervisor@lh.io.in
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query
from fastapi.responses import FileResponse
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging
import os
import io
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
        
        if not all([
            users_collection is not None, 
            supervisors_collection is not None, 
            guards_collection is not None, 
            scan_events_collection is not None
        ]):
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
        
        # Get recent activity - convert ObjectIds to strings
        recent_scans_cursor = scan_events_collection.find({}) \
            .sort("scannedAt", -1) \
            .limit(10)
        
        recent_scans = []
        async for scan in recent_scans_cursor:
            scan_data = {
                "_id": str(scan["_id"]),
                "guardId": str(scan.get("guardId", "")),
                "guardEmail": scan.get("guardEmail", ""),
                "qrId": str(scan.get("qrId", "")),
                "scannedAt": scan.get("scannedAt"),
                "deviceLat": scan.get("deviceLat"),
                "deviceLng": scan.get("deviceLng"),
                "address": scan.get("address", ""),
                "timestampIST": scan.get("timestampIST", "")
            }
            recent_scans.append(scan_data)
        
        # Convert admin ObjectIds to strings
        admin_info = {
            "_id": str(current_admin["_id"]),
            "email": current_admin["email"],
            "name": current_admin.get("name", "Admin"),
            "role": current_admin.get("role", "ADMIN")
        }
        
        return {
            "stats": {
                "totalUsers": total_users,
                "totalSupervisors": total_supervisors,
                "totalGuards": total_guards,
                "scansToday": total_scans_today
            },
            "recentActivity": recent_scans,
            "adminInfo": admin_info
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load dashboard"
        )


@admin_router.get("/excel/area-wise-reports")
async def get_area_wise_excel_reports(
    current_admin: Dict[str, Any] = Depends(get_current_admin),
    days_back: int = Query(7, ge=1, le=30, description="Number of days to include in report"),
    area: Optional[str] = Query(None, description="Specific area/state to filter (optional)"),
    building_name: Optional[str] = Query(None, description="Name of the building to filter (optional)")
):
    """
    Generate area-wise Excel reports for all areas or a specific area
    """
    try:
        scan_events_collection = get_scan_events_collection()
        if scan_events_collection is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )

        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days_back)

        # Build base filter for date range
        base_filter = {
            "scannedAt": {"$gte": start_date, "$lte": end_date}
        }

        # Add area filter if specified
        if area:
            base_filter["address"] = {"$regex": area, "$options": "i"}

        # Add building filter if specified
        if building_name:
            base_filter["organization"] = building_name

        # Fetch scan data
        scans = await scan_events_collection.find(base_filter).to_list(length=None)

        if not scans:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No scan data found in the specified date range"
            )

        # Group data by area
        area_data = {}
        for scan in scans:
            area_name = scan.get("address", "Unknown Area")
            building_name = scan.get("organization", "Unknown Building")

            if area_name not in area_data:
                area_data[area_name] = []

            row_data = {
                "Area": area_name,
                "Building Name": building_name
            }
            area_data[area_name].append(row_data)

        # Create Excel files for each area
        import pandas as pd
        excel_files = {}
        excel_folder = "excel_reports"
        os.makedirs(excel_folder, exist_ok=True)

        for area_name, data in area_data.items():
            if not data:
                continue

            # Generate filename
            filename = f"area_report_{area_name.replace(' ', '_')}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.xlsx"
            file_path = os.path.join(excel_folder, filename).replace("/", "\\")

            # Create DataFrame and Excel file
            df = pd.DataFrame(data)
            df.to_excel(file_path, index=False, sheet_name="Area Report")

            excel_files[area_name] = file_path

        return {"message": "Area-wise Excel reports generated successfully", "files": excel_files}

    except Exception as e:
        logger.error(f"Error generating area-wise Excel reports: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while generating the reports"
        )
