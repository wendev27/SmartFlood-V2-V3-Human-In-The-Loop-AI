"""
MongoDB integration module.
Handles connections to MongoDB Atlas and sensor data retrieval.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
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
            mongodb_db = os.getenv("MONGODB_DB")
            if mongodb_db:
                cls._db = cls._client[mongodb_db]
            else:
                cls._db = cls._client.get_database()
            logger.info(
                f"Successfully connected to MongoDB Atlas database={mongodb_db or cls._db.name}"
            )
            
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
    def _empty_sensor_fallback(cls) -> Dict[str, Any]:
        """Safe defaults when MongoDB is unavailable or has no recent readings."""
        return {
            "avg_water_level": 0.0,
            "max_water_level": 0.0,
            "trend": "stable",
            "rainfall_intensity_mm": 0.0,
            "timestamp": datetime.utcnow().isoformat(),
            "readings_count": 0,
        }

    @classmethod
    def _reading_time(cls, doc: Dict[str, Any]) -> Optional[datetime]:
        """Parse timestamp from Malabon sensor documents (recorded_at or timestamp)."""
        raw = doc.get("recorded_at") or doc.get("timestamp")
        if raw is None:
            return None
        if isinstance(raw, datetime):
            return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
        if isinstance(raw, str):
            text = raw.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(text)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                return None
        return None

    @classmethod
    def _water_level_cm(cls, doc: Dict[str, Any]) -> float:
        for key in ("water_level_cm", "water_level", "waterLevel"):
            if key in doc and doc[key] is not None:
                try:
                    return max(0.0, float(doc[key]))
                except (TypeError, ValueError):
                    continue
        return 0.0

    @classmethod
    def _rain_mm(cls, doc: Dict[str, Any]) -> float:
        for key in (
            "rainfall_intensity_mm",
            "rainfall_mm",
            "rainfall",
            "rain_mm",
            "rainfall_intensity",
        ):
            if key in doc and doc[key] is not None:
                try:
                    return max(0.0, float(doc[key]))
                except (TypeError, ValueError):
                    continue
        return 0.0

    @classmethod
    def _aggregate_readings(cls, readings: List[Dict[str, Any]], barangay_id: int) -> Dict[str, Any]:
        water_levels = [cls._water_level_cm(r) for r in readings]
        rainfall_samples = [cls._rain_mm(r) for r in readings]

        avg_water_level = sum(water_levels) / len(water_levels)
        max_water_level = max(water_levels)

        mid_point = len(water_levels) // 2
        if mid_point > 0:
            first_half_avg = sum(water_levels[:mid_point]) / mid_point
            second_half_avg = sum(water_levels[mid_point:]) / len(water_levels[mid_point:])
            threshold = first_half_avg * 0.02
            if second_half_avg > first_half_avg + threshold:
                trend = "rising"
            elif second_half_avg < first_half_avg - threshold:
                trend = "falling"
            else:
                trend = "stable"
        else:
            trend = "stable"

        latest_timestamp = cls._reading_time(readings[-1]) or datetime.now(timezone.utc)
        rainfall_intensity_mm = (
            sum(rainfall_samples) / len(rainfall_samples) if rainfall_samples else 0.0
        )

        logger.info(
            "Retrieved %s sensor readings for barangay %s",
            len(water_levels),
            barangay_id,
        )

        return {
            "avg_water_level": avg_water_level,
            "max_water_level": max_water_level,
            "trend": trend,
            "rainfall_intensity_mm": rainfall_intensity_mm,
            "timestamp": latest_timestamp.isoformat(),
            "readings_count": len(water_levels),
        }
    
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
                - rainfall_intensity_mm: Mean rainfall intensity (mm) when readings include a rainfall field; else 0.0
                - timestamp: Latest reading timestamp
                - readings_count: Number of readings aggregated
        """
        try:
            db = cls.get_db()
        except Exception as e:
            logger.warning(
                "MongoDB unavailable for barangay %s, using sensor fallback: %s",
                barangay_id,
                e,
            )
            return cls._empty_sensor_fallback()
        
        try:
            collection = db.get_collection("sensor_readings")
            cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)

            all_for_barangay = list(
                collection.find({"barangay_id": barangay_id}).sort("recorded_at", 1)
            )
            if not all_for_barangay:
                all_for_barangay = list(
                    collection.find({"barangay_id": barangay_id}).sort("timestamp", 1)
                )

            readings = [
                doc
                for doc in all_for_barangay
                if (t := cls._reading_time(doc)) is not None and t >= cutoff_time
            ]

            if not readings and all_for_barangay:
                logger.info(
                    "No sensor data in last %s minutes for barangay %s; using latest stored readings",
                    minutes,
                    barangay_id,
                )
                readings = all_for_barangay[-10:]

            if not readings:
                logger.warning(f"No sensor data found for barangay {barangay_id}")
                return cls._empty_sensor_fallback()

            return cls._aggregate_readings(readings, barangay_id)
            
        except Exception as e:
            logger.warning(
                "Error fetching sensor data for barangay %s, using fallback: %s",
                barangay_id,
                e,
            )
            return cls._empty_sensor_fallback()
