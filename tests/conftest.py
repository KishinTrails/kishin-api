"""
Pytest configuration and shared fixtures.

The tests run against PostgreSQL, the database the application uses. By default
testcontainers starts a throwaway ``postgres:17-alpine`` container (the server's
version) for the run and removes it at exit; Docker must be running. To use an
existing server instead, set ``TEST_DATABASE_URL`` to a superuser URL on it, such as
``postgresql+psycopg://postgres:password@127.0.0.1:55432/postgres``: the databases
``kishin_test`` and ``health_test`` are then dropped and created there.
"""

import atexit
import os

from sqlalchemy import create_engine, make_url, text

#: The two databases the tests create, one for the game data, one for the health data.
GAME_TEST_DATABASE = "kishin_test"
HEALTH_TEST_DATABASE = "health_test"


def _serverUrl() -> str:
    """A superuser URL on the test PostgreSQL server, starting a container when needed."""
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        return url
    from testcontainers.community.postgres import PostgresContainer  # pylint: disable=import-outside-toplevel

    container = PostgresContainer("postgres:17-alpine", driver="psycopg")
    container.start()
    atexit.register(container.stop)
    return container.get_connection_url()


def _createDatabases(serverUrl: str) -> tuple[str, str]:
    """Drops and creates the two test databases; returns their URLs."""
    admin = create_engine(serverUrl, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        for name in (GAME_TEST_DATABASE, HEALTH_TEST_DATABASE):
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    base = make_url(serverUrl)
    return (
        base.set(database=GAME_TEST_DATABASE).render_as_string(hide_password=False),
        base.set(database=HEALTH_TEST_DATABASE).render_as_string(hide_password=False),
    )


# Set before the application is imported: kishin_trails.database builds its engine,
# and noise_cache its per-process engines, from DATABASE_URL.
os.environ["DATABASE_URL"], os.environ["HEALTH_TEST_DATABASE_URL"] = _createDatabases(_serverUrl())
# A test signing key, so the tests do not depend on a local .env (the setting has
# no default).
os.environ["SECRET_KEY"] = "test-secret-key-of-at-least-32-characters"

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from kishin_trails import database  # noqa: E402
from kishin_trails.main import app  # noqa: E402
from kishin_trails.database import Base, getDb  # noqa: E402
from kishin_trails.auth import LOGIN_THROTTLE  # noqa: E402
from kishin_trails.dependencies import requireLogin  # noqa: E402

# Created once: tests like test_noise_cache call the cache functions directly,
# without the db_session fixture.
Base.metadata.create_all(bind=database.engine)


def _truncateAll() -> None:
    """Empties every table of the game database, and restarts its id sequences.

    Code under test commits through its own sessions, so rolling back a
    transaction around the test would not undo its writes. ``lock_timeout``
    turns a session left open by a test into an error instead of a hang.
    """
    names = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    with database.engine.begin() as conn:
        conn.execute(text("SET LOCAL lock_timeout = '5s'"))
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def cleanDatabase():
    """Each test starts and ends with empty tables, and the tables exist."""
    Base.metadata.create_all(bind=database.engine)
    yield
    _truncateAll()


@pytest.fixture(autouse=True)
def clearLoginThrottle():
    """Each test starts with no recorded login attempt."""
    LOGIN_THROTTLE.clear()
    yield
    LOGIN_THROTTLE.clear()


@pytest.fixture(scope="function")
def db_session():
    """A session on the test database; its tables are emptied after the test."""
    db = database.SESSION_LOCAL()
    try:
        yield db
    finally:
        db.close()


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

    engine = buildHealthEngine()

    def override_health_connection():
        with engine.connect() as conn:
            yield conn

    monkeypatch.setattr(health, "healthEngine", lambda url, prefix="": engine)
    monkeypatch.setattr(settings, "TIMEZONE", "UTC")
    app.dependency_overrides[getHealthConnection] = override_health_connection
    app.dependency_overrides[optionalHealthConnection] = override_health_connection
    yield engine
    app.dependency_overrides.pop(getHealthConnection, None)
    app.dependency_overrides.pop(optionalHealthConnection, None)
    engine.dispose()
