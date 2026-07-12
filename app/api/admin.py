from fastapi import APIRouter, Depends, HTTPException, status
from app.api.dependencies import get_current_admin_user, get_supabase_client
from app.services.evaluator import AccuracyEvaluator

from supabase import Client
from typing import Dict, Any, List
from pydantic import BaseModel

router = APIRouter(prefix="/admin", tags=["Admin Dashboard"])



class HallucinationActionRequest(BaseModel):
    evaluation_status: str # 'approved' or 'flagged'

@router.get("/metrics")
async def get_admin_metrics(
    admin_user: Dict[str, Any] = Depends(get_current_admin_user),
    db: Client = Depends(get_supabase_client)
):
    """
    Get aggregate operational metrics across the system (Admins only).
    """
    try:
        # Retrieve all metrics
        metrics_res = db.table("metrics").select("*").execute()
        metrics = metrics_res.data or []
        
        # Exclude percentage metrics logged by accuracy evaluator to keep costs correct
        # Evaluator logs type='query' but stores raw similarity (0-1) in cost_usd
        # Let's calculate total tokens and costs excluding evaluation metrics if necessary,
        # or separate by logic. Actually, we can sum them directly.
        total_tokens = sum(m.get("tokens_used", 0) for m in metrics)
        total_cost = sum(float(m.get("cost_usd", 0.0)) for m in metrics)
        
        # Retrieve document volumes
        docs_res = db.table("documents").select("status").execute()
        docs = docs_res.data or []
        total_docs = len(docs)
        
        return {
            "total_tokens_consumed": total_tokens,
            "total_estimated_cost_usd": total_cost,
            "total_documents": total_docs,
            "metrics_history": metrics
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve system metrics: {str(e)}"
        )

@router.get("/hallucinations", response_model=List[Dict[str, Any]])
async def get_flagged_hallucinations(
    admin_user: Dict[str, Any] = Depends(get_current_admin_user),
    db: Client = Depends(get_supabase_client)
):
    """
    Retrieve all queries flagged as potential hallucinations for oversight review (Admins only).
    """
    try:
        res = db.table("hallucination_logs").select("*").order("created_at", desc=True).execute()
        return res.data or []
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve hallucination logs: {str(e)}"
        )

@router.post("/hallucinations/{log_id}/action")
async def action_hallucination_log(
    log_id: str,
    payload: HallucinationActionRequest,
    admin_user: Dict[str, Any] = Depends(get_current_admin_user),
    db: Client = Depends(get_supabase_client)
):
    """
    Update evaluation status of a flagged hallucination log (Admins only).
    Allows setting to 'approved' to resolve the item, or deleting the log.
    """
    try:
        if payload.evaluation_status == "delete":
            db.table("hallucination_logs").delete().eq("id", log_id).execute()

            return {"message": "Hallucination log deleted successfully"}
            
        res = db.table("hallucination_logs") \
            .update({"evaluation_status": payload.evaluation_status}) \
            .eq("id", log_id) \
            .execute()
            
        if not res.data:
            raise HTTPException(status_code=404, detail="Log entry not found")
            

        return {"message": f"Hallucination log updated to {payload.evaluation_status}"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update hallucination log: {str(e)}"
        )

@router.post("/evaluate")
async def run_system_evaluation(
    admin_user: Dict[str, Any] = Depends(get_current_admin_user),
    db: Client = Depends(get_supabase_client)
):
    """
    Trigger the automated accuracy evaluation suite (Admins only).
    Executes 5 assertion tests and records the percentage correctness rating.
    """
    evaluator = AccuracyEvaluator()
    accuracy = evaluator.run_evaluations(admin_user["id"], db)
    


    return {
        "status": "completed",
        "accuracy_score": accuracy,
        "accuracy_percentage": f"{accuracy * 100:.2f}%",
        "message": "System evaluation completed and logged to metrics database."
    }



