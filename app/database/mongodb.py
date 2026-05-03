"""
MongoDB integration module.
Handles connections to MongoDB Atlas and sensor data retrieval.
"""

import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import logging

logger = logging.getLogger(__name__)


class MongoDBConnection:
    """
    Manages MongoDB Atlas connection and operations.
    Connects using MONGODB_URI environment variable.
    """
    
    _client: Optional[MongoClient] = None
    _db = None
    
    @classmethod
    def connect(cls) -> None:
        """
        Establish connection to MongoDB Atlas.
        Raises an exception if connection fails.
        """
        try:
            mongodb_uri = os.getenv("MONGODB_URI")
            if not mongodb_uri:
                raise ValueError("MONGODB_URI environment variable not set")
            
            cls._client = MongoClient(
                mongodb_uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                retryWrites=True
            )
            
            # Verify connection
            cls._client.admin.command("ping")
            cls._db = cls._client.get_database()
            logger.info("Successfully connected to MongoDB Atlas")
            
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"Failed to connect to MongoDB: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error connecting to MongoDB: {str(e)}")
            raise
    
    @classmethod
    def disconnect(cls) -> None:
        """Close the MongoDB connection."""
        if cls._client:
            cls._client.close()
            logger.info("Disconnected from MongoDB Atlas")
    
    @classmethod
    def get_db(cls):
        """Get the database instance. Connects if not already connected."""
        if cls._db is None:
            cls.connect()
        return cls._db
    
    @classmethod
    def get_sensor_data(cls, barangay_id: int, minutes: int = 10) -> Dict[str, Any]:
        """
        Fetch sensor readings from the last N minutes for a barangay.
        Aggregates readings to compute avg_water_level, max_water_level, and trend.
        
        Args:
            barangay_id: Identifier for the barangay
            minutes: How many minutes back to look for data (default 10)
        
        Returns:
            Dictionary with:
                - avg_water_level: Average water level in cm
                - max_water_level: Maximum water level in cm
                - trend: "rising", "falling", or "stable"
                - timestamp: Latest reading timestamp
                - readings_count: Number of readings aggregated
        """
        db = cls.get_db()
        
        try:
            # Query for recent sensor readings
            cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
            
            collection = db.get_collection("sensor_readings")
            readings = list(collection.find({
                "barangay_id": barangay_id,
                "timestamp": {"$gte": cutoff_time}
            }).sort("timestamp", 1))
            
            if not readings:
                logger.warning(f"No sensor data found for barangay {barangay_id}")
                return {
                    "avg_water_level": 0.0,
                    "max_water_level": 0.0,
                    "trend": "stable",
                    "timestamp": datetime.utcnow().isoformat(),
                    "readings_count": 0
                }
            
            # Extract water levels
            water_levels = [float(r.get("water_level", 0)) for r in readings]
            
            # Calculate aggregate metrics
            avg_water_level = sum(water_levels) / len(water_levels)
            max_water_level = max(water_levels)
            
            # Determine trend (compare first half vs second half)
            mid_point = len(water_levels) // 2
            if mid_point > 0:
                first_half_avg = sum(water_levels[:mid_point]) / mid_point
                second_half_avg = sum(water_levels[mid_point:]) / len(water_levels[mid_point:])
                
                # Allow 2% tolerance for "stable"
                threshold = first_half_avg * 0.02
                if second_half_avg > first_half_avg + threshold:
                    trend = "rising"
                elif second_half_avg < first_half_avg - threshold:
                    trend = "falling"
                else:
                    trend = "stable"
            else:
                trend = "stable"
            
            latest_timestamp = readings[-1].get("timestamp", datetime.utcnow())
            
            logger.info(f"Retrieved {len(water_levels)} sensor readings for barangay {barangay_id}")
            
            return {
                "avg_water_level": avg_water_level,
                "max_water_level": max_water_level,
                "trend": trend,
                "timestamp": latest_timestamp.isoformat() if hasattr(latest_timestamp, 'isoformat') else str(latest_timestamp),
                "readings_count": len(water_levels)
            }
            
        except Exception as e:
            logger.error(f"Error fetching sensor data: {str(e)}")
            raise
