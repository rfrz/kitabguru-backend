import logging
from typing import Optional

from app.config import Settings

logger = logging.getLogger(__name__)


class LightLLMError(Exception):
    pass


class LightLLMClient:
    """
    A lightweight LLM wrapper that handles fallback mechanisms between
    Gemini and OpenAI-compatible providers.
    Used for small tasks like summarizing chat into an SDXL prompt.
    """
    def __init__(self, settings: Settings):
        self.settings = settings
        self.fallback_order = [
            p.strip().lower() 
            for p in self.settings.llm_fallback_order.split(",") 
            if p.strip()
        ]

    async def generate_image_prompt(self, conversation_text: str) -> str:
        """
        Translates a long Indonesian conversation into a concise English prompt
        for Cloudflare SDXL image generation.
        """
        system_instruction = (
            "You are an assistant that creates prompts for an image generation model (SDXL). "
            "Read the following Indonesian educational conversation, extract the core visual subject, "
            "and write a highly descriptive, concise English prompt (max 70 words). "
            "Focus on visual elements: subject, action, lighting, environment, and style "
            "(e.g., 'Islamic geometric art style, vibrant colors, high quality'). "
            "Output ONLY the prompt string, no markdown, no quotes, no conversational text."
        )

        for provider in self.fallback_order:
            try:
                if provider == "gemini":
                    result = await self._call_gemini(system_instruction, conversation_text)
                    if result: return result
                elif provider == "openai_compatible":
                    result = await self._call_openai_compatible(system_instruction, conversation_text)
                    if result: return result
                else:
                    logger.warning(f"Unknown LLM provider in fallback: {provider}")
            except Exception as e:
                logger.error(f"LightLLM provider '{provider}' failed: {e}")
                continue
                
        # If all fail, return a generic fallback
        logger.error("All LightLLM providers failed. Using generic fallback prompt.")
        return "An Islamic educational scene with geometric patterns and books, high quality, vibrant."

    async def _call_gemini(self, system: str, user_text: str) -> Optional[str]:
        if not self.settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not set")
            
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise ImportError("google-genai package not installed")

        client = genai.Client(api_key=self.settings.gemini_api_key)
        
        # We use sync call here, or run in threadpool if async is needed.
        # google-genai supports async via client.aio
        response = await client.aio.models.generate_content(
            model=self.settings.gemini_llm_model,
            contents=[system + "\n\nConversation:\n" + user_text],
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=150,
            )
        )
        return response.text.strip()

    async def _call_openai_compatible(self, system: str, user_text: str) -> Optional[str]:
        if not self.settings.openai_compatible_api_key or not self.settings.openai_compatible_base_url or not self.settings.openai_compatible_model:
            raise ValueError("OpenAI compatible config is missing")
            
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("openai package not installed")

        client = AsyncOpenAI(
            api_key=self.settings.openai_compatible_api_key,
            base_url=self.settings.openai_compatible_base_url
        )
        
        response = await client.chat.completions.create(
            model=self.settings.openai_compatible_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_text}
            ],
            temperature=0.3,
            max_tokens=150
        )
        return response.choices[0].message.content.strip()
