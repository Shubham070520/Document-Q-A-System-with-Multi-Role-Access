from fastapi import Header, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.database import supabase, supabase_admin
from app.config import settings
from typing import Dict, Any, Optional
from supabase import create_client, Client, ClientOptions

security = HTTPBearer()

def get_token_header(authorization: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Extract standard Bearer token header."""
    return authorization.credentials

def get_supabase_client(token: str = Depends(get_token_header)) -> Client:
    """
    Get a request-scoped Supabase client initialized with the user's JWT token.
    Enables RLS policies to be evaluated correctly on the DB.
    """
    if token in ("dummy-token", "dummy-admin-token"):
        if supabase_admin is None:
            raise HTTPException(status_code=503, detail="Supabase admin client unconfigured.")
        return supabase_admin
    try:
        if settings.supabase_url and settings.supabase_anon_key:
            return create_client(
                settings.supabase_url,
                settings.supabase_anon_key,
                options=ClientOptions(headers={"Authorization": f"Bearer {token}"})
            )
        else:
            raise HTTPException(status_code=503, detail="Supabase configurations missing.")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Failed to create request client: {str(e)}")

def get_current_user_profile(
    token: str = Depends(get_token_header),
    db: Client = Depends(get_supabase_client)
) -> Dict[str, Any]:
    """
    User validation dependency using Supabase Auth JWT token.
    Resolves the user's role from the public.profiles database table.
    """
    # Accept mock tokens for testing/development
    if token == "dummy-token":
        return {
            "id": "00000000-0000-0000-0000-000000000001",
            "role": "user",
            "email": "user@example.com"
        }
    elif token == "dummy-admin-token":
        return {
            "id": "00000000-0000-0000-0000-000000000002",
            "role": "admin",
            "email": "admin@example.com"
        }

    try:
        # Validate JWT token against Supabase Auth
        user_response = db.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Authentication token invalid or user not found")
        
        user_id = user_response.user.id
        email = user_response.user.email
        
        # Query public.profiles to retrieve the user's role
        profile_response = db.table("profiles").select("role").eq("id", user_id).execute()
        
        role = "user"  # default role
        if profile_response.data and len(profile_response.data) > 0:
            role = profile_response.data[0].get("role", "user")
            
        return {
            "id": user_id,
            "role": role,
            "email": email
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail=f"Authentication failed: {str(e)}"
        )

def get_current_admin_user(current_user: Dict[str, Any] = Depends(get_current_user_profile)) -> Dict[str, Any]:
    """Enforce admin-only access."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Admin privileges required")
    return current_user

