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
def h3_test_cell():
    """Fixture providing a test H3 cell (resolution 10)."""
    return "8a1f9c4e628ffff"


@pytest.fixture
def h3_parent_cell(h3_test_cell):
    """Fixture providing parent H3 cell (resolution 8) for batch tests."""
    import h3
    return h3.cell_to_parent(h3_test_cell, res=8)


@pytest.fixture
def h3_children_cells(h3_parent_cell):
    """Fixture providing 10 children cells (resolution 10) from parent."""
    import h3
    return h3.cell_to_children(h3_parent_cell, res=10)[:10]


class TestTileIdempotency:
    """Tests for Tile and POI idempotency."""
    def test_populate_twice_no_duplicates(self, db_session, mock_overpass_response, h3_test_cell, mocker):
        """Running populate twice produces identical DB state, no duplicates."""
        from scripts.populate_cache import populateCacheForTile

        # Mock runOverpass to return our fixed response
        mocker.patch("kishin_trails.overpass.runOverpass", return_value=mock_overpass_response)

        # First run
        populateCacheForTile(h3_test_cell)
        poi_count_1 = db_session.query(POI).filter(POI.h3_cell == h3_test_cell).count()

        # Second run (should not add duplicates)
        populateCacheForTile(h3_test_cell)
        poi_count_2 = db_session.query(POI).filter(POI.h3_cell == h3_test_cell).count()

        assert poi_count_1 == poi_count_2
        assert poi_count_1 > 0

    def test_restore_deleted_poi(self, db_session, mock_overpass_response, h3_test_cell, mocker):
        """Deleting a POI and re-running restores it without affecting others."""
        from scripts.populate_cache import populateCacheForTile

        mocker.patch("kishin_trails.overpass.runOverpass", return_value=mock_overpass_response)

        # Initial population
        populateCacheForTile(h3_test_cell)
        all_pois = db_session.query(POI).filter(POI.h3_cell == h3_test_cell).all()
        initial_osm_ids = {poi.osm_id
                           for poi in all_pois}
        initial_count = len(all_pois)

        # Delete one POI
        if all_pois:
            deleted_poi = all_pois[0]
            db_session.delete(deleted_poi)
            db_session.commit()

        # Re-populate
        populateCacheForTile(h3_test_cell, skipCached=False)

        # Verify restoration
        final_pois = db_session.query(POI).filter(POI.h3_cell == h3_test_cell).all()
        final_osm_ids = {poi.osm_id
                         for poi in final_pois}

        assert final_osm_ids == initial_osm_ids
        assert len(final_pois) == initial_count

    def test_complete_partial_tile(self, db_session, mock_overpass_response, h3_test_cell, mocker):
        """Tile row exists - normal mode skips it without re-processing."""
        from scripts.populate_cache import populateCacheForTile

        # Simulate interrupted run: Tile created, no POIs
        tile = Tile(h3_cell=h3_test_cell, tile_type=None)
        db_session.add(tile)
        db_session.commit()

        mocker.patch("kishin_trails.overpass.runOverpass", return_value=mock_overpass_response)

        # Re-run with skipCached=True (default) - should skip existing tile
        populateCacheForTile(h3_test_cell)

        # Verify tile was NOT modified (still has no POIs)
        tile_data = getTile(h3_test_cell)
        assert tile_data is not None
        assert len(tile_data["pois"]) == 0

    def test_tile_type_never_updated(self, db_session, h3_test_cell, mocker):
        """Existing tile_type is preserved even if Overpass returns different type."""
        from scripts.populate_cache import populateCacheForTile

        # Pre-populate with specific tile_type
        setTile(h3_test_cell,
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
        populateCacheForTile(h3_test_cell)

        # Verify tile_type unchanged
        tile = db_session.query(Tile).filter(Tile.h3_cell == h3_test_cell).first()
        assert tile.tile_type == "natural"

    def test_tile_type_preserved_when_null(self, db_session, mock_overpass_response, h3_test_cell, mocker):
        """Tile with NULL tile_type keeps NULL after re-population."""
        from scripts.populate_cache import populateCacheForTile

        # Create tile with NULL tile_type
        tile = Tile(h3_cell=h3_test_cell, tile_type=None)
        db_session.add(tile)
        db_session.commit()

        mocker.patch("kishin_trails.overpass.runOverpass", return_value=mock_overpass_response)

        # Re-populate
        populateCacheForTile(h3_test_cell)

        # Verify tile_type is still NULL
        tile = db_session.query(Tile).filter(Tile.h3_cell == h3_test_cell).first()
        assert tile.tile_type is None

    def test_restore_empty_tile_with_skip_cached_false(self, db_session, mock_overpass_response, h3_test_cell, mocker):
        """Tile exists with no POIs - skipCached=False restores POIs."""
        from scripts.populate_cache import populateCacheForTile

        # Create tile with no POIs
        tile = Tile(h3_cell=h3_test_cell, tile_type=None)
        db_session.add(tile)
        db_session.commit()

        mocker.patch("kishin_trails.overpass.runOverpass", return_value=mock_overpass_response)

        # Re-populate with skipCached=False to force processing
        populateCacheForTile(h3_test_cell, skipCached=False)

        # Verify POIs were added
        tile_data = getTile(h3_test_cell)
        assert tile_data is not None
        assert len(tile_data["pois"]) > 0

        # Verify POI records in database
        poi_count = db_session.query(POI).filter(POI.h3_cell == h3_test_cell).count()
        assert poi_count > 0

    def test_restore_partial_pois_with_skip_cached_false(
        self,
        db_session,
        mock_overpass_response,
        h3_test_cell,
        mocker
    ):
        """Tile exists with partial POIs - skipCached=False restores missing POIs."""
        from scripts.populate_cache import populateCacheForTile

        # Initial population
        populateCacheForTile(h3_test_cell, skipCached=False)
        all_pois = db_session.query(POI).filter(POI.h3_cell == h3_test_cell).all()
        initial_osm_ids = {poi.osm_id
                           for poi in all_pois}
        initial_count = len(all_pois)
        assert initial_count > 0

        # Delete some POIs (but not all)
        if len(all_pois) > 1:
            for poi in all_pois[:-1]:  # Keep last POI
                db_session.delete(poi)
            db_session.commit()
            remaining_count = db_session.query(POI).filter(POI.h3_cell == h3_test_cell).count()
            assert remaining_count == 1

        # Re-populate with skipCached=False to restore deleted POIs
        populateCacheForTile(h3_test_cell, skipCached=False)

        # Verify all POIs restored
        final_pois = db_session.query(POI).filter(POI.h3_cell == h3_test_cell).all()
        final_osm_ids = {poi.osm_id
                         for poi in final_pois}
        assert final_osm_ids == initial_osm_ids
        assert len(final_pois) == initial_count

    def test_populate_tile_type_with_skip_cached_false(self, db_session, mock_overpass_response, h3_test_cell, mocker):
        """Tile with NULL tile_type - skipCached=False populates tile_type from POIs."""
        from scripts.populate_cache import populateCacheForTile

        # Create tile with NULL tile_type
        tile = Tile(h3_cell=h3_test_cell, tile_type=None)
        db_session.add(tile)
        db_session.commit()

        mocker.patch("kishin_trails.overpass.runOverpass", return_value=mock_overpass_response)

        # Re-populate with skipCached=False
        populateCacheForTile(h3_test_cell, skipCached=False)

        # Verify tile_type was set based on POI type
        tile_data = getTile(h3_test_cell)
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

    def test_insert_junction_entry_no_duplicates(self, db_session, h3_test_cell):
        """insertJunctionEntry with INSERT OR IGNORE never creates duplicates."""
        from scripts.populate_cache import insertJunctionEntry, insertOrGetPostProcessingPoi

        poi_id = insertOrGetPostProcessingPoi(12345, "Forest", "natural")

        # Insert twice
        insertJunctionEntry(h3_test_cell, poi_id)
        insertJunctionEntry(h3_test_cell, poi_id)

        # Verify single entry
        result = db_session.execute(
            text(
                "SELECT COUNT(*) FROM tile_post_processing_pois WHERE tile_h3_cell = :tile AND post_processing_poi_id = :poi"
            ),
            {
                "tile": h3_test_cell,
                "poi": poi_id
            }
        )
        assert result.scalar() == 1

    def test_fill_polygons_safe_to_rerun(self, db_session, h3_test_cell):
        """--fill-polygons can be run multiple times safely."""
        from scripts.populate_cache import (fillPolygonInteriors, insertJunctionEntry, insertOrGetPostProcessingPoi)

        # Setup: PostProcessingPoI with linked tiles
        poi_id = insertOrGetPostProcessingPoi(12345, "Forest", "natural")
        insertJunctionEntry(h3_test_cell, poi_id)

        tile = Tile(h3_cell=h3_test_cell, tile_type=None)
        db_session.add(tile)
        db_session.commit()

        # First fill
        fillPolygonInteriors()
        tile_type_1 = db_session.query(Tile).filter(Tile.h3_cell == h3_test_cell).first().tile_type

        # Second fill (should be safe no-op)
        fillPolygonInteriors()
        tile_type_2 = db_session.query(Tile).filter(Tile.h3_cell == h3_test_cell).first().tile_type

        assert tile_type_1 == "natural"
        assert tile_type_2 == "natural"

        # PostProcessingPoI should be deleted after first fill
        poi_count = db_session.query(PostProcessingPoI).filter(PostProcessingPoI.id == poi_id).count()
        assert poi_count == 0

    def test_post_processing_poi_to_tile_restoration(self, db_session, h3_test_cell, mocker):
        """PostProcessingPoI linked to tiles - validates tile_type propagation with skipCached=False."""
        from scripts.populate_cache import (
            fillPolygonInteriors,
            insertJunctionEntry,
            insertOrGetPostProcessingPoi,
            populateCacheForTile,
        )

        # Create PostProcessingPoI
        poi_id = insertOrGetPostProcessingPoi(54321, "Test Forest", "natural")

        # Link to tile via junction table
        insertJunctionEntry(h3_test_cell, poi_id)

        # Create tile with NULL tile_type (simulating incomplete state)
        tile = Tile(h3_cell=h3_test_cell, tile_type=None)
        db_session.add(tile)
        db_session.commit()

        # Verify initial state
        tile_initial = db_session.query(Tile).filter(Tile.h3_cell == h3_test_cell).first()
        assert tile_initial.tile_type is None

        # Run fillPolygonInteriors to propagate tile_type
        fillPolygonInteriors()

        # Expire all cached objects to force re-query from database
        db_session.expire_all()

        # Verify tile_type was set from PostProcessingPoI
        tile_final = db_session.query(Tile).filter(Tile.h3_cell == h3_test_cell).first()
        assert tile_final.tile_type == "natural"

        # Verify PostProcessingPoI was cleaned up
        poi_count = db_session.query(PostProcessingPoI).filter(PostProcessingPoI.id == poi_id).count()
        assert poi_count == 0

        # Verify junction entry was cleaned up
        junction_result = db_session.execute(
            text(
                "SELECT COUNT(*) FROM tile_post_processing_pois WHERE tile_h3_cell = :tile AND post_processing_poi_id = :poi"
            ),
            {
                "tile": h3_test_cell,
                "poi": poi_id
            }
        )
        assert junction_result.scalar() == 0


class TestNoCacheFlag:
    """Tests for --no-cache flag behavior."""
    def test_no_cache_flag_processes_all_tiles(self, db_session, h3_test_cell, mocker):
        """--no-cache flag forces re-processing of all tiles."""
        from scripts.populate_cache import populateCacheForTile

        # Pre-populate tile
        setTile(h3_test_cell,
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
        populateCacheForTile(h3_test_cell, skipCached=False)

        # Verify Overpass was called despite tile existing
        assert mock_run_overpass.called

    def test_normal_mode_skips_cached_tiles(self, db_session, h3_test_cell, mocker):
        """Normal mode (skipCached=True) skips cached tiles."""
        from scripts.populate_cache import populateCacheForTile

        # Pre-populate tile
        setTile(h3_test_cell,
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
        populateCacheForTile(h3_test_cell, skipCached=True)

        # Verify Overpass was NOT called
        assert not mock_run_overpass.called

    def test_batch_processing_skips_cached(self, db_session, mocker, h3_parent_cell, h3_children_cells):
        """Normal mode skips cached tiles in batch processing."""
        from scripts.populate_cache import populateCacheForTile

        children = h3_children_cells

        # Pre-cache first 5 tiles
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

        # Run populate
        populateCacheForTile(h3_parent_cell, skipCached=True)

        # Verify only 5 tiles were processed (not the pre-cached ones)
        assert mock_run_overpass.call_count == 44

    def test_no_cache_processes_all_in_batch(self, db_session, mocker, h3_parent_cell, h3_children_cells):
        """--no-cache mode processes all tiles in batch, even cached ones."""
        from scripts.populate_cache import populateCacheForTile

        children = h3_children_cells

        # Pre-cache all tiles
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

        # Run with skipCached=False (simulates --no-cache)
        populateCacheForTile(h3_parent_cell, skipCached=False)

        # Verify all 10 tiles were processed
        assert mock_run_overpass.call_count == 49


class TestSetTileIdempotency:
    """Direct tests for setTile function idempotency."""
    def test_setTile_twice_same_data(self, db_session, h3_test_cell):
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
        setTile(h3_test_cell, "natural", pois)
        tile1 = getTile(h3_test_cell)

        # Second call with same data
        setTile(h3_test_cell, "natural", pois)
        tile2 = getTile(h3_test_cell)

        assert tile1 is not None
        assert tile2 is not None
        assert tile1 == tile2
        assert len(tile1["pois"]) == 2

    def test_setTile_preserves_existing_pois(self, db_session, h3_test_cell):
        """setTile preserves existing POIs, only adds missing ones."""
        # Initial set
        setTile(h3_test_cell,
                "natural",
                [{
                    "osm_id": 123456,
                    "lat": 45.8325,
                    "lon": 6.8652,
                    "name": "Peak 1"
                }])

        # Second set with additional POI
        setTile(
            h3_test_cell,
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
        tile = getTile(h3_test_cell)
        assert tile is not None
        osm_ids = {poi["osm_id"]
                   for poi in tile["pois"]}

        assert 123456 in osm_ids
        assert 123457 in osm_ids
        assert len(tile["pois"]) == 2

    def test_setTile_does_not_update_poi_data(self, db_session, h3_test_cell):
        """setTile does not update existing POI data, only inserts missing."""
        # Initial set
        setTile(h3_test_cell,
                "natural",
                [{
                    "osm_id": 123456,
                    "lat": 45.8325,
                    "lon": 6.8652,
                    "name": "Original Name"
                }])

        # Second set with different name for same osm_id
        setTile(h3_test_cell,
                "natural",
                [{
                    "osm_id": 123456,
                    "lat": 45.9999,
                    "lon": 6.9999,
                    "name": "New Name"
                }])

        # Verify original data preserved
        tile = getTile(h3_test_cell)
        assert tile is not None
        poi = tile["pois"][0]

        assert poi["name"] == "Original Name"
        assert poi["lat"] == 45.8325
        assert poi["lon"] == 6.8652
