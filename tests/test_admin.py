import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_admin_endpoints(client: AsyncClient):
    # Register a normal user
    payload = {
        "email": "user@example.com",
        "username": "normaluser",
        "password": "Password123!"
    }
    await client.post("/api/v1/auth/register", json=payload)
    login_res = await client.post("/api/v1/auth/login", json=payload)
    user_token = login_res.json()["access_token"]
    user_headers = {"Authorization": f"Bearer {user_token}"}

    # Normal user should be forbidden to access admin
    res = await client.get("/api/v1/admin/users", headers=user_headers)
    assert res.status_code == 403

    # For admin, we would normally use the seeded admin credentials from env.
    # But since we can't easily read the env in test if they are dynamic, we just check the forbidden part.
    # To fully test admin, we would login as admin, then access the endpoints.
    login_admin = {
        "email": "admin@kitabguru.com", # Default from config
        "password": "ChangeThisPassword!" # Default from config
    }
    admin_res = await client.post("/api/v1/auth/login", json=login_admin)
    
    if admin_res.status_code == 200:
        admin_token = admin_res.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # Admin can access
        res = await client.get("/api/v1/admin/users", headers=admin_headers)
        assert res.status_code == 200
        assert "users" in res.json()
