import cohere
from typing import List
from app.config import settings

class EmbeddingService:
    def __init__(self):
        self.api_key = settings.cohere_api_key
        self.client = None
        if self.api_key and "dummy" not in self.api_key:
            try:
                self.client = cohere.Client(api_key=self.api_key)
            except Exception as e:
                pass

    def embed_texts_with_usage(self, texts: List[str], input_type: str = "search_document") -> tuple[List[List[float]], int]:
        """
        Generate Cohere embeddings and return both vectors and input token count.
        """
        if not texts:
            return [], 0

        # Graceful fallback to dummy 1024-dimension float vectors if API client is not configured
        if self.client is None:
            estimated_tokens = sum(max(1, len(t) // 4) for t in texts)
            return [[0.0] * 1024 for _ in texts], estimated_tokens

        import time
        last_err = None
        for attempt in range(3):
            try:
                response = self.client.embed(
                    texts=texts,
                    model="embed-english-v3.0",
                    input_type=input_type,
                    embedding_types=["float"]
                )
                tokens = 0
                if hasattr(response, "meta") and response.meta:
                    if hasattr(response.meta, "billed_units") and response.meta.billed_units:
                        tokens = getattr(response.meta.billed_units, "input_tokens", 0)
                if not tokens:
                    tokens = sum(max(1, len(t) // 4) for t in texts)

                if hasattr(response.embeddings, "float_") and response.embeddings.float_:
                    embs = [list(e) for e in response.embeddings.float_]
                elif hasattr(response, "embeddings") and response.embeddings:
                    embs = [list(e) for e in response.embeddings]
                else:
                    raise ValueError("Unexpected Cohere API response format")
                return embs, tokens
            except Exception as e:
                last_err = e
                # Exponential backoff: sleep 2, 4 seconds
                time.sleep(2 ** (attempt + 1))
                
        # Only raise if client is configured (production mode) to allow tasks to fail cleanly
        if self.client is not None:
            raise last_err
            
        estimated_tokens = sum(max(1, len(t) // 4) for t in texts)
        return [[0.0] * 1024 for _ in texts], estimated_tokens

    def embed_texts(self, texts: List[str], input_type: str = "search_document") -> List[List[float]]:
        """
        Generate Cohere embeddings for a list of texts. Backward-compatible.
        """
        embs, _ = self.embed_texts_with_usage(texts, input_type)
        return embs

    def embed_text_with_usage(self, text: str, input_type: str = "search_document") -> tuple[List[float], int]:
        """
        Generate Cohere embedding for a single text and return vector and token count.
        """
        embs, tokens = self.embed_texts_with_usage([text], input_type)
        return embs[0] if embs else [0.0] * 1024, tokens

    def embed_text(self, text: str, input_type: str = "search_document") -> List[float]:
        """Generate embedding for a single text string. Backward-compatible."""
        emb, _ = self.embed_text_with_usage(text, input_type)
        return emb
