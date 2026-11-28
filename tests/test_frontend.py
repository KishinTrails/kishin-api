"""
Tests for frontend.py (the built frontend served with FRONTEND_DIR), the /api prefix and
/api/config.
"""

import importlib

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import kishin_trails.main as mainModule
from kishin_trails import frontend
from kishin_trails.config import settings

INDEX = "<!doctype html><title>Kishin Trails</title>"
SCRIPT = "console.log('Foo');"


@pytest.fixture
def build(tmp_path):
    """A build directory: index.html, assets/index-abc123.js, logo.png, and a file next to it."""
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text(INDEX)
    (root / "assets" / "index-abc123.js").write_text(SCRIPT)
    (root / "logo.png").write_bytes(b"\x89PNG")
    (tmp_path / "secret.txt").write_text("Bar")
    return root


@pytest.fixture
def appWithFrontend(monkeypatch, build):
    """Builds the app again with FRONTEND_DIR set to the build, then restores the module's app."""
    monkeypatch.setattr(settings, "FRONTEND_DIR", build)
    yield importlib.reload(mainModule).app
    monkeypatch.undo()
    importlib.reload(mainModule)


async def _get(app: FastAPI, path: str):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get(path)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/", "/map", "/plan", "/athlete", "/athlete/activities/1001", "/nope.js"])
async def test_pages_answer_index(appWithFrontend, path):
    response = await _get(appWithFrontend, path)
    assert response.status_code == 200
    assert response.text == INDEX
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["content-security-policy"] == "frame-ancestors 'none'"


@pytest.mark.asyncio
async def test_asset_is_immutable(appWithFrontend):
    response = await _get(appWithFrontend, "/assets/index-abc123.js")
    assert response.status_code == 200
    assert response.text == SCRIPT
    assert response.headers["cache-control"] == frontend.IMMUTABLE


@pytest.mark.asyncio
async def test_file_at_root_is_served(appWithFrontend):
    response = await _get(appWithFrontend, "/logo.png")
    assert response.content == b"\x89PNG"
    assert response.headers["cache-control"] == "no-cache"


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/nope", "/api/plan/nope/nope", "/withings/nope", "/api"])
async def test_reserved_paths_answer_json_404(appWithFrontend, path):
    response = await _get(appWithFrontend, path)
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/json"


@pytest.mark.asyncio
@pytest.mark.parametrize("expose", [False, True])
async def test_docs_paths_are_never_a_page(monkeypatch, build, expose):
    monkeypatch.setattr(settings, "FRONTEND_DIR", build)
    monkeypatch.setattr(settings, "EXPOSE_DOCS", expose)
    app = importlib.reload(mainModule).app
    try:
        for path in ("/docs", "/redoc", "/openapi.json"):
            response = await _get(app, path)
            assert response.status_code == (200 if expose else 404), path
            assert response.text != INDEX, path
    finally:
        monkeypatch.undo()
        importlib.reload(mainModule)


@pytest.mark.asyncio
async def test_api_routes_still_answer(appWithFrontend):
    assert "Welcome" in (await _get(appWithFrontend, "/api/")).json()["message"]
    assert (await _get(appWithFrontend, "/api/plan")).status_code == 401
    assert (await _get(appWithFrontend, "/withings/withings.html")).status_code == 200


def test_resolve_stays_inside_the_build(build):
    root = build.resolve()
    assert frontend.resolve(root, "../secret.txt") == root / "index.html"
    assert frontend.resolve(root, "assets/../../secret.txt") == root / "index.html"
    assert frontend.resolve(root, "assets") == root / "index.html"
    assert frontend.resolve(root, "assets/index-abc123.js") == root / "assets" / "index-abc123.js"


def test_resolve_refuses_a_symlink_out_of_the_build(build):
    (build / "link.txt").symlink_to(build.parent / "secret.txt")
    root = build.resolve()
    assert frontend.resolve(root, "link.txt") == root / "index.html"


def test_mount_refuses_a_directory_without_index(tmp_path):
    with pytest.raises(RuntimeError, match="index.html"):
        frontend.mount(FastAPI(), tmp_path)


@pytest.mark.asyncio
async def test_no_page_without_frontend_dir(client):
    assert settings.FRONTEND_DIR is None
    assert (await client.get("/plan")).status_code == 404


@pytest.mark.asyncio
async def test_config_needs_login(client):
    assert (await client.get("/api/config")).status_code == 401


@pytest.mark.asyncio
async def test_config_returns_the_default_centre(authenticated_client, monkeypatch):
    monkeypatch.setattr(settings, "DEFAULT_CENTER_LAT", 48.8566)
    monkeypatch.setattr(settings, "DEFAULT_CENTER_LON", 2.3522)
    response = await authenticated_client.get("/api/config")
    assert response.status_code == 200
    assert response.json() == {"default_center": {"lat": 48.8566, "lon": 2.3522}}
