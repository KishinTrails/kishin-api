"""
Main entry point for the Kishin API.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from kishin_trails.database import engine, Base
from kishin_trails.auth import router as auth_router
from kishin_trails.poi import router as poi_router
from kishin_trails.trails import router as trails_router
from kishin_trails.noise import router as noise_router
from kishin_trails.cache import initDb as initCacheDb
from kishin_trails.dependencies import getCurrentUser
from kishin_trails.models import User


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan event to handle startup and shutdown tasks.
    Creates database tables on startup.
    """
    Base.metadata.create_all(bind=engine)
    initCacheDb()
    yield


app = FastAPI(
    title="Kishin Trails API",
    description="",
    version="0.1.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(auth_router)
if poi_router:
    app.include_router(poi_router)
if trails_router:
    app.include_router(trails_router)
if noise_router:
    app.include_router(noise_router)


@app.get("/", summary="Root endpoint")
def readRoot():
    """
    Public root endpoint to verify the API is running.
    """
    return {
        "message": "Welcome to Kishin Trails' API. Go to /docs for the API documentation."
    }


@app.get("/me", summary="Get current user info")
def readUsersMe(currentUser: User = Depends(getCurrentUser)):
    """
    Guarded endpoint to return the currently authenticated user's information.
    """
    return {
        "username": currentUser.username,
        "id": currentUser.id
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
