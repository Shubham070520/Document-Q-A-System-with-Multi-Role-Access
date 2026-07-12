from supabase import create_client, Client
import redis.asyncio as aioredis
from app.config import settings

# Initialize Supabase clients (standard client and service-role client for background updates)
supabase: Client = None
supabase_admin: Client = None

try:
    if settings.supabase_url and settings.supabase_anon_key and "dummy" not in settings.supabase_anon_key:
        supabase = create_client(settings.supabase_url, settings.supabase_anon_key)
except Exception as e:
    pass

try:
    if settings.supabase_url and settings.supabase_service_role_key and "dummy" not in settings.supabase_service_role_key:
        supabase_admin = create_client(settings.supabase_url, settings.supabase_service_role_key)
except Exception as e:
    pass

# Async Redis Connection Manager
redis_client = aioredis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)

def get_supabase() -> Client:
    """Dependency injector for Supabase standard client."""
    if supabase is None:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail="Supabase standard client is unconfigured. Provide a valid SUPABASE_ANON_KEY in .env."
        )
    return supabase

def get_supabase_admin() -> Client:
    """Dependency injector for Supabase admin client."""
    if supabase_admin is None:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail="Supabase admin client is unconfigured. Provide a valid SUPABASE_SERVICE_ROLE_KEY in .env."
        )
    return supabase_admin

async def get_redis() -> aioredis.Redis:
    """Dependency injector for async Redis client."""
    return redis_client
