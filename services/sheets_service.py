"""
Google Sheets service for logging scan events
Handles sheet creation, data appending, and access control
"""

import gspread
from google.oauth2.service_account import Credentials
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime
import pytz
from config import settings

logger = logging.getLogger(__name__)


class GoogleSheetsService:
    """Google Sheets integration for scan event logging"""
    
    def __init__(self):
        self.credentials_file = settings.GOOGLE_SHEETS_CREDENTIALS_FILE
        self.spreadsheet_id = settings.GOOGLE_SHEETS_SPREADSHEET_ID
        self.timezone = pytz.timezone(settings.TIMEZONE)
        
        self.client = None
        self.spreadsheet = None
        
        if not self.credentials_file or not self.spreadsheet_id:
            logger.warning("⚠️ Google Sheets not configured. Scan logging to sheets disabled.")
            return
        
        try:
            # Setup Google Sheets client
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            
            credentials = Credentials.from_service_account_file(
                self.credentials_file, 
                scopes=scopes
            )
            
            self.client = gspread.authorize(credentials)
            self.spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            
            logger.info("✅ Google Sheets service initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Google Sheets service: {e}")
            self.client = None
            self.spreadsheet = None
    
    def format_timestamp_ist(self, utc_datetime: datetime) -> str:
        """
        Format UTC datetime to IST string for sheets
        
        Args:
            utc_datetime: UTC datetime object
            
        Returns:
            Formatted IST timestamp string (DD-MM-YYYY HH:mm:ss)
        """
        # Convert UTC to IST
        utc_dt = utc_datetime.replace(tzinfo=pytz.UTC)
        ist_dt = utc_dt.astimezone(self.timezone)
        
        return ist_dt.strftime("%d-%m-%Y %H:%M:%S")
    
    def get_or_create_supervisor_tab(self, supervisor_code: str, area_city: str) -> Optional[Any]:
        """
        Get or create a tab for supervisor scans
        
        Args:
            supervisor_code: Supervisor code (e.g., SUP001)
            area_city: Area/city name
            
        Returns:
            Worksheet object or None if error
        """
        if not self.spreadsheet:
            return None
        
        try:
            # Tab name format: SUP_<SupervisorCode>_<City>
            tab_name = f"SUP_{supervisor_code}_{area_city}".replace(" ", "_").upper()
            
            # Try to get existing worksheet
            try:
                worksheet = self.spreadsheet.worksheet(tab_name)
                return worksheet
            except gspread.WorksheetNotFound:
                pass
            
            # Create new worksheet
            worksheet = self.spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=16)
            
            # Add headers
            headers = [
                "timestamp_ist",
                "supervisor_id", 
                "supervisor_name",
                "supervisor_area_city",
                "guard_id",
                "guard_name",
                "qr_id",
                "qr_label",
                "qr_lat",
                "qr_lng", 
                "device_lat",
                "device_lng",
                "distance_meters",
                "within_radius",
                "reverse_geocoded_address",
                "notes"
            ]
            
            # Format headers
            worksheet.insert_row(headers, 1)
            worksheet.format('A1:P1', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9}
            })
            
            # Freeze header row
            worksheet.freeze(rows=1)
            
            logger.info(f"✅ Created new supervisor tab: {tab_name}")
            return worksheet
            
        except Exception as e:
            logger.error(f"❌ Failed to create supervisor tab: {e}")
            return None
    
    def get_or_create_area_tab(self, area_city: str) -> Optional[Any]:
        """
        Get or create a tab for area-wise reports (admin view)
        
        Args:
            area_city: Area/city name
            
        Returns:
            Worksheet object or None if error
        """
        if not self.spreadsheet:
            return None
        
        try:
            # Tab name format: AREA_<City>
            tab_name = area_city.replace(" ", "_").upper()
            
            # Try to get existing worksheet
            try:
                worksheet = self.spreadsheet.worksheet(tab_name)
                return worksheet
            except gspread.WorksheetNotFound:
                pass
            
            # Create new worksheet
            worksheet = self.spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=16)
            
            # Add headers (same as supervisor tabs)
            headers = [
                "timestamp_ist",
                "supervisor_id", 
                "supervisor_name",
                "supervisor_area_city",
                "guard_id",
                "guard_name",
                "qr_id",
                "qr_label",
                "qr_lat",
                "qr_lng", 
                "device_lat",
                "device_lng",
                "distance_meters",
                "within_radius",
                "reverse_geocoded_address",
                "notes"
            ]
            
            # Format headers
            worksheet.insert_row(headers, 1)
            worksheet.format('A1:P1', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.8, 'green': 0.9, 'blue': 1.0}
            })
            
            # Freeze header row
            worksheet.freeze(rows=1)
            
            logger.info(f"✅ Created new area tab: {tab_name}")
            return worksheet
            
        except Exception as e:
            logger.error(f"❌ Failed to create area tab: {e}")
            return None
    
    async def append_scan_event(self, scan_data: Dict[str, Any]) -> bool:
        """
        Append scan event to appropriate sheet tabs
        
        Args:
            scan_data: Complete scan event data with all required fields
            
        Returns:
            True if successful, False otherwise
        """
        if not self.spreadsheet:
            logger.warning("Google Sheets not available, skipping scan log")
            return False
        
        try:
            # Prepare row data matching exact header order
            row_data = [
                scan_data.get("timestamp_ist", ""),
                scan_data.get("supervisor_id", ""),
                scan_data.get("supervisor_name", ""),
                scan_data.get("supervisor_area_city", ""),
                scan_data.get("guard_id", ""),
                scan_data.get("guard_name", ""),
                scan_data.get("qr_id", ""),
                scan_data.get("qr_label", ""),
                scan_data.get("qr_lat", ""),
                scan_data.get("qr_lng", ""),
                scan_data.get("device_lat", ""),
                scan_data.get("device_lng", ""),
                scan_data.get("distance_meters", ""),
                scan_data.get("within_radius", ""),
                scan_data.get("reverse_geocoded_address", ""),
                scan_data.get("notes", "")
            ]
            
            # Append to supervisor tab
            supervisor_code = scan_data.get("supervisor_code", "UNKNOWN")
            area_city = scan_data.get("supervisor_area_city", "UNKNOWN")
            
            supervisor_worksheet = self.get_or_create_supervisor_tab(supervisor_code, area_city)
            if supervisor_worksheet:
                supervisor_worksheet.append_row(row_data)
                logger.info(f"✅ Appended scan to supervisor tab: SUP_{supervisor_code}_{area_city}")
            
            # Append to area tab (for admin view)
            area_worksheet = self.get_or_create_area_tab(area_city)
            if area_worksheet:
                area_worksheet.append_row(row_data)
                logger.info(f"✅ Appended scan to area tab: {area_city}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to append scan event to sheets: {e}")
            return False
    
    def get_supervisor_sheet_url(self, supervisor_code: str, area_city: str) -> Optional[str]:
        """
        Get URL for supervisor's sheet tab
        
        Args:
            supervisor_code: Supervisor code
            area_city: Area/city name
            
        Returns:
            Sheet URL with tab reference or None
        """
        if not self.spreadsheet:
            return None
        
        try:
            tab_name = f"SUP_{supervisor_code}_{area_city}".replace(" ", "_").upper()
            worksheet = self.spreadsheet.worksheet(tab_name)
            
            # Construct URL with sheet ID and tab GID
            base_url = f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}"
            tab_url = f"{base_url}#gid={worksheet.id}"
            
            return tab_url
            
        except Exception as e:
            logger.error(f"Failed to get supervisor sheet URL: {e}")
            return None
    
    def get_area_sheet_url(self, area_city: str) -> Optional[str]:
        """
        Get URL for area sheet tab
        
        Args:
            area_city: Area/city name
            
        Returns:
            Sheet URL with tab reference or None
        """
        if not self.spreadsheet:
            return None
        
        try:
            tab_name = area_city.replace(" ", "_").upper()
            worksheet = self.spreadsheet.worksheet(tab_name)
            
            # Construct URL with sheet ID and tab GID
            base_url = f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}"
            tab_url = f"{base_url}#gid={worksheet.id}"
            
            return tab_url
            
        except Exception as e:
            logger.error(f"Failed to get area sheet URL: {e}")
            return None
    
    def get_sheet_health(self) -> Dict[str, Any]:
        """
        Get health status of Google Sheets service
        
        Returns:
            Health status information
        """
        if not self.client or not self.spreadsheet:
            return {
                "status": "disabled",
                "message": "Google Sheets service not configured"
            }
        
        try:
            # Test access by getting spreadsheet info
            sheet_info = self.spreadsheet.title
            worksheet_count = len(self.spreadsheet.worksheets())
            
            return {
                "status": "healthy",
                "message": "Google Sheets service operational",
                "spreadsheet_title": sheet_info,
                "worksheet_count": worksheet_count
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Google Sheets service error: {str(e)}"
            }


# Global Google Sheets service instance
sheets_service = GoogleSheetsService()
