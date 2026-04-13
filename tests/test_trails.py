"""
Tests for the trails API endpoints.
"""

import pytest
from httpx import AsyncClient

from kishin_trails.database import SESSION_LOCAL
from kishin_trails.dependencies import getCurrentUser
from kishin_trails.main import app
from kishin_trails.models import User, Tile


@pytest.mark.asyncio
async def test_explored_requires_auth(client: AsyncClient):
    response = await client.get("/trails/explored")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_explored_returns_empty_list_for_new_user(authenticated_client: AsyncClient):
    response = await authenticated_client.get("/trails/explored")
    assert response.status_code == 200
    result = response.json()
    assert result == {
        "explored": []
    }


@pytest.mark.asyncio
async def test_explored_returns_user_explored_tiles(db_session):
    test_user = User(id=1, username="trailstest", hashed_password="dummy_hash")
    db_session.add(test_user)

    tile1 = Tile(h3_cell="851f9eabfffffff", tile_type="peak")
    tile2 = Tile(h3_cell="851f2c2ffffffff", tile_type="natural")
    tile3 = Tile(h3_cell="85196b17fffffff", tile_type="industrial")
    tile4 = Tile(h3_cell="851fa443fffffff", tile_type=None)
    db_session.add_all([tile1, tile2, tile3, tile4])
    db_session.commit()

    test_user.explored_tiles.append(tile1)
    test_user.explored_tiles.append(tile2)
    test_user.explored_tiles.append(tile3)
    test_user.explored_tiles.append(tile4)
    db_session.commit()

    def override_get_current_user():
        return test_user

    app.dependency_overrides[getCurrentUser] = override_get_current_user

    from httpx import ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/trails/explored")

    app.dependency_overrides.pop(getCurrentUser, None)

    assert response.status_code == 200
    result = response.json()
    assert set(result["explored"]) == {
        "851f9eabfffffff",
        "851f2c2ffffffff",
        "85196b17fffffff",
        "851fa443fffffff",
    }
