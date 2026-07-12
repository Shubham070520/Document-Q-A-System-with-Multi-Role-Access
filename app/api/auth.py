from fastapi import APIRouter, Depends
from app.api.dependencies import get_current_user_profile
from typing import Dict, Any

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.get("/me")
def get_current_user(current_user: Dict[str, Any] = Depends(get_current_user_profile)):
    """
    Get the profile details (ID, role, email) of the currently authenticated user.
    Useful for clients to verify session status and retrieve user metadata.
    """
    return current_user
