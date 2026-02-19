# services/supabase_client.py
"""
Supabase Client — centralised DB helper for all agents.
"""

import os
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()

_client = None


def get_supabase_client():
    """Lazy-initialise and return the Supabase client singleton."""
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            print("⚠️  SUPABASE_URL / SUPABASE_KEY not set — DB push disabled")
            return None
        from supabase import create_client
        _client = create_client(url, key)
    return _client


def push_to_table(table: str, data: dict):
    """Insert a row into a Supabase table. Returns the response or None on error."""
    sb = get_supabase_client()
    if sb is None:
        return None
    try:
        res = sb.table(table).insert(data).execute()
        print(f"✅ Pushed to '{table}' table")
        return res
    except Exception as e:
        print(f"⚠️  Supabase insert to '{table}' failed: {e}")
        return None


def upsert_to_table(table: str, data: dict):
    """Upsert a row (insert or update on conflict). Returns the response or None."""
    sb = get_supabase_client()
    if sb is None:
        return None
    try:
        res = sb.table(table).upsert(data).execute()
        print(f"✅ Upserted to '{table}' table")
        return res
    except Exception as e:
        print(f"⚠️  Supabase upsert to '{table}' failed: {e}")
        return None


def get_from_table(table: str, filters: dict = None):
    """Query rows from a table with optional eq filters."""
    sb = get_supabase_client()
    if sb is None:
        return []
    try:
        q = sb.table(table).select("*")
        if filters:
            for col, val in filters.items():
                q = q.eq(col, val)
        res = q.execute()
        return res.data if res.data else []
    except Exception as e:
        print(f"⚠️  Supabase query on '{table}' failed: {e}")
        return []


def move_expired_tenders():
    """
    Move tenders whose submission_deadline < today from 'tenders'
    to 'expired_tenders'.
    """
    sb = get_supabase_client()
    if sb is None:
        return

    today_str = date.today().isoformat()  # 'YYYY-MM-DD'

    try:
        # Fetch tenders with deadline before today
        expired = (
            sb.table("tenders")
            .select("*")
            .lt("submission_deadline", today_str)
            .execute()
        )

        if not expired.data:
            print("📋 No expired tenders to move")
            return

        print(f"🔄 Moving {len(expired.data)} expired tender(s) ...")

        for row in expired.data:
            # Copy to expired_tenders (strip the original id)
            expired_row = {
                "project_name":        row.get("project_name"),
                "issued_by":           row.get("issued_by"),
                "category":            row.get("category"),
                "submission_deadline":  row.get("submission_deadline"),
                "tender_data":         row.get("tender_data"),
                "expired_at":          datetime.utcnow().isoformat(),
            }
            sb.table("expired_tenders").insert(expired_row).execute()

            # Delete from active tenders
            sb.table("tenders").delete().eq("id", row["id"]).execute()

        print(f"✅ Moved {len(expired.data)} tender(s) to expired_tenders")

    except Exception as e:
        print(f"⚠️  Expire-tenders failed: {e}")
