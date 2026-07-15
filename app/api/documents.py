from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Query
from app.api.dependencies import get_current_user_profile, get_current_admin_user, get_supabase_client
from app.database import supabase_admin
from supabase import Client
import uuid
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

router = APIRouter(prefix="/documents", tags=["Documents"])

STORAGE_BUCKET = "documents"

class ShareRequest(BaseModel):
    document_id: str
    user_id: str

@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile = File(...),
    target_user_id: Optional[str] = Query(None, description="Optional user ID to assign this document to (Admins only)"),
    current_user: Dict[str, Any] = Depends(get_current_admin_user),
    db: Client = Depends(get_supabase_client)
):
    """
    Upload a document, store it in Supabase Storage, and queue it for
    asynchronous parsing and embedding via a Celery worker (Admins only).
    """
    filename = file.filename
    file_ext = filename.split(".")[-1].lower() if "." in filename else ""
    if file_ext not in ["pdf", "txt"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file format. Only PDF and TXT are supported."
        )

    owner_id = target_user_id if target_user_id else current_user["id"]
    doc_id = str(uuid.uuid4())

    try:
        db_res = db.table("documents").insert({
            "id": doc_id,
            "user_id": owner_id,
            "filename": filename,
            "status": "pending"
        }).execute()

        if not db_res.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database failed to generate document record"
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database initialization error: {str(e)}"
        )

    storage_path = f"{doc_id}_{filename}"

    try:
        file_bytes = await file.read()

        # Upload to Supabase Storage — the worker (separate container) will
        # fetch it from here rather than relying on local disk.
        supabase_admin.storage.from_(STORAGE_BUCKET).upload(
            storage_path,
            file_bytes,
            {"content-type": file.content_type or "application/octet-stream"}
        )

        from app.workers.tasks import process_document_task
        process_document_task.delay(doc_id, storage_path, file_ext)

        return {
            "message": "Document uploaded successfully and queued via Celery background worker",
            "document_id": doc_id,
            "filename": filename,
            "status": "pending"
        }

    except Exception as e:
        # Best-effort cleanup of the Storage object if something failed after upload
        try:
            supabase_admin.storage.from_(STORAGE_BUCKET).remove([storage_path])
        except Exception:
            pass

        try:
            db.table("documents").update({"status": "failed"}).eq("id", doc_id).execute()
        except Exception:
            pass

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion queue failed: {str(e)}"
        )

@router.get("", response_model=List[Dict[str, Any]])
async def list_documents(
    current_user: Dict[str, Any] = Depends(get_current_user_profile),
    db: Client = Depends(get_supabase_client)
):
    try:
        res = db.table("documents").select("*").order("created_at", desc=True).execute()
        return res.data or []
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list documents: {str(e)}"
        )

@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user_profile),
    db: Client = Depends(get_supabase_client)
):
    try:
        doc_res = db.table("documents").select("*").eq("id", document_id).execute()
        if not doc_res.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found or access denied"
            )

        doc = doc_res.data[0]
        storage_path = f"{document_id}_{doc['filename']}"

        db.table("documents").delete().eq("id", document_id).execute()

        # Clean up the underlying file in Storage too — best-effort, don't
        # fail the whole delete if this errors.
        try:
            supabase_admin.storage.from_(STORAGE_BUCKET).remove([storage_path])
        except Exception as e_storage:
            print(f"Warning: failed to remove storage object {storage_path}: {e_storage}")

        return {"message": "Document deleted successfully", "document_id": document_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {str(e)}"
        )

@router.post("/share")
async def share_document(
    payload: ShareRequest,
    current_user: Dict[str, Any] = Depends(get_current_user_profile),
    db: Client = Depends(get_supabase_client)
):
    """
    Share a document with another user by email (or user ID fallback).
    Requires document ownership or admin status.
    """
    try:
        # Check if the document exists and is owned by the user or if current user is admin
        doc_res = db.table("documents").select("*").eq("id", payload.document_id).execute()
        if not doc_res.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found or access denied"
            )
            
        doc = doc_res.data[0]
        if doc["user_id"] != current_user["id"] and current_user["role"] != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Only the document owner or an admin can share this document"
            )

        target_user_id = None
        
        # Resolve target email using Supabase Admin Auth
        try:
            if supabase_admin is not None:
                users_res = supabase_admin.auth.admin.list_users()
                # list_users returns an object that has user details
                users_list = getattr(users_res, "users", []) or users_res
                for u in users_list:
                    if getattr(u, "email", None) == payload.user_id:
                        target_user_id = getattr(u, "id", None)
                        break
        except Exception:
            pass

        # If not found via email lookup, check if input is a valid UUID user ID directly
        if not target_user_id:
            try:
                uuid.UUID(payload.user_id)
                target_user_id = payload.user_id
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Target user not found with email/id: {payload.user_id}"
                )

        if target_user_id == current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot share a document with yourself"
            )

        # Record share in document_shares
        share_res = db.table("document_shares").insert({
            "document_id": payload.document_id,
            "shared_with_user_id": target_user_id
        }).execute()
        return {
            "message": f"Document shared successfully with {payload.user_id}",
            "shared_with": target_user_id
        }
    except HTTPException:
        raise
    except Exception as e:
        if "unique" in str(e).lower():
            return {"message": f"Document is already shared with this user"}
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to share document: {str(e)}"
        )

