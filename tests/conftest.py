"""
Pytest configuration and shared fixtures.
"""

import os

# Use the in-memory URL as the env var itself — this way any module that reads
# DATABASE_URL from settings (including noise_cache_sqlite._get_session()) will
# also get the in-memory database and never touch the filesystem.
# The old "sqlite:///./test.db" guard was half-hearted: it prevented writes to
# kishin.db but still created a test.db file on disk.
os.environ["DATABASE_URL"] = "sqlite://"
# A test signing key, so the tests do not depend on a local .env (the setting has
# no default).
os.environ["SECRET_KEY"] = "test-secret-key-of-at-least-32-characters"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from kishin_trails.main import app
from kishin_trails.database import Base, getDb
from kishin_trails.auth import LOGIN_THROTTLE
from kishin_trails.dependencies import requireLogin
from kishin_trails.models import Tile, POI

# ---------------------------------------------------------------------------
# Single shared in-memory engine for the entire test session.
# StaticPool ensures every connection (including from monkey-patched modules)
# sees the same in-memory database instead of getting an independent blank one.
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = "sqlite://"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={
        "check_same_thread": False
    },
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ---------------------------------------------------------------------------
# Monkey-patch every module that manages its own session or engine.
#
# - database_module / cache_module: patch SESSION_LOCAL (their public API).
# - noise_cache: patch both SESSION_LOCAL and _LOCAL._session_factory so that
#   all code paths (direct SESSION_LOCAL use and the lazy per-process
#   _get_session() factory) hit the same test engine. Without both patches,
#   initCache() creates the table on one engine while queries run against
#   another, producing "no such table: noise_cache".
# ---------------------------------------------------------------------------
import kishin_trails.database as database_module
import kishin_trails.cache as cache_module
import kishin_trails.noise_cache as noise_cache_module

database_module.SESSION_LOCAL = TestingSessionLocal
cache_module.SESSION_LOCAL = TestingSessionLocal

# Force noise_cache to use our test session factory immediately,
# bypassing its lazy per-process engine creation entirely.
noise_cache_module._LOCAL.session_factory = TestingSessionLocal

# Create all tables on the test engine once at collection time.
# This must happen at module level — not inside a fixture — because tests
# like test_noise_cache and test_perlin call initCache() / clearCache()
# directly without going through the db_session fixture. initCache() calls
# Base.metadata.create_all(bind=<production engine>), which creates tables
# on the wrong engine. By pre-creating them here on the test engine,
# all TestingSessionLocal queries find the tables they expect.
Base.metadata.create_all(bind=engine)


@pytest.fixture(autouse=True)
def clearLoginThrottle():
    """Each test starts with no recorded login attempt."""
    LOGIN_THROTTLE.clear()
    yield
    LOGIN_THROTTLE.clear()


@pytest.fixture(scope="function")
def db_session():
    """
    Fixture to provide a clean in-memory database session for each test.
    """
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        # Recreate immediately so tests that don't use this fixture
        # (e.g. test_noise_cache, test_perlin) still find their tables.
        Base.metadata.create_all(bind=engine)


@pytest_asyncio.fixture(scope="function")
async def client(db_session):
    """
    Fixture to provide an AsyncClient for FastAPI testing,
    overriding the database dependency.
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[getDb] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def authenticated_client(client):
    """
    Fixture that provides an authenticated client for testing protected routes.
    Overrides requireLogin so that every request is accepted.
    """
    app.dependency_overrides[requireLogin] = lambda: None
    yield client
    app.dependency_overrides.pop(requireLogin, None)


@pytest.fixture(scope="function")
def cache_with_data():
    """
    Fixture that provides a function to pre-populate the cache with test POI data.
    """
    from kishin_trails.cache import setTile

    def _set_tile(s2_cell: str, tile_type: str | None, pois: list):
        setTile(s2_cell, tile_type, pois)

    return _set_tile


@pytest.fixture(scope="function")
def mock_cell_activity(mocker):
    """
    Fixture to mock isCellActive for testing.

    By default, all cells are active (returns True).
    Call the returned function with a list of cell IDs to mark as inactive.

    Usage:
        def test_something(mock_cell_activity):
            mock_cell_activity(inactive_cells=["4XXXXXXXX"])
            # Now this specific cell will be inactive (returns False)
            # All other cells remain active (return True)

    Args:
        mocker: pytest-mock fixture for patching.

    Returns:
        A function that accepts an optional inactive_cells list parameter.
    """
    from kishin_trails.cache import isCellActive

    inactive_cells_set = set()

    def mock_is_cell_active(cell: str, *args, **kwargs) -> bool:
        return cell not in inactive_cells_set

    def configure_mock(inactive_cells: list[str] | None = None):
        """
        Configure which cells should be inactive.

        Args:
            inactive_cells: List of S2 cell IDs that should return False (inactive).
                           All other cells will return True (active).
                           If None or empty list, all cells are active.
        """
        nonlocal inactive_cells_set
        inactive_cells_set = set(inactive_cells) if inactive_cells else set()
        mocker.patch("kishin_trails.cache.isCellActive", side_effect=mock_is_cell_active)

    mocker.patch("kishin_trails.cache.isCellActive", side_effect=mock_is_cell_active)
    return configure_mock


@pytest.fixture(scope="function")
def health_engine(monkeypatch):
    """The made-up health-sync database of tests/healthdata.py.

    The CLI reaches it through ``health.healthEngine`` and the API through the
    ``getHealthConnection`` dependency; both are replaced. Days are in UTC.
    """
    from healthdata import buildHealthEngine
    from kishin_trails import health
    from kishin_trails.athlete import getHealthConnection
    from kishin_trails.config import settings
    from kishin_trails.plan import optionalHealthConnection

    sqlite = buildHealthEngine()

    def override_health_connection():
        with sqlite.connect() as conn:
            yield conn

    monkeypatch.setattr(health, "healthEngine", lambda url, prefix="": sqlite)
    monkeypatch.setattr(settings, "TIMEZONE", "UTC")
    app.dependency_overrides[getHealthConnection] = override_health_connection
    app.dependency_overrides[optionalHealthConnection] = override_health_connection
    yield sqlite
    app.dependency_overrides.pop(getHealthConnection, None)
    app.dependency_overrides.pop(optionalHealthConnection, None)
