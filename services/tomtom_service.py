"""
TomTom API service for reverse geocoding and address lookup
Focused on POI search and human-readable addresses for Indian locations
"""

import httpx
from typing import Optional, Dict, Any, Tuple
from config import settings
import logging
from geopy.distance import geodesic

logger = logging.getLogger(__name__)


class TomTomService:
    """Enhanced TomTom service for reverse geocoding and POI search"""
    
    def __init__(self):
        self.api_key = settings.TOMTOM_API_KEY
        self.base_url = "https://api.tomtom.com"
        
        # India geographical boundaries (approximate)
        self.india_bounds = {
            "min_lat": 6.0,   # Southern tip
            "max_lat": 37.0,  # Northern tip
            "min_lon": 68.0,  # Western tip
            "max_lon": 97.0   # Eastern tip
        }
        
        if not self.api_key:
            logger.warning("⚠️ TOMTOM_API_KEY not found. Reverse geocoding will be limited.")
    
    def validate_india_coordinates(self, latitude: float, longitude: float) -> bool:
        """
        Validate if coordinates are within India's geographical boundaries
        
        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            
        Returns:
            True if coordinates are within India, False otherwise
        """
        return (self.india_bounds["min_lat"] <= latitude <= self.india_bounds["max_lat"] and
                self.india_bounds["min_lon"] <= longitude <= self.india_bounds["max_lon"])
    
    def calculate_distance(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """
        Calculate distance between two coordinates in meters
        
        Args:
            lat1, lng1: First coordinate
            lat2, lng2: Second coordinate
            
        Returns:
            Distance in meters
        """
        try:
            distance = geodesic((lat1, lng1), (lat2, lng2)).meters
            return round(distance, 2)
        except Exception as e:
            logger.error(f"Error calculating distance: {e}")
            return 0.0
    
    async def search_poi(self, latitude: float, longitude: float, radius: int = 100) -> Optional[Dict[str, Any]]:
        """
        Search for POI (Point of Interest) near coordinates
        
        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            radius: Search radius in meters
            
        Returns:
            POI information if found, None otherwise
        """
        if not self.api_key:
            return None
        
        try:
            url = f"{self.base_url}/search/2/nearbySearch/.json"
            params = {
                "key": self.api_key,
                "lat": latitude,
                "lon": longitude,
                "radius": radius,
                "limit": 1,
                "countrySet": "IN"
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                
                data = response.json()
                
                if data.get("results") and len(data["results"]) > 0:
                    poi = data["results"][0]
                    return {
                        "name": poi.get("poi", {}).get("name"),
                        "category": poi.get("poi", {}).get("categories", []),
                        "address": poi.get("address", {}),
                        "distance": poi.get("dist", 0)
                    }
                
                return None
                
        except Exception as e:
            logger.error(f"Error in POI search: {e}")
            return None
    
    async def reverse_geocode_enhanced(self, latitude: float, longitude: float) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        Enhanced reverse geocode with POI search for human-readable addresses
        
        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            
        Returns:
            Tuple of (formatted_address, tomtom_response_data)
        """
        if not self.api_key:
            return None, None
        
        # Validate coordinates are within India
        if not self.validate_india_coordinates(latitude, longitude):
            return "Location outside India", None
        
        try:
            # First, try to find a POI nearby
            poi_data = await self.search_poi(latitude, longitude, radius=50)
            
            # Then do reverse geocoding for address
            url = f"{self.base_url}/search/2/reverseGeocode/{latitude},{longitude}.json"
            params = {
                "key": self.api_key,
                "radius": 100,
                "limit": 1,
                "countrySet": "IN"
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                
                data = response.json()
                
                if data.get("addresses") and len(data["addresses"]) > 0:
                    address_data = data["addresses"][0]["address"]
                    
                    # Build enhanced address with POI if available
                    address_parts = []
                    
                    # Add POI name if found and relevant
                    if poi_data and poi_data.get("name"):
                        poi_name = poi_data["name"]
                        # Filter out generic POI names
                        if not any(generic in poi_name.lower() for generic in ["unnamed", "road", "highway", "street"]):
                            address_parts.append(poi_name)
                    
                    # Add street/area information
                    if address_data.get("streetName"):
                        street = address_data["streetName"]
                        if not any(part in street for part in address_parts):  # Avoid duplication
                            address_parts.append(street)
                    
                    # Add locality/area
                    if address_data.get("municipality"):
                        municipality = address_data["municipality"]
                        if not any(part in municipality for part in address_parts):
                            address_parts.append(municipality)
                    
                    # Add district/sub-division
                    if address_data.get("countrySecondarySubdivision"):
                        district = address_data["countrySecondarySubdivision"]
                        if not any(part in district for part in address_parts):
                            address_parts.append(district)
                    
                    # Add state
                    if address_data.get("countrySubdivision"):
                        state = address_data["countrySubdivision"]
                        if not any(part in state for part in address_parts):
                            address_parts.append(state)
                    
                    # Format final address
                    if address_parts:
                        formatted_address = ", ".join(address_parts)
                    else:
                        formatted_address = address_data.get("freeformAddress", "Address not available")
                    
                    # Prepare response data for audit/reference
                    response_data = {
                        "placeId": address_data.get("id"),
                        "poi_data": poi_data,
                        "raw_address": address_data,
                        "coordinates": {"lat": latitude, "lng": longitude}
                    }
                    
                    return formatted_address, response_data
                
                return "Address not found", None
                
        except Exception as e:
            logger.error(f"Error in enhanced reverse geocoding: {e}")
            return f"Error: {str(e)}", None
    
    async def reverse_geocode(self, latitude: float, longitude: float) -> Optional[str]:
        """
        Simple reverse geocode for backward compatibility
        
        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            
        Returns:
            Formatted address string or None if error
        """
        formatted_address, _ = await self.reverse_geocode_enhanced(latitude, longitude)
        return formatted_address


# Global TomTom service instance
tomtom_service = TomTomService()
 