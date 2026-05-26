"""
Async HTTP client for kitabguru-inference RAG service.
"""
from typing import Any, Optional

import httpx

from app.config import Settings


class InferenceClient:
    def __init__(self, settings: Settings):
        self.base_url = settings.inference_base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=120.0,  # LLM inference can take a while
        )

    async def chat(self, query: str, book_filter: Optional[str] = None) -> dict[str, Any]:
        """
        POST /api/chat to inference engine.
        Returns the full ChatResponse dict.
        """
        payload: dict[str, Any] = {"query": query}
        if book_filter:
            payload["book_filter"] = book_filter

        response = await self._client.post("/api/chat", json=payload)
        response.raise_for_status()
        return response.json()

    async def health(self) -> bool:
        """Quick health check against inference service."""
        try:
            resp = await self._client.get("/health", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.aclose()
