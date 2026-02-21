"""
Main entry point for the Kishin API.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from kishin_trails.database import engine, Base
from kishin_trails.auth import router as auth_router
from kishin_trails.overpass import router as overpass_router
from kishin_trails.dependencies import get_current_user
from kishin_trails.models import User


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan event to handle startup and shutdown tasks.
    Creates database tables on startup.
    """
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Kishin API",
    description="Professional level FastAPI server with OSM data and JWT authentication.",
    version="1.0.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(auth_router)
app.include_router(overpass_router)


@app.get("/", summary="Root endpoint")
def read_root():
    """
    Public root endpoint to verify the API is running.
    """
    return {"message": "Welcome to Kishin API. Go to /docs for the API documentation."}


@app.get("/me", summary="Get current user info")
def read_users_me(current_user: User = Depends(get_current_user)):
    """
    Guarded endpoint to return the currently authenticated user's information.
    """
    return {"username": current_user.username, "id": current_user.id}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
