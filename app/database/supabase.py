"""
Supabase integration module.
Handles connections to Supabase PostgreSQL and household data retrieval.
"""

import os
from typing import Optional, List, Dict, Any
from supabase import create_client, Client
import logging

logger = logging.getLogger(__name__)


class SupabaseConnection:
    """
    Manages Supabase connection and operations.
    Connects using SUPABASE_URL and SUPABASE_KEY environment variables.
    """
    
    _client: Optional[Client] = None
    
    @classmethod
    def connect(cls) -> Client:
        """
        Establish connection to Supabase.
        Raises an exception if connection fails.
        
        Returns:
            Supabase client instance
        """
        try:
            supabase_url = os.getenv("SUPABASE_URL")
            supabase_key = os.getenv("SUPABASE_KEY")
            
            if not supabase_url or not supabase_key:
                raise ValueError("SUPABASE_URL or SUPABASE_KEY environment variables not set")
            
            cls._client = create_client(supabase_url, supabase_key)
            logger.info("Successfully connected to Supabase")
            
            return cls._client
            
        except Exception as e:
            logger.error(f"Failed to connect to Supabase: {str(e)}")
            raise
    
    @classmethod
    def get_client(cls) -> Client:
        """Get the Supabase client instance. Connects if not already connected."""
        if cls._client is None:
            cls.connect()
        return cls._client
    
    @classmethod
    def get_household_vulnerability(cls, barangay_id: int) -> Dict[str, Any]:
        """
        Fetch household data for a barangay and compute vulnerability metrics.
        Aggregates residents data to count:
        - elderly_count: age >= 60
        - infant_count: age <= 2
        - pregnant_count: pregnant residents
        - pwd_count: residents with disabilities
        
        Args:
            barangay_id: Identifier for the barangay
        
        Returns:
            Dictionary with vulnerability metrics:
                - household_id: Barangay ID
                - elderly_count: Number of elderly residents
                - infant_count: Number of infants
                - pregnant_count: Number of pregnant residents
                - pwd_count: Number of PWD residents
                - total_residents: Total residents in barangay
        """
        client = cls.get_client()
        
        try:
            # Query residents table filtered by barangay_id
            response = client.table("residents").select("*").eq("barangay_id", barangay_id).execute()
            
            residents = response.data if response.data else []
            
            if not residents:
                logger.warning(f"No residents found for barangay {barangay_id}")
                return {
                    "household_id": str(barangay_id),
                    "elderly_count": 0,
                    "infant_count": 0,
                    "pregnant_count": 0,
                    "pwd_count": 0,
                    "four_ps_count": 0,
                    "lactating_count": 0,
                    "solo_parent_count": 0,
                    "total_residents": 0
                }
            
            def _truthy(row: Dict[str, Any], *keys: str) -> bool:
                for k in keys:
                    v = row.get(k)
                    if v is True:
                        return True
                    if isinstance(v, (int, float)) and v != 0:
                        return True
                    if isinstance(v, str) and v.lower() in ("true", "1", "yes", "y"):
                        return True
                return False

            # Count vulnerability categories
            elderly_count = sum(1 for r in residents if r.get("age", 0) >= 60)
            infant_count = sum(1 for r in residents if r.get("age", 0) <= 2)
            pregnant_count = sum(1 for r in residents if r.get("is_pregnant", False))
            pwd_count = sum(1 for r in residents if r.get("is_pwd", False))
            four_ps_count = sum(
                1 for r in residents if _truthy(r, "is_4ps", "is_four_ps", "four_ps", "is_4ps_beneficiary")
            )
            lactating_count = sum(1 for r in residents if _truthy(r, "is_lactating", "lactating"))
            solo_parent_count = sum(1 for r in residents if _truthy(r, "is_solo_parent", "solo_parent"))
            
            logger.info(
                f"Retrieved vulnerability data for barangay {barangay_id}: "
                f"elderly={elderly_count}, infants={infant_count}, "
                f"pregnant={pregnant_count}, pwd={pwd_count}, "
                f"4ps={four_ps_count}, lactating={lactating_count}, solo_parent={solo_parent_count}, "
                f"total={len(residents)}"
            )
            
            return {
                "household_id": str(barangay_id),
                "elderly_count": elderly_count,
                "infant_count": infant_count,
                "pregnant_count": pregnant_count,
                "pwd_count": pwd_count,
                "four_ps_count": four_ps_count,
                "lactating_count": lactating_count,
                "solo_parent_count": solo_parent_count,
                "total_residents": len(residents)
            }
            
        except Exception as e:
            logger.error(f"Error fetching household vulnerability data: {str(e)}")
            raise
