import asyncio
from app.database.supabase import SupabaseConnection

async def main():
    client = SupabaseConnection.get_client()
    try:
        res = client.table("barangays").select("id").execute()
        print("Barangays table:", res.data)
    except Exception as e:
        print("Error checking barangays table:", e)
        
    try:
        res2 = client.table("residents").select("barangay_id").execute()
        ids = list(set([r["barangay_id"] for r in res2.data]))
        print("Barangay IDs from residents:", ids)
    except Exception as e:
        print("Error checking residents table:", e)

asyncio.run(main())
