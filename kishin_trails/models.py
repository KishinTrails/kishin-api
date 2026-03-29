"""
SQLAlchemy models for the Kishin API.

Defines the database schema for users, tiles (H3 cells), and Points of Interest.
"""

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Table, UniqueConstraint
from sqlalchemy.orm import relationship

from kishin_trails.database import Base


class User(Base):
    """User model for authentication and profile data.

    Attributes:
        id: Primary key for the user.
        username: Unique username for login.
        hashed_password: Bcrypt-hashed password.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    explored_tiles = relationship("Tile", secondary="user_explored_tiles", back_populates="explored_by")


class Tile(Base):
    """Tile model representing an H3 hexagonal cell.

    Stores H3 cell identifiers and their associated POIs.

    Attributes:
        h3_cell: Primary key - the H3 cell identifier.
        tile_type: Type of POI in this tile (e.g., 'peak', 'natural', 'industrial').
        pois: Related POI records for this tile.
    """

    __tablename__ = "tiles"

    h3_cell = Column(String, primary_key=True)
    tile_type = Column(String)
    pois = relationship("POI", back_populates="tile", cascade="all, delete-orphan")
    post_processing_pois = relationship(
        "PostProcessingPoI",
        secondary="tile_post_processing_pois",
        back_populates="tiles"
    )
    explored_by = relationship("User", secondary="user_explored_tiles", back_populates="explored_tiles")


class POI(Base):
    """Point of Interest model for OSM elements within an H3 cell.

    Represents trail-related features like peaks, viewpoints, parks, etc.

    Attributes:
        id: Primary key for the POI.
        h3_cell: Foreign key to the parent H3 tile.
        osm_id: OpenStreetMap element ID.
        name: Name of the POI from OSM tags.
        lat: Latitude of the POI.
        lon: Longitude of the POI.
        elevation: Elevation in meters (for peaks).
        tile: Relationship back to parent Tile.
    """

    __tablename__ = "pois"

    id = Column(Integer, primary_key=True, autoincrement=True)
    h3_cell = Column(String, ForeignKey("tiles.h3_cell"), nullable=False, index=True)
    osm_id = Column(Integer, nullable=False)
    name = Column(String)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    elevation = Column(Integer)

    tile = relationship("Tile", back_populates="pois")

    __table_args__ = (UniqueConstraint('h3_cell', 'osm_id', name='uix_h3_osm'),)


tile_post_processing_pois = Table(
    "tile_post_processing_pois",
    Base.metadata,
    Column("tile_h3_cell", String, ForeignKey("tiles.h3_cell"), primary_key=True),
    Column("post_processing_poi_id", Integer, ForeignKey("post_processing_pois.id"), primary_key=True)
)


user_explored_tiles = Table(
    "user_explored_tiles",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("tile_h3_cell", String, ForeignKey("tiles.h3_cell"), primary_key=True)
)


class PostProcessingPoI(Base):
    __tablename__ = "post_processing_pois"

    id = Column(Integer, primary_key=True, autoincrement=True)
    osm_id = Column(Integer, nullable=False, unique=True)
    name = Column(String)
    tile_type = Column(String, nullable=False)
    tiles = relationship(
        "Tile",
        secondary="tile_post_processing_pois",
        back_populates="post_processing_pois"
    )
