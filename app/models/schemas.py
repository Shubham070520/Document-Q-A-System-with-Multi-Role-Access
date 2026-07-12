from pydantic import BaseModel, Field
from typing import List, Optional


class QueryRequest(BaseModel):
    query: str = Field(..., description="The query to ask against documents")

class SourceResponse(BaseModel):
    filename: str
    page_number: Optional[int] = None
    similarity_score: float

class QueryResponse(BaseModel):
    answer: str
    confidence_score: float
    sources: List[SourceResponse]
    quota_remaining: int
