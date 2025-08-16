"""
Minimal Supervisor routes for testing imports
"""

from fastapi import APIRouter
import logging

logger = logging.getLogger(__name__)

# Create router
supervisor_router = APIRouter()

@supervisor_router.get("/test")
async def test_endpoint():
    """Test endpoint"""
    return {"message": "Supervisor routes working!"}
