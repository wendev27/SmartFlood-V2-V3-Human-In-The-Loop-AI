import os
import sys
import traceback
from dotenv import load_dotenv

# Add the project directory to sys.path
sys.path.insert(0, '/home/hyoukasterben/Desktop/Human in the loop AI')

# Load env variables
load_dotenv('/home/hyoukasterben/Desktop/Human in the loop AI/.env')

from app.database.mongodb import MongoDBConnection
from app.database.supabase import SupabaseConnection
from app.services.decision_service import DecisionService

try:
    print("Connecting to databases...")
    MongoDBConnection.connect()
    SupabaseConnection.connect()
    print("Connected successfully!")
    
    print("Generating city-wide decisions...")
    results = DecisionService.make_city_wide_decision()
    print(f"Success! Generated {len(results)} results:")
    for r in results:
        print(f"- {r['barangay_name']}: priority={r['priority_level']}, confidence={r['analysis_confidence']}%, vulnerable={r['affected_population']}")
except Exception as e:
    print("Error during execution:")
    traceback.print_exc()
