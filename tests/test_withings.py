"""
Tests for the static Withings OAuth callback page.
"""

import pytest
from httpx import AsyncClient

# Fixture 'client' is automatically loaded from conftest.py


@pytest.mark.asyncio
async def test_withings_page_get(client: AsyncClient):
    response = await client.get("/withings/withings.html", params={"code": "abc123"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert '<script src="withings.js"></script>' in response.text


@pytest.mark.asyncio
async def test_withings_page_head(client: AsyncClient):
    # Withings refuses a redirect address that does not answer HEAD with a 2xx status.
    response = await client.head("/withings/withings.html")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_withings_script_get(client: AsyncClient):
    response = await client.get("/withings/withings.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_withings_unknown_file(client: AsyncClient):
    response = await client.get("/withings/other.html")
    assert response.status_code == 404
