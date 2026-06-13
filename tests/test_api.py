"""
Basic integration tests for the REST API.
"""
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.fixture(scope="module")
async def client():
    """Async test client with in-memory database."""
    import os
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    os.environ["SCRAPER_ENABLED"] = "false"
    os.environ["SESSION_SECRET"] = "test_secret"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_matches(client):
    response = await client.get("/api/v1/matches/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["count"], int)
    assert isinstance(data["matches"], list)


@pytest.mark.asyncio
async def test_scorers(client):
    response = await client.get("/api/v1/scorers")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["count"], int)


@pytest.mark.asyncio
async def test_standings_empty(client):
    response = await client.get("/api/v1/standings/")
    assert response.status_code == 200
    data = response.json()
    assert "groups" in data


@pytest.mark.asyncio
async def test_match_not_found(client):
    response = await client.get("/api/v1/matches/nonexistent_id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_login_redirect(client):
    """Unauthenticated admin access should redirect to login."""
    response = await client.get("/admin/", follow_redirects=False)
    # Should redirect to login
    assert response.status_code in (307, 302, 401)


@pytest.mark.asyncio
async def test_status(client):
    response = await client.get("/api/v1/status")
    assert response.status_code == 200
    data = response.json()
    assert "scraper_enabled" in data
    assert "matches_tracked" in data
