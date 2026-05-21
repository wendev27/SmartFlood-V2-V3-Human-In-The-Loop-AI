"""
Inventory awareness layer for operational intelligence.
Manages mocked warehouse stock and calculates recommendation adjustments.
"""

from typing import Dict, Any, Tuple, List

import logging

logger = logging.getLogger(__name__)


class InventoryService:
    """
    Simulates a connection to an inventory management system.
    Provides mocked data for available relief supplies and evaluates requested quantities against stock.
    """

    # Mocked available stock
    _MOCK_INVENTORY = {
        "Food Packs": 2500,
        "Water (Liters)": 5000,
        "Medicine Kits": 400,
        "Hygiene Kits": 1000,
        "Blankets": 800,
    }

    @classmethod
    def get_available_stock(cls) -> Dict[str, int]:
        """Returns the currently available stock levels."""
        return cls._MOCK_INVENTORY.copy()

    @classmethod
    def check_and_adjust_recommendations(
        cls, ideal_recommendations: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], bool]:
        """
        Validates requested resource quantities against available inventory.
        Reduces recommended quantities if they exceed stock.

        Returns:
            Tuple containing:
            - Adjusted recommendations list
            - List of inventory constraints (shortages identified)
            - Boolean indicating if any adjustments were made (shortage exists)
        """
        available_stock = cls.get_available_stock()
        adjusted_recommendations = []
        inventory_constraints = []
        has_shortage = False

        for rec in ideal_recommendations:
            item_name = rec["item"]
            
            # Handle string quantities like "1000L" -> "1000"
            raw_quantity = str(rec["quantity"])
            numeric_qty = 0
            unit = ""
            
            import re
            match = re.match(r"^(\d+)([a-zA-Z]*)$", raw_quantity.strip())
            if match:
                numeric_qty = int(match.group(1))
                unit = match.group(2)
            else:
                try:
                    numeric_qty = int(raw_quantity)
                except ValueError:
                    # If it's completely unparseable, just pass it through
                    adjusted_recommendations.append(rec)
                    continue

            # Lookup stock. For water, we map "Water" to "Water (Liters)" if needed
            stock_key = item_name
            if item_name == "Water":
                stock_key = "Water (Liters)"
                
            available = available_stock.get(stock_key)
            
            if available is not None and numeric_qty > available:
                has_shortage = True
                allocated_qty = available
                shortage_reason = f"Warehouse stock depleted. Only {allocated_qty} {unit} available out of requested {numeric_qty} {unit}."
                
                inventory_constraints.append({
                    "item": item_name,
                    "requested": numeric_qty,
                    "allocated": allocated_qty,
                    "shortage_reason": shortage_reason
                })
                
                # Update the recommendation with the constrained amount
                adjusted_rec = rec.copy()
                adjusted_rec["quantity"] = f"{allocated_qty}{unit}" if unit else allocated_qty
                
                # Append constraint info to reason
                adjusted_rec["reason"] += f" (Note: Adjusted down due to inventory limits)"
                adjusted_recommendations.append(adjusted_rec)
                
                logger.warning(f"Inventory shortage for {item_name}: requested {numeric_qty}, allocated {allocated_qty}")
            else:
                adjusted_recommendations.append(rec)

        return adjusted_recommendations, inventory_constraints, has_shortage
