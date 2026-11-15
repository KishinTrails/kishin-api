"""
Tests for EXPOSE_DOCS: /docs, /redoc and /openapi.json answer only while it is on.
"""

import importlib

import pytest
from httpx import ASGITransport, AsyncClient

import kishin_trails.main as mainModule
from kishin_trails.config import settings

DOC_ROUTES = ("/docs", "/redoc", "/openapi.json")


@pytest.fixture
def appWithDocs(monkeypatch):
    """Builds the app again with a given EXPOSE_DOCS, then restores the module's app."""
    def build(expose: bool):
        monkeypatch.setattr(settings, "EXPOSE_DOCS", expose)
        return importlib.reload(mainModule).app

    yield build
    monkeypatch.undo()
    importlib.reload(mainModule)


async def _get(app, path: str):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get(path)


@pytest.mark.asyncio
async def test_docs_answer_when_exposed(appWithDocs):
    app = appWithDocs(True)
    for path in DOC_ROUTES:
        assert (await _get(app, path)).status_code == 200, path
    assert "/docs" in (await _get(app, "/")).json()["message"]


@pytest.mark.asyncio
async def test_docs_absent_when_not_exposed(appWithDocs):
    app = appWithDocs(False)
    for path in DOC_ROUTES:
        assert (await _get(app, path)).status_code == 404, path
    assert "/docs" not in (await _get(app, "/")).json()["message"]
