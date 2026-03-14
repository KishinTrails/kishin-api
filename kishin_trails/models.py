"""
SQLAlchemy models for the Kishin API.

Defines the database schema for users, tiles (H3 cells), and Points of Interest.
"""

from sqlalchemy import Column, Float, ForeignKey, Integer, String, UniqueConstraint
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
