from fastapi import APIRouter, Depends, HTTPException, status
from app.models.schemas import QueryRequest, QueryResponse, SourceResponse
from app.api.dependencies import get_current_user_profile, get_supabase_client
from app.database import redis_client
from app.services.embedding import EmbeddingService
from app.services.llm import LLMService
from app.services.guardrails import GuardrailsService

from supabase import Client
import datetime
from typing import Dict, Any

router = APIRouter(prefix="/qa", tags=["Q&A Query"])

@router.post("/query", response_model=QueryResponse)
async def ask_question(
    payload: QueryRequest,
    current_user: Dict[str, Any] = Depends(get_current_user_profile),
    db: Client = Depends(get_supabase_client)
):
    """
    Execute a real-time Retrieval-Augmented Generation (RAG) query.
    1. Check Redis daily query rate limits (fallback to DB metrics count if Redis is down).
    2. Embed user query with Cohere search_query.
    3. Perform cosine similarity vector search against public.document_chunks via Supabase match_document_chunks RPC (respects DB RLS).
    4. Construct strict system prompts and invoke Groq LLM (llama-3.1-8b-instant) for response.
    5. Perform grounding evaluation check using dynamic thresholds.
    6. Record token usage and costs inside public.metrics table.
    """
    query_text = payload.query.strip()
    if not query_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query text cannot be empty"
        )

    user_id = current_user["id"]

    # Retrieve quality settings (hardcoded to architecture specifications)
    sim_threshold = 0.25
    conf_threshold = 0.7

    # 1. Rate Limiting check
    quota_remaining = 10
    redis_failed = False
    
    try:
        current_date = datetime.date.today().strftime('%Y%m%d')
        rate_limit_key = f"rate_limit:{user_id}:{current_date}"
        current_count = await redis_client.incr(rate_limit_key)
        if current_count == 1:
            await redis_client.expire(rate_limit_key, 86400) # Set 24 hour TTL on first request
        
        if current_count > 10:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Daily query quota reached (10/10)"
            )
        quota_remaining = max(0, 10 - current_count)
    except HTTPException:
        raise
    except Exception as redis_err:
        redis_failed = True
        print(f"Redis rate limiting connection fallback: {redis_err}")

    # Fallback to Database metrics audit count if Redis is down
    if redis_failed:
        try:
            today_start = datetime.datetime.now(datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            metrics_res = db.table("metrics") \
                .select("id") \
                .eq("user_id", user_id) \
                .eq("metric_type", "query") \
                .gte("created_at", today_start.isoformat()) \
                .execute()
            
            queries_today = len(metrics_res.data) if metrics_res.data else 0
            if queries_today >= 10:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Daily query quota reached (10/10)"
                )
            quota_remaining = max(0, 10 - (queries_today + 1))
        except HTTPException:
            raise
        except Exception as db_err:
            print(f"Fallback database rate limit check failed: {db_err}")



    # 2. Embed query
    embedding_service = EmbeddingService()
    query_embedding, cohere_tokens = embedding_service.embed_text_with_usage(query_text, input_type="search_query")

    # 3. Vector Similarity Search via RPC (respects RLS based on auth headers)
    matched_chunks = []
    
    try:
        rpc_res = db.rpc("match_document_chunks", {
            "query_embedding": query_embedding,
            "similarity_threshold": sim_threshold,
            "match_count": 5
        }).execute()
        matched_chunks = rpc_res.data or []
    except Exception as e:
        if "dummy" in str(db.supabase_url):
            pass
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database search query failed: {str(e)}"
            )
    
    # Local development mock search results fallback if db is not present
    if not matched_chunks and "dummy" in str(db.supabase_url):
        if "antigravity" in query_text.lower():
            matched_chunks = [
                {
                    "filename": "mock_antigravity.txt",
                    "page_number": 1,
                    "content": "Antigravity is a project designed by Google Deepmind pair programming team.",
                    "similarity_score": 0.88
                }
            ]

    # Handle threshold starvation (no chunks matched)
    if not matched_chunks:
        # Save metrics for embedding call
        try:
            db.table("metrics").insert({
                "user_id": user_id,
                "metric_type": "query",
                "tokens_used": int(cohere_tokens),
                "cost_usd": cohere_tokens * (0.10 / 1_000_000)
            }).execute()
        except Exception as e:
            print(f"Error logging metrics: {e}")

        return QueryResponse(
            answer=f"I cannot confidently answer this question based on your uploaded documents. (Similarity threshold filter of {sim_threshold} failed to yield matching fragments)",
            confidence_score=0.0,
            sources=[],
            quota_remaining=quota_remaining
        )

    # 4. Construct Context Prompt for Groq Cloud LLM
    context_snippets = []
    sources = []
    
    for idx, chunk in enumerate(matched_chunks, 1):
        filename = chunk.get("filename", "unknown")
        page_num = chunk.get("page_number", 1)
        content = chunk.get("content", "")
        similarity = chunk.get("similarity_score", 0.0)
        
        context_snippets.append(f"[{idx}] Source: {filename}, Page: {page_num} - \"{content}\"")
        sources.append(SourceResponse(
            filename=filename,
            page_number=page_num,
            similarity_score=similarity
        ))
        
    context_str = "\n".join(context_snippets)
    
    prompt = f"""Context Chunks:
{context_str}

Query: {query_text}

Answer the query directly using only the context chunks. Do NOT prefix the response with statements like "Based on the provided context chunks" or "According to the context". Answer concisely and directly. If the answer is not supported, reply with "UNSUPPORTED"."""

    # 5. Generate Answer via Groq
    llm_service = LLMService()
    completion_res = llm_service.generate_completion(prompt)
    answer = completion_res["text"].strip()
    
    groq_inference_input = completion_res.get("input_tokens", 0)
    groq_inference_output = completion_res.get("output_tokens", 0)

    # 6. Execute Hallucination Check (Context vs Answer)
    guardrails_service = GuardrailsService()
    eval_res = guardrails_service.verify_grounding(context_str, answer)
    confidence_score = eval_res["score"]
    
    groq_eval_input = eval_res.get("input_tokens", 0)
    groq_eval_output = eval_res.get("output_tokens", 0)

    is_hallucinated = confidence_score < conf_threshold
    
    if is_hallucinated:
        answer_to_return = f"I cannot confidently answer this question based on your uploaded documents. (Confidence Score: {confidence_score:.2f} is below the safety threshold of {conf_threshold:.2f})"
        evaluation_status = "flagged"
    else:
        answer_to_return = answer
        evaluation_status = "approved"
        # If the model returned UNSUPPORTED, confidence score should be 0.0
        if answer == "UNSUPPORTED":
            confidence_score = 0.0

    # Log to hallucination_logs if evaluation status is flagged
    if is_hallucinated:
        try:
            db.table("hallucination_logs").insert({
                "user_id": user_id,
                "query": query_text,
                "response": answer, # log the original hallucinated text
                "context_retrieved": context_str,
                "confidence_score": confidence_score,
                "evaluation_status": evaluation_status
            }).execute()
        except Exception as e:
            print(f"Error logging hallucination check: {e}")

    # 7. Token Counting & Billing Logging
    total_input_tokens = cohere_tokens + groq_inference_input + groq_eval_input
    total_output_tokens = groq_inference_output + groq_eval_output
    total_tokens = total_input_tokens + total_output_tokens
    
    # Calculate costs
    cohere_cost = cohere_tokens * (0.10 / 1_000_000)
    groq_input_cost = (groq_inference_input + groq_eval_input) * (0.05 / 1_000_000)
    groq_output_cost = (groq_inference_output + groq_eval_output) * (0.08 / 1_000_000)
    cost_usd = cohere_cost + groq_input_cost + groq_output_cost

    try:
        db.table("metrics").insert({
            "user_id": user_id,
            "metric_type": "query",
            "tokens_used": int(total_tokens),
            "cost_usd": cost_usd
        }).execute()
    except Exception as e:
        print(f"Error logging query metrics: {e}")

    return QueryResponse(
        answer=answer_to_return,
        confidence_score=confidence_score,
        sources=sources,
        quota_remaining=quota_remaining
    )

