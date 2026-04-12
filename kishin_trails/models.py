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
    """Post-processed Point of Interest model for validated OSM elements.

    Stores POIs that have been processed and validated after initial import,
    separate from the raw POI data. Used for quality control and curation.

    Attributes:
        id: Primary key for the post-processed POI.
        osm_id: Unique OpenStreetMap element ID.
        name: Name of the POI from OSM tags.
        tile_type: Type of POI (e.g., 'peak', 'natural', 'industrial').
        tiles: Related Tile records associated with this POI.
    """

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


class NoiseCache(Base):
    """Cache model for Perlin noise values.

    Stores computed Perlin noise values for H3 cells to avoid redundant calculations.
    Uses composite primary key to ensure one entry per unique parameter combination.

    Attributes:
        cell: H3 cell identifier (primary key component).
        scale: Noise scale parameter (primary key component).
        octaves: Number of noise octaves (primary key component).
        amplitude_decay: Amplitude decay factor per octave (primary key component).
        noise_value: Computed noise value in range [0, 1].
    """

    __tablename__ = "noise_cache"

    cell = Column(String, primary_key=True)
    scale = Column(Integer, primary_key=True)
    octaves = Column(Integer, primary_key=True)
    amplitude_decay = Column(Float, primary_key=True)
    noise_value = Column(Float, nullable=False)
