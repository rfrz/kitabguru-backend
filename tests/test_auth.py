import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_register_and_login(client: AsyncClient):
    # 1. Register
    payload = {
        "email": "test@example.com",
        "username": "testuser",
        "password": "Password123!"
    }
    res = await client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["email"] == "test@example.com"

    # 2. Login
    login_payload = {
        "email": "test@example.com",
        "password": "Password123!"
    }
    res = await client.post("/api/v1/auth/login", json=login_payload)
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert "refresh_token" in data

    # 3. Refresh token
    refresh_payload = {
        "refresh_token": data["refresh_token"]
    }
    res = await client.post("/api/v1/auth/refresh", json=refresh_payload)
    assert res.status_code == 200
    new_data = res.json()
    assert "access_token" in new_data
    assert "refresh_token" in new_data
    assert new_data["refresh_token"] != data["refresh_token"]

    # 4. Logout
    logout_payload = {
        "refresh_token": new_data["refresh_token"]
    }
    # For logout we need auth token
    res = await client.post(
        "/api/v1/auth/logout",
        json=logout_payload,
        headers={"Authorization": f"Bearer {new_data['access_token']}"}
    )
    assert res.status_code == 204
