from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.get("/me")
def get_current_user():
    return {"message": "Auth endpoint skeleton"}
