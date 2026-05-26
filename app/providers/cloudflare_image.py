"""
Cloudflare Workers AI client for image generation.
Credentials (CF_ACCOUNT_ID, CF_API_TOKEN, CF_IMAGE_MODEL) are loaded from env — never hardcoded.
"""
import httpx

from app.config import Settings


class CloudflareImageError(RuntimeError):
    pass


class CloudflareImageClient:
    """
    Calls Cloudflare Workers AI text-to-image endpoint.
    API docs: https://developers.cloudflare.com/workers-ai/models/stable-diffusion-xl-base-1.0/
    """

    def __init__(self, settings: Settings):
        if not settings.cf_account_id:
            raise CloudflareImageError("CF_ACCOUNT_ID is not set in environment")
        if not settings.cf_api_token:
            raise CloudflareImageError("CF_API_TOKEN is not set in environment")

        self._url = (
            f"https://api.cloudflare.com/client/v4/accounts/"
            f"{settings.cf_account_id}/ai/run/{settings.cf_image_model}"
        )
        self._headers = {
            "Authorization": f"Bearer {settings.cf_api_token}",
            "Content-Type": "application/json",
        }

    async def generate(self, prompt: str) -> bytes:
        """
        Generate an image from a text prompt.
        Returns raw PNG/JPEG bytes.
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                self._url,
                headers=self._headers,
                json={"prompt": prompt},
            )
            if response.status_code != 200:
                raise CloudflareImageError(
                    f"Cloudflare AI returned {response.status_code}: {response.text}"
                )
            return response.content
