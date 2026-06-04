"""
Shared pytest fixtures for users API endpoint tests.

The server must be running separately (e.g. ``uvicorn app.main:app``).
Tests send real HTTP requests to it.
"""

import os

import jwt
import pytest
import httpx
from bson import ObjectId
from datetime import timedelta
from pymongo import AsyncMongoClient
from app.helper.timezone import now_in_app_timezone

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Config
BASE_URL = os.getenv("TEST_BASE_URL", "http://127.0.0.1:8000")
JWT_SECRET = os.getenv("AUTH_JWT_SECRET", "change-me")
JWT_ALGORITHM = os.getenv("AUTH_JWT_ALGORITHM", "HS256")


def make_token(user_id: str, role: str = "rep") -> str:
    """Mint a valid JWT identical to what the server would issue."""
    now = now_in_app_timezone()
    payload = {
        "sub": user_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def auth_header(user_id: str, role: str = "rep") -> dict:
    """Return an Authorization header dict for the given user_id."""
    return {"Authorization": f"Bearer {make_token(user_id, role)}"}


# Fixtures
@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture
def client(base_url):
    """Synchronous httpx client pointed at the running server."""
    with httpx.Client(base_url=base_url, timeout=10) as c:
        yield c


@pytest.fixture
def create_user(client):
    """
    Factory fixture: call it with a payload dict to POST /users.
    Returns the response.
    """
    created_ids: list[str] = []

    def _create(payload: dict, headers: dict | None = None):
        resp = client.post("/users", json=payload, headers=headers or {})
        if resp.status_code == 201:
            created_ids.append(resp.json()["_id"])
        return resp

    yield _create

    # Cleanup: delete every user created during this test
    for uid in created_ids:
        client.delete("/users/me", headers=auth_header(uid))
