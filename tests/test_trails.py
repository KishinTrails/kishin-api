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

    tile1 = Tile(s2_cell_id="478f74", tile_type="peak")
    tile2 = Tile(s2_cell_id="465704", tile_type="natural")
    tile3 = Tile(s2_cell_id="47c5ac", tile_type="industrial")
    tile4 = Tile(s2_cell_id="47c3c4", tile_type=None)
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
        "478f74",
        "465704",
        "47c5ac",
        "47c3c4",
    }


class TestAddExploredTiles:
    """Test POST /trails/explored endpoint."""

    def test_addExploredTiles_adds_valid_tiles(self, db_session):
        """Test adding valid tiles marks them as explored in DB."""
        from kishin_trails.schemas import AddExploredTilesRequest
        from kishin_trails.trails import addExploredTiles

        test_user = User(id=1, username="testuser", hashed_password="dummy_hash")
        tile = Tile(s2_cell_id="89c25a221", tile_type="peak")
        db_session.add_all([test_user, tile])
        db_session.commit()

        request = AddExploredTilesRequest(cells=["89c25a221"])
        result = addExploredTiles(request, test_user, db_session)

        assert result["added"] == ["89c25a221"]
        assert result["skipped"] == []

        db_session.refresh(test_user)
        assert tile in test_user.explored_tiles
        assert len(test_user.explored_tiles) == 1

    def test_addExploredTiles_skips_invalid_cells(self, db_session):
        """Test invalid S2 cells are skipped and valid ones are added."""
        from kishin_trails.schemas import AddExploredTilesRequest
        from kishin_trails.trails import addExploredTiles

        test_user = User(id=1, username="testuser", hashed_password="dummy_hash")
        tile = Tile(s2_cell_id="89c25a221", tile_type="peak")
        db_session.add_all([test_user, tile])
        db_session.commit()

        request = AddExploredTilesRequest(cells=["invalid_cell", "89c25a221"])
        result = addExploredTiles(request, test_user, db_session)

        assert result["added"] == ["89c25a221"]
        assert len(result["skipped"]) == 1
        assert result["skipped"][0].cell == "invalid_cell"
        assert result["skipped"][0].reason == "invalid"

        db_session.refresh(test_user)
        assert tile in test_user.explored_tiles

    def test_addExploredTiles_skips_not_found_cells(self, db_session):
        """Test cells not in database are skipped."""
        from kishin_trails.schemas import AddExploredTilesRequest
        from kishin_trails.trails import addExploredTiles

        test_user = User(id=1, username="testuser", hashed_password="dummy_hash")
        db_session.add(test_user)
        db_session.commit()

        request = AddExploredTilesRequest(cells=["89c25a221", "89c25a223"])
        result = addExploredTiles(request, test_user, db_session)

        assert result["added"] == []
        assert len(result["skipped"]) == 2
        assert all(s.reason == "not_found" for s in result["skipped"])

        db_session.refresh(test_user)
        assert len(test_user.explored_tiles) == 0

    def test_addExploredTiles_ignores_duplicates(self, db_session):
        """Test already explored tiles are silently ignored."""
        from kishin_trails.schemas import AddExploredTilesRequest
        from kishin_trails.trails import addExploredTiles

        test_user = User(id=1, username="testuser", hashed_password="dummy_hash")
        tile = Tile(s2_cell_id="89c25a221", tile_type="peak")
        db_session.add_all([test_user, tile])
        db_session.commit()
        test_user.explored_tiles.append(tile)
        db_session.commit()
        initial_count = len(test_user.explored_tiles)

        request = AddExploredTilesRequest(cells=["89c25a221"])
        result = addExploredTiles(request, test_user, db_session)

        assert result["added"] == []
        assert result["skipped"] == []

        db_session.refresh(test_user)
        assert len(test_user.explored_tiles) == initial_count

    def test_addExploredTiles_limits_to_100(self, db_session):
        """Test that requests are limited to 100 cells."""
        from kishin_trails.schemas import AddExploredTilesRequest
        from kishin_trails.trails import addExploredTiles

        test_user = User(id=1, username="testuser", hashed_password="dummy_hash")
        db_session.add(test_user)
        db_session.commit()

        request = AddExploredTilesRequest(cells=["cell"] * 150)
        result = addExploredTiles(request, test_user, db_session)

        assert result["added"] == []
        assert len(result["skipped"]) == 100

    def test_addExploredTiles_batch_add_multiple(self, db_session):
        """Test adding multiple valid tiles at once."""
        from kishin_trails.schemas import AddExploredTilesRequest
        from kishin_trails.trails import addExploredTiles

        test_user = User(id=1, username="testuser", hashed_password="dummy_hash")
        tile1 = Tile(s2_cell_id="89c25a221", tile_type="peak")
        tile2 = Tile(s2_cell_id="89c25a223", tile_type="natural")
        tile3 = Tile(s2_cell_id="89c25a225", tile_type="industrial")
        db_session.add_all([test_user, tile1, tile2, tile3])
        db_session.commit()

        request = AddExploredTilesRequest(cells=["89c25a221", "89c25a223", "89c25a225"])
        result = addExploredTiles(request, test_user, db_session)

        assert set(result["added"]) == {"89c25a221", "89c25a223", "89c25a225"}
        assert result["skipped"] == []

        db_session.refresh(test_user)
        assert len(test_user.explored_tiles) == 3
        assert tile1 in test_user.explored_tiles
        assert tile2 in test_user.explored_tiles
        assert tile3 in test_user.explored_tiles
