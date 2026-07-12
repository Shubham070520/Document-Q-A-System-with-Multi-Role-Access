from app.config import settings

class LLMService:
    def __init__(self):
        self.api_key = settings.groq_api_key
        self.client = None
        if self.api_key and "dummy" not in self.api_key:
            try:
                import groq
                self.client = groq.Groq(api_key=self.api_key)
            except Exception:
                pass

    def generate_completion(self, prompt: str, system_prompt: str = None, model: str = "llama-3.1-8b-instant") -> dict:
        """
        Sends completion request to Groq LLM.
        Returns: {
            "text": str,
            "input_tokens": int,
            "output_tokens": int
        }
        """
        if self.client is None:
            # Dev mock fallback
            return {
                "text": "Based on the provided documents, this is a mock answer for verification.",
                "input_tokens": 100,
                "output_tokens": 50
            }

        import time
        last_err = None
        for attempt in range(3):
            try:
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})

                completion = self.client.chat.completions.create(
                    messages=messages,
                    model=model,
                    temperature=0.0  # Greedy decoding for consistent fact-grounding
                )
                
                text = completion.choices[0].message.content
                usage = completion.usage
                
                return {
                    "text": text,
                    "input_tokens": usage.prompt_tokens if usage else 0,
                    "output_tokens": usage.completion_tokens if usage else 0
                }
            except Exception as e:
                last_err = e
                # Exponential backoff: sleep 2, 4 seconds
                time.sleep(2 ** (attempt + 1))

        return {
            "text": f"Error calling Groq after retries: {str(last_err)}",
            "input_tokens": 0,
            "output_tokens": 0
        }

    def generate_response(self, prompt: str) -> str:
        """Backward compatible signature returning just the text answer."""
        res = self.generate_completion(prompt)
        return res["text"]
