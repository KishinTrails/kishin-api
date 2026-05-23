"""
Idempotency tests for cache population and database operations.

These tests verify that:
1. Running populate scripts multiple times produces identical results
2. Missing data is restored without duplicates when re-running
3. Existing data is preserved (tile_type, POIs)
4. PostProcessingPoI and junction table operations are idempotent
5. --no-cache flag works correctly
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from kishin_trails.cache import getTile, setTile
from kishin_trails.models import POI, PostProcessingPoI, Tile


@pytest.fixture
def mock_overpass_response():
    """Fixture providing a mock Overpass API JSON response."""
    return {
        "version":
            0.6,
        "generator":
            "Overpass API",
        "elements":
            [
                {
                    "type": "node",
                    "id": 123456,
                    "lat": 45.8325,
                    "lon": 6.8652,
                    "tags": {
                        "natural": "peak",
                        "name": "Mont Blanc",
                        "ele": "4809"
                    }
                },
                {
                    "type": "node",
                    "id": 123457,
                    "lat": 45.8320,
                    "lon": 6.8650,
                    "tags": {
                        "natural": "peak",
                        "name": "Dôme du Goûter",
                        "ele": "4304"
                    }
                },
                {
                    "type": "way",
                    "id": 987654,
                    "nodes": [111,
                              222,
                              333,
                              111],
                    "tags": {
                        "landuse": "forest",
                        "name": "Forêt de Chamonix"
                    }
                }
            ]
    }


@pytest.fixture
def s2_test_cell():
    """Fixture providing a test S2 cell (level 16)."""
    return "4789459fb"


@pytest.fixture
def s2_parent_cell(s2_test_cell):
    """Fixture providing parent S2 cell (level 13) for batch tests."""
    from kishin_trails.utils import s2CellToParent
    return s2CellToParent(s2_test_cell, 13)


@pytest.fixture
def s2_chilren_cells(s2_parent_cell):
    """Fixture providing 10 children cells (level 16) from parent."""
    from kishin_trails.utils import s2CellToChildren
    return s2CellToChildren(s2_parent_cell, 16)[:10]


@pytest.fixture
def track_set_tile(mocker):
    """Fixture providing a mock setTile function that tracks calls."""
    set_tile_calls = []

    def track_set_tile(s2Cell, tileType, pois):
        set_tile_calls.append(s2Cell)

    mocker.patch("scripts.populate_cache.setTile", side_effect=track_set_tile)
    return set_tile_calls


class TestTileIdempotency:
    """Tests for Tile and POI idempotency."""
    def test_populate_twice_no_duplicates(self, db_session, mock_overpass_response, s2_test_cell, mocker):
        """Running populate twice produces identical DB state, no duplicates."""
        from scripts.populate_cache import populateCacheForTiles

        # Mock runOverpass to return our fixed response
        mocker.patch("kishin_trails.overpass.runOverpass", return_value=mock_overpass_response)

        # First run
        populateCacheForTiles([s2_test_cell])
        poi_count_1 = db_session.query(POI).filter(POI.s2_cell_id == s2_test_cell).count()

        # Second run (should not add duplicates)
        populateCacheForTiles([s2_test_cell])
        poi_count_2 = db_session.query(POI).filter(POI.s2_cell_id == s2_test_cell).count()

        assert poi_count_1 == poi_count_2
        assert poi_count_1 > 0

    def test_restore_deleted_poi(self, db_session, mock_overpass_response, s2_test_cell, mocker):
        """Deleting a POI and re-running restores it without affecting others."""
        from scripts.populate_cache import populateCacheForTiles

        mocker.patch("kishin_trails.overpass.runOverpass", return_value=mock_overpass_response)

        # Initial population
        populateCacheForTiles([s2_test_cell])
        all_pois = db_session.query(POI).filter(POI.s2_cell_id == s2_test_cell).all()
        initial_osm_ids = {poi.osm_id
                           for poi in all_pois}
        initial_count = len(all_pois)

        # Delete one POI
        if all_pois:
            deleted_poi = all_pois[0]
            db_session.delete(deleted_poi)
            db_session.commit()

        # Re-populate
        populateCacheForTiles([s2_test_cell], skipCached=False)

        # Verify restoration
        final_pois = db_session.query(POI).filter(POI.s2_cell_id == s2_test_cell).all()
        final_osm_ids = {poi.osm_id
                         for poi in final_pois}

        assert final_osm_ids == initial_osm_ids
        assert len(final_pois) == initial_count

    def test_complete_partial_tile(self, db_session, mock_overpass_response, s2_test_cell, mocker):
        """Tile row exists - normal mode skips it without re-processing."""
        from scripts.populate_cache import populateCacheForTiles

        # Simulate interrupted run: Tile created, no POIs
        tile = Tile(s2_cell_id=s2_test_cell, tile_type=None)
        db_session.add(tile)
        db_session.commit()

        mocker.patch("kishin_trails.overpass.runOverpass", return_value=mock_overpass_response)

        # Re-run with skipCached=True (default) - should skip existing tile
        populateCacheForTiles([s2_test_cell])

        # Verify tile was NOT modified (still has no POIs)
        tile_data = getTile(s2_test_cell)
        assert tile_data is not None
        assert len(tile_data["pois"]) == 0

    def test_tile_type_never_updated(self, db_session, s2_test_cell, mocker):
        """Existing tile_type is preserved even if Overpass returns different type."""
        from scripts.populate_cache import populateCacheForTiles

        # Pre-populate with specific tile_type
        setTile(s2_test_cell,
                "natural",
                [{
                    "osm_id": 123456,
                    "lat": 45.8325,
                    "lon": 6.8652,
                    "name": "Peak"
                }])

        # Mock Overpass to return different tile_type
        mock_response = {
            "version": 0.6,
            "generator": "Overpass API",
            "elements": [{
                "type": "way",
                "id": 999,
                "nodes": [111,
                          222,
                          333,
                          111],
                "tags": {
                    "landuse": "industrial"
                }
            }]
        }
        mocker.patch("kishin_trails.overpass.runOverpass", return_value=mock_response)

        # Re-populate
        populateCacheForTiles([s2_test_cell])

        # Verify tile_type unchanged
        tile = db_session.query(Tile).filter(Tile.s2_cell_id == s2_test_cell).first()
        assert tile.tile_type == "natural"

    def test_tile_type_preserved_when_null(self, db_session, mock_overpass_response, s2_test_cell, mocker):
        """Tile with NULL tile_type keeps NULL after re-population."""
        from scripts.populate_cache import populateCacheForTiles

        # Create tile with NULL tile_type
        tile = Tile(s2_cell_id=s2_test_cell, tile_type=None)
        db_session.add(tile)
        db_session.commit()

        mocker.patch("kishin_trails.overpass.runOverpass", return_value=mock_overpass_response)

        # Re-populate
        populateCacheForTiles([s2_test_cell])

        # Verify tile_type is still NULL
        tile = db_session.query(Tile).filter(Tile.s2_cell_id == s2_test_cell).first()
        assert tile.tile_type is None

    def test_restore_empty_tile_with_skip_cached_false(self, db_session, mock_overpass_response, s2_test_cell, mocker):
        """Tile exists with no POIs - skipCached=False restores POIs."""
        from scripts.populate_cache import populateCacheForTiles

        # Create tile with no POIs
        tile = Tile(s2_cell_id=s2_test_cell, tile_type=None)
        db_session.add(tile)
        db_session.commit()

        mocker.patch("kishin_trails.overpass.runOverpass", return_value=mock_overpass_response)

        # Re-populate with skipCached=False to force processing
        populateCacheForTiles([s2_test_cell], skipCached=False)

        # Verify POIs were added
        tile_data = getTile(s2_test_cell)
        assert tile_data is not None
        assert len(tile_data["pois"]) > 0

        # Verify POI records in database
        poi_count = db_session.query(POI).filter(POI.s2_cell_id == s2_test_cell).count()
        assert poi_count > 0

    def test_restore_partial_pois_with_skip_cached_false(
        self,
        db_session,
        mock_overpass_response,
        s2_test_cell,
        mocker
    ):
        """Tile exists with partial POIs - skipCached=False restores missing POIs."""
        from scripts.populate_cache import populateCacheForTiles

        mocker.patch("kishin_trails.overpass.runOverpass", return_value=mock_overpass_response)

        # Initial population
        populateCacheForTiles([s2_test_cell], skipCached=False)
        all_pois = db_session.query(POI).filter(POI.s2_cell_id == s2_test_cell).all()
        initial_osm_ids = {poi.osm_id
                           for poi in all_pois}
        initial_count = len(all_pois)
        assert initial_count > 0

        # Delete some POIs (but not all)
        if len(all_pois) > 1:
            for poi in all_pois[:-1]:  # Keep last POI
                db_session.delete(poi)
            db_session.commit()
            remaining_count = db_session.query(POI).filter(POI.s2_cell_id == s2_test_cell).count()
            assert remaining_count == 1

        # Re-populate with skipCached=False to restore deleted POIs
        populateCacheForTiles([s2_test_cell], skipCached=False)

        # Verify all POIs restored
        final_pois = db_session.query(POI).filter(POI.s2_cell_id == s2_test_cell).all()
        final_osm_ids = {poi.osm_id
                         for poi in final_pois}
        assert final_osm_ids == initial_osm_ids
        assert len(final_pois) == initial_count

    def test_populate_tile_type_with_skip_cached_false(self, db_session, mock_overpass_response, s2_test_cell, mocker):
        """Tile with NULL tile_type - skipCached=False populates tile_type from POIs."""
        from scripts.populate_cache import populateCacheForTiles

        # Create tile with NULL tile_type
        tile = Tile(s2_cell_id=s2_test_cell, tile_type=None)
        db_session.add(tile)
        db_session.commit()

        mocker.patch("kishin_trails.overpass.runOverpass", return_value=mock_overpass_response)

        # Re-populate with skipCached=False
        populateCacheForTiles([s2_test_cell], skipCached=False)

        # Verify tile_type was set based on POI type
        tile_data = getTile(s2_test_cell)
        assert tile_data is not None
        assert tile_data["tile_type"] is not None
        assert tile_data["tile_type"] in ["peak", "natural", "industrial"]

        # Verify POIs were also added
        assert len(tile_data["pois"]) > 0


class TestPostProcessingPoIIdempotency:
    """Tests for PostProcessingPoI and junction table idempotency."""
    def test_insert_or_get_poi_no_duplicates(self, db_session):
        """insertOrGetPostProcessingPoi never creates duplicates."""
        from scripts.populate_cache import insertOrGetPostProcessingPoi

        # First call
        id1 = insertOrGetPostProcessingPoi(12345, "Forest", "natural")

        # Second call with same osm_id
        id2 = insertOrGetPostProcessingPoi(12345, "Forest", "natural")

        assert id1 == id2

        # Verify only one record exists
        count = db_session.query(PostProcessingPoI).filter(PostProcessingPoI.osm_id == 12345).count()
        assert count == 1

    def test_insert_junction_entry_no_duplicates(self, db_session, s2_test_cell):
        """insertJunctionEntry with INSERT OR IGNORE never creates duplicates."""
        from scripts.populate_cache import insertJunctionEntry, insertOrGetPostProcessingPoi

        poi_id = insertOrGetPostProcessingPoi(12345, "Forest", "natural")

        # Insert twice
        insertJunctionEntry(s2_test_cell, poi_id)
        insertJunctionEntry(s2_test_cell, poi_id)

        # Verify single entry
        result = db_session.execute(
            text(
                "SELECT COUNT(*) FROM tile_post_processing_pois WHERE tile_s2_cell_id = :tile AND post_processing_poi_id = :poi"
            ),
            {
                "tile": s2_test_cell,
                "poi": poi_id
            }
        )
        assert result.scalar() == 1

    def test_fill_polygons_safe_to_rerun(self, db_session, s2_test_cell):
        """--fill-polygons can be run multiple times safely."""
        from scripts.populate_cache import (fillPolygonInteriors, insertJunctionEntry, insertOrGetPostProcessingPoi)

        # Setup: PostProcessingPoI with linked tiles
        poi_id = insertOrGetPostProcessingPoi(12345, "Forest", "natural")
        insertJunctionEntry(s2_test_cell, poi_id)

        tile = Tile(s2_cell_id=s2_test_cell, tile_type=None)
        db_session.add(tile)
        db_session.commit()

        # First fill
        fillPolygonInteriors()
        tile_type_1 = db_session.query(Tile).filter(Tile.s2_cell_id == s2_test_cell).first().tile_type

        # Second fill (should be safe no-op)
        fillPolygonInteriors()
        tile_type_2 = db_session.query(Tile).filter(Tile.s2_cell_id == s2_test_cell).first().tile_type

        assert tile_type_1 == "natural"
        assert tile_type_2 == "natural"

        # PostProcessingPoI should be deleted after first fill
        poi_count = db_session.query(PostProcessingPoI).filter(PostProcessingPoI.id == poi_id).count()
        assert poi_count == 0

    def test_post_processing_poi_to_tile_restoration(self, db_session, s2_test_cell, mocker):
        """PostProcessingPoI linked to tiles - validates tile_type propagation with skipCached=False."""
        from scripts.populate_cache import (
            fillPolygonInteriors,
            insertJunctionEntry,
            insertOrGetPostProcessingPoi,
            populateCacheForTiles,
        )

        # Create PostProcessingPoI
        poi_id = insertOrGetPostProcessingPoi(54321, "Test Forest", "natural")

        # Link to tile via junction table
        insertJunctionEntry(s2_test_cell, poi_id)

        # Create tile with NULL tile_type (simulating incomplete state)
        tile = Tile(s2_cell_id=s2_test_cell, tile_type=None)
        db_session.add(tile)
        db_session.commit()

        # Verify initial state
        tile_initial = db_session.query(Tile).filter(Tile.s2_cell_id == s2_test_cell).first()
        assert tile_initial.tile_type is None

        # Run fillPolygonInteriors to propagate tile_type
        fillPolygonInteriors()

        # Expire all cached objects to force re-query from database
        db_session.expire_all()

        # Verify tile_type was set from PostProcessingPoI
        tile_final = db_session.query(Tile).filter(Tile.s2_cell_id == s2_test_cell).first()
        assert tile_final.tile_type == "natural"

        # Verify PostProcessingPoI was cleaned up
        poi_count = db_session.query(PostProcessingPoI).filter(PostProcessingPoI.id == poi_id).count()
        assert poi_count == 0

        # Verify junction entry was cleaned up
        junction_result = db_session.execute(
            text(
                "SELECT COUNT(*) FROM tile_post_processing_pois WHERE tile_s2_cell_id = :tile AND post_processing_poi_id = :poi"
            ),
            {
                "tile": s2_test_cell,
                "poi": poi_id
            }
        )
        assert junction_result.scalar() == 0


class TestNoCacheFlag:
    """Tests for --no-cache flag behavior."""
    def test_no_cache_flag_processes_all_tiles(self, db_session, s2_test_cell, mocker):
        """--no-cache flag forces re-processing of all tiles."""
        from scripts.populate_cache import populateCacheForTiles

        # Pre-populate tile
        setTile(s2_test_cell,
                "natural",
                [{
                    "osm_id": 123456,
                    "lat": 45.8325,
                    "lon": 6.8652,
                    "name": "Peak"
                }])

        # Mock to track Overpass calls
        mock_run_overpass = mocker.patch("kishin_trails.overpass.runOverpass")
        mock_run_overpass.return_value = {
            "version": 0.6,
            "elements": []
        }

        # Run with skipCached=False (simulates --no-cache)
        populateCacheForTiles([s2_test_cell], skipCached=False)

        # Verify Overpass was called despite tile existing
        assert mock_run_overpass.called

    def test_normal_mode_skips_cached_tiles(self, db_session, s2_test_cell, mocker, track_set_tile):
        """Normal mode (skipCached=True) skips cached tiles."""
        from scripts.populate_cache import populateCacheForTiles

        # Pre-populate tile
        setTile(s2_test_cell,
                "natural",
                [{
                    "osm_id": 123456,
                    "lat": 45.8325,
                    "lon": 6.8652,
                    "name": "Peak"
                }])

        # Mock to track Overpass calls
        mock_run_overpass = mocker.patch("kishin_trails.overpass.runOverpass")

        # Run with skipCached=True (default mode)
        populateCacheForTiles([s2_test_cell], skipCached=True)

        # Overpass will always be called.
        assert mock_run_overpass.called

        # Yet, cells are left unchanged - setTile should not be called for cached tiles
        assert len(track_set_tile) == 0

    def test_batch_processing_skips_cached(self, db_session, mocker, s2_parent_cell, s2_chilren_cells, track_set_tile):
        """Normal mode skips cached tiles in batch processing."""
        from scripts.populate_cache import populateCacheForTiles

        children = s2_chilren_cells

        # Pre-cache first 5 tiles from the 10 children
        for child in children[:5]:
            setTile(child,
                    "natural",
                    [{
                        "osm_id": 999,
                        "lat": 45.0,
                        "lon": 6.0
                    }])

        # Mock to track calls
        mock_run_overpass = mocker.patch("kishin_trails.overpass.runOverpass")
        mock_run_overpass.return_value = {
            "version": 0.6,
            "elements": []
        }

        # Run populate - processes all 64 children of parent
        populateCacheForTiles([s2_parent_cell], skipCached=True)

        # Verify 59 tiles were processed (64 total - 5 pre-cached)
        assert len(track_set_tile) == 59
        # All 10 children should be in the result, but only 5 of them were actually set
        assert set(children[5:]).issubset(set(track_set_tile))

        # Yet a single overpass call.
        assert mock_run_overpass.call_count == 1

    def test_no_cache_processes_all_in_batch(
        self,
        db_session,
        mocker,
        s2_parent_cell,
        s2_chilren_cells,
        track_set_tile
    ):
        """--no-cache mode processes all tiles in batch, even cached ones."""
        from scripts.populate_cache import populateCacheForTiles

        children = s2_chilren_cells

        # Pre-cache all 10 children tiles
        for child in children:
            setTile(child,
                    "natural",
                    [{
                        "osm_id": 999,
                        "lat": 45.0,
                        "lon": 6.0
                    }])

        # Mock to track calls
        mock_run_overpass = mocker.patch("kishin_trails.overpass.runOverpass")
        mock_run_overpass.return_value = {
            "version": 0.6,
            "elements": []
        }

        # Run with skipCached=False (simulates --no-cache) - processes all 64 children
        populateCacheForTiles([s2_parent_cell], skipCached=False)

        # Verify all 64 children of parent were processed (including the 10 pre-cached ones)
        assert len(track_set_tile) == 64
        # The 10 pre-cached children should be in the result
        assert set(children).issubset(set(track_set_tile))

        # Yet only a single overpass call.
        assert mock_run_overpass.call_count == 1


class TestSetTileIdempotency:
    """Direct tests for setTile function idempotency."""
    def test_setTile_twice_same_data(self, db_session, s2_test_cell):
        """Calling setTile twice with same data produces identical result."""
        pois = [
            {
                "osm_id": 123456,
                "lat": 45.8325,
                "lon": 6.8652,
                "name": "Peak 1"
            },
            {
                "osm_id": 123457,
                "lat": 45.8320,
                "lon": 6.8650,
                "name": "Peak 2"
            }
        ]

        # First call
        setTile(s2_test_cell, "natural", pois)
        tile1 = getTile(s2_test_cell)

        # Second call with same data
        setTile(s2_test_cell, "natural", pois)
        tile2 = getTile(s2_test_cell)

        assert tile1 is not None
        assert tile2 is not None
        assert tile1 == tile2
        assert len(tile1["pois"]) == 2

    def test_setTile_preserves_existing_pois(self, db_session, s2_test_cell):
        """setTile preserves existing POIs, only adds missing ones."""
        # Initial set
        setTile(s2_test_cell,
                "natural",
                [{
                    "osm_id": 123456,
                    "lat": 45.8325,
                    "lon": 6.8652,
                    "name": "Peak 1"
                }])

        # Second set with additional POI
        setTile(
            s2_test_cell,
            "natural",
            [
                {
                    "osm_id": 123456,
                    "lat": 45.8325,
                    "lon": 6.8652,
                    "name": "Peak 1"
                },
                {
                    "osm_id": 123457,
                    "lat": 45.8320,
                    "lon": 6.8650,
                    "name": "Peak 2"
                }
            ]
        )

        # Verify both POIs exist
        tile = getTile(s2_test_cell)
        assert tile is not None
        osm_ids = {poi["osm_id"]
                   for poi in tile["pois"]}

        assert 123456 in osm_ids
        assert 123457 in osm_ids
        assert len(tile["pois"]) == 2

    def test_setTile_does_not_update_poi_data(self, db_session, s2_test_cell):
        """setTile does not update existing POI data, only inserts missing."""
        # Initial set
        setTile(s2_test_cell,
                "natural",
                [{
                    "osm_id": 123456,
                    "lat": 45.8325,
                    "lon": 6.8652,
                    "name": "Original Name"
                }])

        # Second set with different name for same osm_id
        setTile(s2_test_cell,
                "natural",
                [{
                    "osm_id": 123456,
                    "lat": 45.9999,
                    "lon": 6.9999,
                    "name": "New Name"
                }])

        # Verify original data preserved
        tile = getTile(s2_test_cell)
        assert tile is not None
        poi = tile["pois"][0]

        assert poi["name"] == "Original Name"
        assert poi["lat"] == 45.8325
        assert poi["lon"] == 6.8652


class TestBatchProcessing:
    """Tests for batch tile processing with deduplication."""
    def test_batch_processing_deduplication(self, db_session, mocker, s2_parent_cell, s2_chilren_cells, track_set_tile):
        """Batch processing deduplicates overlapping children from multiple parents."""
        from scripts.populate_cache import populateCacheForTiles

        children = s2_chilren_cells

        # Mock to track Overpass calls
        mock_run_overpass = mocker.patch("kishin_trails.overpass.runOverpass")
        mock_run_overpass.return_value = {
            "version": 0.6,
            "elements": []
        }

        # Run with parent + some of its children (should deduplicate)
        populateCacheForTiles([s2_parent_cell] + list(children[:5]))

        # Should process all unique children from parent
        from kishin_trails.utils import s2CellToChildren
        expected_children = s2CellToChildren(s2_parent_cell, 16)
        assert len(track_set_tile) == len(expected_children)
        assert set(track_set_tile) == set(expected_children)

        # Yet only 1 overpass call.
        assert mock_run_overpass.call_count == 1

    def test_batch_processing_multiple_parents(self, db_session, mocker, s2_parent_cell, track_set_tile):
        """Batch processing handles multiple non-overlapping parents."""
        from scripts.populate_cache import populateCacheForTiles
        from kishin_trails.utils import s2CellToChildren, s2CellToParent

        # Get two non-overlapping parent tiles
        parent1 = s2_parent_cell
        parent2 = s2CellToParent("478f7577b", 13)

        # Mock to track Overpass calls
        mock_run_overpass = mocker.patch("kishin_trails.overpass.runOverpass")
        mock_run_overpass.return_value = {
            "version": 0.6,
            "elements": []
        }

        # Run with two parents
        populateCacheForTiles([parent1, parent2])

        # Two parents, each with their children
        expected_count = len(s2CellToChildren(parent1, 16)) + len(s2CellToChildren(parent2, 16))
        assert len(track_set_tile) == expected_count

        # Two parents, only two calls to overpass.
        assert mock_run_overpass.call_count == 2

    def test_batch_processing_with_duplicates(self, db_session, mocker, s2_test_cell):
        """Batch processing logs deduplication when same tile is passed twice."""
        from scripts.populate_cache import populateCacheForTiles

        # Mock to track Overpass calls
        mock_run_overpass = mocker.patch("kishin_trails.overpass.runOverpass")
        mock_run_overpass.return_value = {
            "version": 0.6,
            "elements": []
        }

        # Pass same tile twice
        populateCacheForTiles([s2_test_cell, s2_test_cell])

        # Should only process once
        assert mock_run_overpass.call_count == 1
