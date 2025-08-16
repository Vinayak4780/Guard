"""
Google Sheets service for real-time scan event logging
Enhanced with background updates and queue system for real-time data sync
"""

import gspread
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from google.auth.exceptions import DefaultCredentialsError
from queue import Queue
import threading
import time

from config import settings

logger = logging.getLogger(__name__)

class SheetsService:
    """Google Sheets service for real-time scan event logging"""
    
    def __init__(self):
        self.client = None
        self.spreadsheet = None
        self.update_queue = Queue()
        self.is_running = False
        self.update_thread = None
        
        # Headers for scan data (exact order)
        self.headers = [
            "Timestamp (IST)", "Guard Name", "Guard Email", "Employee Code",
            "Supervisor Name", "Supervisor Email", "Area/City", "QR ID",
            "Location Label", "Latitude", "Longitude", "Address",
            "Distance from QR (m)", "Within Radius", "Scan Status", "Notes"
        ]
        
        # Initialize Google Sheets connection
        self._initialize_connection()
        
        # Start background update service
        self._start_background_updates()
        
        logger.info(f"📊 Google Sheets service initialized with real-time updates (every {settings.UPDATE_INTERVAL_SECONDS}s)")
    
    def _initialize_connection(self) -> bool:
        """Initialize Google Sheets API connection"""
        try:
            if not settings.GOOGLE_SHEETS_CREDENTIALS_FILE:
                logger.warning("⚠️ Google Sheets credentials file not configured")
                return False
            
            if not settings.GOOGLE_SHEET_ID:
                logger.warning("⚠️ Google Sheet ID not configured")
                return False
            
            # Authenticate with Google Sheets API
            self.client = gspread.service_account(filename=settings.GOOGLE_SHEETS_CREDENTIALS_FILE)
            
            # Open the spreadsheet
            self.spreadsheet = self.client.open_by_key(settings.GOOGLE_SHEET_ID)
            
            logger.info(f"✅ Connected to Google Sheet: {self.spreadsheet.title}")
            return True
            
        except FileNotFoundError:
            logger.error(f"❌ Google Sheets credentials file not found: {settings.GOOGLE_SHEETS_CREDENTIALS_FILE}")
            return False
        except DefaultCredentialsError:
            logger.error("❌ Invalid Google Sheets credentials")
            return False
        except Exception as e:
            logger.error(f"❌ Failed to initialize Google Sheets: {e}")
            return False
    
    def _start_background_updates(self):
        """Start background thread for real-time updates"""
        if self.client and self.spreadsheet:
            self.is_running = True
            self.update_thread = threading.Thread(target=self._background_update_worker, daemon=True)
            self.update_thread.start()
            logger.info("🔄 Started background update service for real-time Google Sheets sync")
    
    def _background_update_worker(self):
        """Background worker that processes update queue every second"""
        while self.is_running:
            try:
                # Collect all pending updates
                batch_updates = []
                while not self.update_queue.empty() and len(batch_updates) < 50:  # Max 50 updates per batch
                    try:
                        update_data = self.update_queue.get_nowait()
                        batch_updates.append(update_data)
                    except:
                        break
                
                # Process batch updates
                if batch_updates:
                    self._process_batch_updates(batch_updates)
                
                # Wait for next interval
                time.sleep(settings.UPDATE_INTERVAL_SECONDS)
                
            except Exception as e:
                logger.error(f"❌ Error in background update worker: {e}")
                time.sleep(5)  # Wait 5 seconds on error
    
    def _process_batch_updates(self, batch_updates: List[Dict[str, Any]]):
        """Process a batch of updates to Google Sheets"""
        try:
            for update_data in batch_updates:
                tab_name = update_data.get("tab_name")
                row_data = update_data.get("row_data")
                
                if tab_name and row_data:
                    worksheet = self._get_or_create_worksheet(tab_name)
                    if worksheet:
                        worksheet.append_row(row_data)
                        logger.info(f"✅ Added scan to {tab_name} worksheet")
            
            logger.info(f"📊 Processed {len(batch_updates)} updates to Google Sheets")
            
        except Exception as e:
            logger.error(f"❌ Failed to process batch updates: {e}")
    
    def _get_or_create_worksheet(self, tab_name: str):
        """Get or create a worksheet with the given tab name"""
        try:
            if not self.spreadsheet:
                return None
            
            # Check if worksheet exists
            try:
                worksheet = self.spreadsheet.worksheet(tab_name)
                return worksheet
            except gspread.WorksheetNotFound:
                pass
            
            # Create new worksheet
            worksheet = self.spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=16)
            
            # Add headers
            worksheet.insert_row(self.headers, 1)
            worksheet.format('A1:P1', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9}
            })
            worksheet.freeze(rows=1)
            
            logger.info(f"✅ Created new worksheet: {tab_name}")
            return worksheet
            
        except Exception as e:
            logger.error(f"❌ Failed to get/create worksheet {tab_name}: {e}")
            return None
    
    async def append_scan_to_sheet(self, scan_data: Dict[str, Any]) -> bool:
        """Queue scan data for real-time update to Google Sheets"""
        try:
            if not self.client or not self.spreadsheet:
                logger.warning("⚠️ Google Sheets not available - skipping append")
                return False
            
            # Prepare data for queue
            supervisor_area = scan_data.get("supervisorArea", "UNKNOWN").upper()
            tab_name = f"{supervisor_area}_SCANS"
            
            # Convert scan data to row format
            ist_time = scan_data.get("scannedAt", datetime.utcnow())
            if isinstance(ist_time, str):
                ist_time = datetime.fromisoformat(ist_time.replace('Z', '+00:00'))
            
            # Convert to IST
            ist_time = ist_time.replace(tzinfo=timezone.utc).astimezone()
            
            row_data = [
                ist_time.strftime("%d-%m-%Y %H:%M:%S"),
                scan_data.get("guardName", ""),
                scan_data.get("guardEmail", ""),
                scan_data.get("guardEmployeeCode", ""),
                scan_data.get("supervisorName", ""),
                scan_data.get("supervisorEmail", ""),
                scan_data.get("supervisorArea", ""),
                scan_data.get("qrId", ""),
                scan_data.get("locationLabel", ""),
                scan_data.get("scannedLatitude", ""),
                scan_data.get("scannedLongitude", ""),
                scan_data.get("address", ""),
                scan_data.get("distanceFromQR", ""),
                "Yes" if scan_data.get("isWithinRadius", False) else "No",
                scan_data.get("scanStatus", "SUCCESS"),
                scan_data.get("notes", "")
            ]
            
            # Add to update queue for real-time processing
            update_item = {
                "tab_name": tab_name,
                "row_data": row_data,
                "timestamp": datetime.utcnow()
            }
            
            self.update_queue.put(update_item)
            logger.info(f"📝 Queued scan data for real-time update to {tab_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to queue scan for sheets update: {e}")
            return False
    
    def get_sheet_health(self) -> Dict[str, Any]:
        """Get Google Sheets service health status"""
        try:
            if not self.client or not self.spreadsheet:
                return {
                    "status": "disconnected",
                    "message": "Google Sheets not connected"
                }
            
            # Test connection
            title = self.spreadsheet.title
            queue_size = self.update_queue.qsize()
            
            return {
                "status": "connected",
                "spreadsheet_title": title,
                "queue_size": queue_size,
                "update_interval": settings.UPDATE_INTERVAL_SECONDS,
                "background_worker": "running" if self.is_running else "stopped"
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }
    
    def stop_background_updates(self):
        """Stop the background update service"""
        self.is_running = False
        if self.update_thread:
            self.update_thread.join(timeout=5)
        logger.info("🛑 Stopped background update service")

# Create global instance
sheets_service = SheetsService()
