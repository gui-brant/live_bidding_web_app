import os
import pytest
from fastapi import FastAPI
from httpx import AsyncClient

# ensure app uses dev-mode components
os.environ.setdefault("AUTH_DEV_MODE", "true")
from app.main import app, _DEV_EMAIL_SERVICE


def get_dev_code(email: str) -> str | None:
    return _DEV_EMAIL_SERVICE.get_code(email)


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_otp_flow_success(client: AsyncClient):
    email = "anshuman.aggarwal6@gmail.com"
    # request
    resp = await client.post("/auth/otp/request", json={"email": email})
    assert resp.status_code == 204

    code = get_dev_code(email)
    assert code is not None, "OTP code should be stored in dev email service"

    # verify
    resp = await client.post("/auth/otp/verify", json={"email": email, "code": code})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["profile"]["email"] == email

    # second attempt with same code should fail (OTP cleared)
    resp2 = await client.post("/auth/otp/verify", json={"email": email, "code": code})
    assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_wrong_code(client: AsyncClient):
    email = "user2@example.com"
    await client.post("/auth/otp/request", json={"email": email})
    code = get_dev_code(email)
    assert code

    wrong = "000000" if code != "000000" else "111111"
    resp = await client.post("/auth/otp/verify", json={"email": email, "code": wrong})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_unknown_email_verify(client: AsyncClient):
    # verifying without requesting should return 401
    resp = await client.post("/auth/otp/verify", json={"email": "nobody@example.com", "code": "123456"})
    assert resp.status_code == 401
