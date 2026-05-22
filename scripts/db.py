"""
db.py — Supabase client singleton.

Reads SUPABASE_URL and SUPABASE_SERVICE_KEY from environment.
Uses the service role key so the backend can bypass RLS when needed.
"""

import os
from supabase import create_client, Client

_client: Client | None = None


def get_client() -> Client:
    """Return the shared Supabase client, initialising it on first call."""
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_KEY")
        if not url or not key:
            raise EnvironmentError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in environment."
            )
        _client = create_client(url, key)
    return _client
