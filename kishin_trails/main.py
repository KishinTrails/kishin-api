"""
Main entry point for the Kishin API.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from kishin_trails.database import engine, Base
from kishin_trails.auth import router as auth_router
from kishin_trails.poi import router as poi_router
from kishin_trails.trails import router as trails_router
from kishin_trails.noise import router as noise_router
from kishin_trails.athlete import router as athlete_router
from kishin_trails.plan import router as plan_router
from kishin_trails.cache import initDb as initCacheDb
from kishin_trails.config import servingProblems, settings

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager for startup and shutdown events.

    Handles initialization tasks when the application starts:
    - Refuses to start while a setting from servingProblems is missing, so the
      server never signs tokens without SECRET_KEY, whatever command started it
    - Creates all database tables from SQLAlchemy models
    - Initializes the POI cache database tables

    Yields control back to FastAPI to run the application, then handles
    cleanup on shutdown (if needed in the future).
    """
    problems = servingProblems(settings)
    if problems:
        raise RuntimeError("Cannot serve: " + " ".join(problems))
    Base.metadata.create_all(bind=engine)
    initCacheDb()
    yield


app = FastAPI(
    title="Kishin Trails API",
    description="",
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.EXPOSE_DOCS else None,
    redoc_url="/redoc" if settings.EXPOSE_DOCS else None,
    openapi_url="/openapi.json" if settings.EXPOSE_DOCS else None,
)

app.add_middleware(
    CORSMiddleware,  # type: ignore[invalid-argument-type]
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
if poi_router:
    app.include_router(poi_router)
if trails_router:
    app.include_router(trails_router)
if noise_router:
    app.include_router(noise_router)
app.include_router(athlete_router)
app.include_router(plan_router)

# Static page that displays the code Withings appends to its OAuth redirect, so that a
# program waiting for it (health-sync's first sync) can be given it by hand. Withings checks
# the redirect address with a HEAD request before accepting it: StaticFiles answers HEAD,
# a plain @app.get route answers 405.
app.mount(
    "/withings",
    StaticFiles(directory=Path(__file__).parent / "static" / "withings"),
    name="withings",
)


@app.get("/", summary="Root endpoint")
def readRoot():
    """
    Root endpoint providing API welcome message and documentation pointer.

    This is a public endpoint that confirms the API server is running and,
    when EXPOSE_DOCS is on, directs users to the interactive API documentation.

    Returns:
        Welcome message, with a pointer to /docs when it answers.
    """
    message = "Welcome to Kishin Trails' API."
    if app.docs_url:
        message += f" Go to {app.docs_url} for the API documentation."
    return {
        "message": message
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
