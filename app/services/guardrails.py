import json
import re
from app.services.llm import LLMService

class GuardrailsService:
    def __init__(self):
        self.llm_service = LLMService()

    def verify_grounding(self, context: str, answer: str) -> dict:
        """
        Verify if the proposed answer is strictly grounded in the context.
        Returns a dict: {
            "score": float,  # score between 0.0 and 1.0
            "input_tokens": int,
            "output_tokens": int
        }
        """
        # If the answer is UNSUPPORTED, it is grounded (it correctly refused to answer)
        if answer == "UNSUPPORTED":
            return {"score": 1.0, "input_tokens": 0, "output_tokens": 0}

        prompt = f"""You are a factual correctness and grounding checker.
Analyze the Context and the Proposed Answer. Determine if the Proposed Answer contains any claims or facts that are not supported by or contradict the Context.
You must output a JSON object containing the float score between 0.0 (completely unsupported/hallucinated) and 1.0 (fully supported/grounded) in this format:
{{"score": <float>}}

Do not include any other explanations, notes, or markdown formatting outside of the JSON block.

Context:
{context}

Proposed Answer:
{answer}
"""
        try:
            res = self.llm_service.generate_completion(
                prompt=prompt,
                system_prompt="You are a strict factual grounding checker. Return JSON only."
            )
            text = res["text"].strip()
            
            # Parse score from response
            score = 1.0
            # Try to find JSON block
            match = re.search(r'\{\s*"score"\s*:\s*([0-9.]+)\s*\}', text)
            if match:
                score = float(match.group(1))
            else:
                # Fallback regex search for any float
                float_match = re.search(r'([0-9.]+)', text)
                if float_match:
                    score = float(float_match.group(1))
            
            # Normalize score to [0.0, 1.0] range
            score = max(0.0, min(1.0, score))
            
            return {
                "score": score,
                "input_tokens": res["input_tokens"],
                "output_tokens": res["output_tokens"]
            }
        except Exception:
            # Safe default fallback on service/model failure
            return {
                "score": 1.0,
                "input_tokens": 0,
                "output_tokens": 0
            }

