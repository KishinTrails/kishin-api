"""
Tests for the trails API endpoints.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from kishin_trails.models import ExploredTile, Tile
from kishin_trails.schemas import AddExploredTilesRequest
from kishin_trails.trails import addExploredTiles


def _explored(db_session) -> set[str]:
    return set(db_session.scalars(select(ExploredTile.s2_cell_id)))


@pytest.mark.asyncio
async def test_explored_requires_auth(client: AsyncClient):
    response = await client.get("/api/trails/explored")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_explored_returns_empty_list_when_nothing_is_explored(authenticated_client: AsyncClient):
    response = await authenticated_client.get("/api/trails/explored")
    assert response.status_code == 200
    assert response.json() == {"explored": []}


@pytest.mark.asyncio
async def test_explored_returns_the_explored_tiles(authenticated_client: AsyncClient, db_session):
    tiles = [
        Tile(s2_cell_id="478f74", tile_type="peak"),
        Tile(s2_cell_id="465704", tile_type="natural"),
        Tile(s2_cell_id="47c5ac", tile_type="industrial"),
        Tile(s2_cell_id="47c3c4", tile_type=None),
        Tile(s2_cell_id="47c3cc", tile_type=None),
    ]
    db_session.add_all(tiles)
    for tile in tiles[:4]:
        tile.explored = ExploredTile()
    db_session.commit()

    response = await authenticated_client.get("/api/trails/explored")
    assert response.status_code == 200
    assert set(response.json()["explored"]) == {"478f74", "465704", "47c5ac", "47c3c4"}


@pytest.mark.asyncio
async def test_post_explored_marks_tiles(authenticated_client: AsyncClient, db_session):
    db_session.add(Tile(s2_cell_id="89c25a221", tile_type="peak"))
    db_session.commit()
    response = await authenticated_client.post("/api/trails/explored", json={"cells": ["89c25a221", "89c25a221"]})
    assert response.status_code == 200
    assert response.json()["added"] == ["89c25a221"]
    assert _explored(db_session) == {"89c25a221"}


class TestAddExploredTiles:
    """Test POST /trails/explored endpoint."""

    def test_addExploredTiles_adds_valid_tiles(self, db_session):
        """Test adding valid tiles marks them as explored in DB."""

        tile = Tile(s2_cell_id="89c25a221", tile_type="peak")
        db_session.add_all([tile])
        db_session.commit()

        request = AddExploredTilesRequest(cells=["89c25a221"])
        result = addExploredTiles(request, db_session)

        assert result["added"] == ["89c25a221"]
        assert result["skipped"] == []

        assert _explored(db_session) == {"89c25a221"}

    def test_addExploredTiles_skips_invalid_cells(self, db_session):
        """Test invalid S2 cells are skipped and valid ones are added."""

        tile = Tile(s2_cell_id="89c25a221", tile_type="peak")
        db_session.add_all([tile])
        db_session.commit()

        request = AddExploredTilesRequest(cells=["invalid_cell", "89c25a221"])
        result = addExploredTiles(request, db_session)

        assert result["added"] == ["89c25a221"]
        assert len(result["skipped"]) == 1
        assert result["skipped"][0].cell == "invalid_cell"
        assert result["skipped"][0].reason == "invalid"

        assert _explored(db_session) == {"89c25a221"}

    def test_addExploredTiles_skips_not_found_cells(self, db_session):
        """Test cells not in database are skipped."""


        request = AddExploredTilesRequest(cells=["89c25a221", "89c25a223"])
        result = addExploredTiles(request, db_session)

        assert result["added"] == []
        assert len(result["skipped"]) == 2
        assert all(s.reason == "not_found" for s in result["skipped"])

        assert _explored(db_session) == set()

    def test_addExploredTiles_logs_counts_and_skipped_cells(self, db_session, caplog):
        """The log line gives each count and names every skipped cell with its reason."""
        db_session.add_all([Tile(s2_cell_id="89c25a221", tile_type="peak"),
                            Tile(s2_cell_id="89c25a225", tile_type="peak")])
        db_session.commit()
        addExploredTiles(AddExploredTilesRequest(cells=["89c25a225"]), db_session)

        caplog.set_level("INFO", logger="trails")
        addExploredTiles(AddExploredTilesRequest(cells=["89c25a221", "89c25a225", "89c25a223"]), db_session)

        assert caplog.messages[-1] == (
            "POST /api/trails/explored: 3 received, 1 added, 1 already explored, 1 skipped 89c25a223:not_found"
        )

    def test_addExploredTiles_ignores_duplicates(self, db_session):
        """Test already explored tiles are silently ignored."""

        tile = Tile(s2_cell_id="89c25a221", tile_type="peak")
        db_session.add_all([tile])
        db_session.commit()
        tile.explored = ExploredTile()
        db_session.commit()

        request = AddExploredTilesRequest(cells=["89c25a221"])
        result = addExploredTiles(request, db_session)

        assert result["added"] == []
        assert result["skipped"] == []

        assert _explored(db_session) == {"89c25a221"}

    def test_addExploredTiles_limits_to_100(self, db_session):
        """Test that requests are limited to 100 cells."""


        request = AddExploredTilesRequest(cells=["cell"] * 150)
        result = addExploredTiles(request, db_session)

        assert result["added"] == []
        assert len(result["skipped"]) == 100

    def test_addExploredTiles_batch_add_multiple(self, db_session):
        """Test adding multiple valid tiles at once."""

        tile1 = Tile(s2_cell_id="89c25a221", tile_type="peak")
        tile2 = Tile(s2_cell_id="89c25a223", tile_type="natural")
        tile3 = Tile(s2_cell_id="89c25a225", tile_type="industrial")
        db_session.add_all([tile1, tile2, tile3])
        db_session.commit()

        request = AddExploredTilesRequest(cells=["89c25a221", "89c25a223", "89c25a225"])
        result = addExploredTiles(request, db_session)

        assert set(result["added"]) == {"89c25a221", "89c25a223", "89c25a225"}
        assert result["skipped"] == []

        assert _explored(db_session) == {"89c25a221", "89c25a223", "89c25a225"}
