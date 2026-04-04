"""
Pytest configuration and shared fixtures.
"""

import os

# FORCE the DATABASE_URL to a test-specific file before any kishin_trails modules are loaded
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from kishin_trails.main import app
from kishin_trails.database import Base, getDb, SESSION_LOCAL
from kishin_trails.dependencies import getCurrentUser
from kishin_trails.models import User, Tile, POI

# --- Test Database Setup ---
# We still use in-memory for speed in the fixtures, 
# but the env var above protects us from accidental disk writes to kishin.db.
SQLALCHEMY_DATABASE_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Monkey-patch cache module to use test database
import kishin_trails.database as database_module
import kishin_trails.cache as cache_module
database_module.SESSION_LOCAL = TestingSessionLocal
cache_module.SESSION_LOCAL = TestingSessionLocal


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
async def authenticated_client(client, db_session):
    """
    Fixture that provides an authenticated client for testing protected routes.
    Overrides getCurrentUser to return a mock test user.
    """
    test_user = User(id=1, username="testuser", hashed_password="dummy_hash")
    db_session.add(test_user)
    db_session.commit()

    def override_get_current_user():
        return test_user

    app.dependency_overrides[getCurrentUser] = override_get_current_user
    yield client
    app.dependency_overrides.pop(getCurrentUser, None)


@pytest.fixture(scope="function")
def cache_with_data():
    """
    Fixture that provides a function to pre-populate the cache with test POI data.
    """
    import kishin_trails.cache as cache_module
    import kishin_trails.database as db_module
    
    # Ensure we're using the patched version
    cache_module.SESSION_LOCAL = TestingSessionLocal
    db_module.SESSION_LOCAL = TestingSessionLocal
    
    from kishin_trails.cache import setTile

    def _set_tile(h3_cell: str, tile_type: str | None, pois: list):
        setTile(h3_cell, tile_type, pois)

    return _set_tile
