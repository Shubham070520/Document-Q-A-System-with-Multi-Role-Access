from fastapi import FastAPI

from app.config import settings
from app.api import auth, documents, qa, admin


app = FastAPI(
    title="Document Q&A System API",
    description="Secure multi-role Document Q&A System with pgvector, Cohere and Groq.",
    version="1.0.0"
)

# Register API Routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(qa.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")



@app.get("/health")
def health_check():
    """Health diagnostic route to check api status and system settings configuration."""
    return {
        "status": "healthy",
        "settings_loaded": {
            "supabase_url": settings.supabase_url != "https://dummy-project-id.supabase.co",
            "cohere_configured": settings.cohere_api_key != "dummy-cohere-api-key",
            "groq_configured": settings.groq_api_key != "dummy-groq-api-key"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)

