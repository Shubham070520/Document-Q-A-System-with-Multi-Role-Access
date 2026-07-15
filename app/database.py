from supabase import create_client, Client
import redis.asyncio as aioredis
from app.config import settings

# Initialize Supabase clients (standard client and service-role client for background updates)
supabase: Client = None
supabase_admin: Client = None

def mask_key(key: str) -> str:
    if not key:
        return "None"
    if len(key) <= 12:
        return "***"
    return f"{key[:6]}...{key[-6:]} (len: {len(key)})"

print("\n=== [STARTUP DIAGNOSTICS] ===")
print(f"SUPABASE_URL: {settings.supabase_url}")
print(f"SUPABASE_ANON_KEY: {mask_key(settings.supabase_anon_key)}")
print(f"SUPABASE_SERVICE_ROLE_KEY: {mask_key(settings.supabase_service_role_key)}")

# Mask credentials in Redis URL for secure logging
redis_log_url = settings.redis_url
if "@" in settings.redis_url:
    try:
        parts = settings.redis_url.split("@")
        redis_log_url = "redis://****@" + parts[-1]
    except Exception:
        redis_log_url = "redis://****@..."
print(f"REDIS_URL: {redis_log_url}")
print("=============================\n")

try:
    if settings.supabase_url and settings.supabase_anon_key and "dummy" not in settings.supabase_anon_key:
        print("Initializing standard Supabase Client...")
        supabase = create_client(settings.supabase_url, settings.supabase_anon_key)
        print("Standard Supabase Client initialized successfully.")
except Exception as e:
    print(f"[ERROR] Failed to initialize standard Supabase client: {e}")

try:
    if settings.supabase_url and settings.supabase_service_role_key and "dummy" not in settings.supabase_service_role_key:
        print("Initializing Supabase Admin Client...")
        supabase_admin = create_client(settings.supabase_url, settings.supabase_service_role_key)
        print("Supabase Admin Client initialized successfully.")
except Exception as e:
    print(f"[ERROR] Failed to initialize Supabase admin client: {e}")

# Async Redis Connection Manager
try:
    redis_client = aioredis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
except Exception as e:
    print(f"[ERROR] Failed to initialize Redis client: {e}")
    redis_client = None

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
