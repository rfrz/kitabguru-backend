import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_media_endpoints(client: AsyncClient):
    payload = {
        "email": "media@example.com",
        "username": "mediauser",
        "password": "Password123!"
    }
    await client.post("/api/v1/auth/register", json=payload)
    login_res = await client.post("/api/v1/auth/login", json=payload)
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Generate Image
    # Depends on chat session, so we'll pass an invalid or missing session_id to get 404 or validation error
    res = await client.post("/api/v1/media/generate/image", json={"session_id": "00000000-0000-0000-0000-000000000000"}, headers=headers)
    assert res.status_code in (404, 502) # Might fail because no session found or inference failure
    
    # Generate Video
    res = await client.post("/api/v1/media/generate/video", json={"session_id": "00000000-0000-0000-0000-000000000000"}, headers=headers)
    assert res.status_code in (404, 502)

    # List User Media
    res = await client.get("/api/v1/media/user", headers=headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)
