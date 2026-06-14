import json
import logging
import re
from typing import Optional

from app.config import Settings

logger = logging.getLogger(__name__)


class LightLLMError(Exception):
    pass


class LightLLMClient:
    """
    A lightweight LLM wrapper that handles fallback mechanisms between
    Gemini and OpenAI-compatible providers.
    Used for small tasks like summarizing chat into an SDXL prompt or video scripts.
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
            "Read the following Indonesian educational conversation and extract the core factual subject. "
            "Write a highly descriptive, concise English prompt (max 70 words) to create an INFOGRAPHIC or ILLUSTRATED POSTER about the subject. "
            "Focus on visual elements: subject, typography layout, informative aesthetic, and style "
            "(e.g., 'Infographic style, clean layout, Islamic geometric borders, educational poster, high quality'). "
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

    async def generate_video_script(self, conversation_text: str) -> dict:
        """
        Generates a video narration script and detects the language of the conversation.
        Returns a dict with keys:
            - "language_code": detected language code (e.g., 'id-ID', 'en-US', 'ja-JP', 'ar-SA', etc.)
            - "script_text": the narration text matching the language, with short sentences (max 10-15 words).
        """
        system_instruction = (
            "You are an expert Islamic educator and scriptwriter. Your task is to write a video narration script based on the provided conversation history.\n"
            "Follow these rules strictly:\n"
            "1. Detect the language of the conversation history (e.g. Indonesian, English, Arabic, Japanese, etc.). The script MUST be written in this exact language.\n"
            "2. The narration must be educational, inspiring, calming, and concise. It should summarize the core educational topics discussed.\n"
            "3. Start the script with a peaceful greeting in the detected language (e.g., 'Bismillahirrahmanirrahim. Assalamualaikum...' or English equivalent like 'In the name of Allah, the Beneficent, the Merciful...').\n"
            "4. End with an inspiring closing sentence.\n"
            "5. The sentences must be very short and readable: maximum of 10-15 words per sentence. This is extremely important because the text will be displayed in large font on slides. Use clear, simple punctuation (periods, question marks, exclamation marks) to separate sentences.\n"
            "6. Output the result ONLY as a valid JSON object with the keys \"language_code\" and \"script_text\".\n"
            "Do not add any conversational responses, formatting or markdown outside the JSON.\n\n"
            "Example output:\n"
            "{\n"
            '  "language_code": "id-ID",\n'
            '  "script_text": "Bismillahirrahmanirrahim. Mari kita pelajari ilmu tajwid bersama. Membaca Al-Qur\'an harus dengan tartil. Semoga Allah memudahkan langkah kita."\n'
            "}"
        )

        fallback_result = {
            "language_code": "id-ID",
            "script_text": "Bismillahirrahmanirrahim. Selamat belajar bersama KitabGuru, platform pendidikan Islam berbasis AI."
        }

        for provider in self.fallback_order:
            try:
                if provider == "gemini":
                    result = await self._call_gemini(system_instruction, conversation_text, max_tokens=600)
                elif provider == "openai_compatible":
                    result = await self._call_openai_compatible(system_instruction, conversation_text, max_tokens=600)
                else:
                    logger.warning(f"Unknown LLM provider in fallback: {provider}")
                    continue

                if result:
                    clean_res = result.strip()
                    if clean_res.startswith("```"):
                        clean_res = re.sub(r"^```(?:json)?\n", "", clean_res)
                        clean_res = re.sub(r"\n```$", "", clean_res)
                    clean_res = clean_res.strip()
                    try:
                        data = json.loads(clean_res)
                        if "language_code" in data and "script_text" in data:
                            return data
                        else:
                            logger.warning(f"JSON from LightLLM missing keys. Content: {clean_res}")
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse JSON from LightLLM content: {clean_res}")
            except Exception as e:
                logger.error(f"LightLLM provider '{provider}' failed in generate_video_script: {e}")
                continue

        logger.error("All LightLLM providers failed or returned invalid JSON for video script. Using fallback.")
        return fallback_result

    async def _call_gemini(self, system: str, user_text: str, max_tokens: int = 150) -> Optional[str]:
        if not self.settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not set")
            
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise ImportError("google-genai package not installed")

        client = genai.Client(api_key=self.settings.gemini_api_key)
        
        response = await client.aio.models.generate_content(
            model=self.settings.gemini_llm_model,
            contents=[system + "\n\nConversation:\n" + user_text],
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=max_tokens,
            )
        )
        return response.text.strip() if response.text else None

    async def _call_openai_compatible(self, system: str, user_text: str, max_tokens: int = 150) -> Optional[str]:
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
            max_tokens=max_tokens
        )
        return response.choices[0].message.content.strip()
