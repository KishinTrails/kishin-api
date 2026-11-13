"""
SQLAlchemy models for the Kishin API using S2 cells.

Defines the database schema for users, tiles (S2 cells), and Points of Interest.
"""

from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String, Table, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kishin_trails.database import Base


class User(Base):
    """User model for authentication and profile data.

    Attributes:
        id: Primary key for the user.
        username: Unique username for login.
        hashed_password: Bcrypt-hashed password.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)

    explored_tiles: Mapped[list["Tile"]] = relationship(
        "Tile", secondary="user_explored_tiles", back_populates="explored_by"
    )


class Tile(Base):
    """Tile model representing an S2 cell at level 16.

    Stores S2 cell identifiers and their associated POIs.

    Attributes:
        s2_cell_id: Primary key - the S2 cell ID as hex token.
        tile_type: Type of POI in this tile (e.g., 'peak', 'natural', 'industrial').
        pois: Related POI records for this tile.
    """

    __tablename__ = "tiles"

    s2_cell_id: Mapped[str] = mapped_column(String, primary_key=True)
    tile_type: Mapped[str | None] = mapped_column(String)
    active: Mapped[bool | None] = mapped_column(Boolean)
    pois: Mapped[list["POI"]] = relationship("POI", back_populates="tile", cascade="all, delete-orphan")
    post_processing_pois: Mapped[list["PostProcessingPoI"]] = relationship(
        "PostProcessingPoI",
        secondary="tile_post_processing_pois",
        back_populates="tiles"
    )
    explored_by: Mapped[list["User"]] = relationship(
        "User", secondary="user_explored_tiles", back_populates="explored_tiles"
    )


class POI(Base):
    """Point of Interest model for OSM elements within an S2 cell.

    Represents trail-related features like peaks, viewpoints, parks, etc.

    Attributes:
        id: Primary key for the POI.
        s2_cell_id: Foreign key to the parent S2 tile.
        osm_id: OpenStreetMap element ID.
        name: Name of the POI from OSM tags.
        lat: Latitude of the POI.
        lon: Longitude of the POI.
        elevation: Elevation in meters (for peaks).
        tile: Relationship back to parent Tile.
    """

    __tablename__ = "pois"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    s2_cell_id: Mapped[str] = mapped_column(String, ForeignKey("tiles.s2_cell_id"), nullable=False, index=True)
    osm_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str | None] = mapped_column(String)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    elevation: Mapped[int | None] = mapped_column(Integer)

    tile: Mapped["Tile"] = relationship("Tile", back_populates="pois")

    __table_args__ = (UniqueConstraint('s2_cell_id', 'osm_id', name='uix_s2_osm'),)


tile_post_processing_pois = Table(
    "tile_post_processing_pois",
    Base.metadata,
    Column("tile_s2_cell_id",
           String,
           ForeignKey("tiles.s2_cell_id"),
           primary_key=True),
    Column("post_processing_poi_id",
           Integer,
           ForeignKey("post_processing_pois.id"),
           primary_key=True)
)

user_explored_tiles = Table(
    "user_explored_tiles",
    Base.metadata,
    Column("user_id",
           Integer,
           ForeignKey("users.id"),
           primary_key=True),
    Column("tile_s2_cell_id",
           String,
           ForeignKey("tiles.s2_cell_id"),
           primary_key=True)
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

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    osm_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(String)
    tile_type: Mapped[str] = mapped_column(String, nullable=False)
    tiles: Mapped[list["Tile"]] = relationship(
        "Tile", secondary="tile_post_processing_pois", back_populates="post_processing_pois"
    )


class NoiseCache(Base):
    """Cache model for Perlin noise values.

    Stores computed Perlin noise values for S2 cells to avoid redundant calculations.
    Uses composite primary key to ensure one entry per unique parameter combination.

    Attributes:
        s2_cell_id: S2 cell ID as hex token (primary key component).
        scale: Noise scale parameter (primary key component).
        octaves: Number of noise octaves (primary key component).
        amplitude_decay: Amplitude decay factor per octave (primary key component).
        noise_value: Computed noise value in range [0, 1].
    """

    __tablename__ = "noise_cache"

    s2_cell_id: Mapped[str] = mapped_column(String, primary_key=True)
    scale: Mapped[int] = mapped_column(Integer, primary_key=True)
    octaves: Mapped[int] = mapped_column(Integer, primary_key=True)
    amplitude_decay: Mapped[float] = mapped_column(Float, primary_key=True)
    noise_value: Mapped[float] = mapped_column(Float, nullable=False)
