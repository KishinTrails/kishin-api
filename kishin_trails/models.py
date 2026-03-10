"""
SQLAlchemy models for the Kishin API.
"""

from sqlalchemy import Column, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from kishin_trails.database import Base


class User(Base):
    """
    User model for authentication and profile data.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)


class Tile(Base):
    __tablename__ = "tiles"

    h3_cell = Column(String, primary_key=True)
    tile_type = Column(String)
    pois = relationship("POI", back_populates="tile", cascade="all, delete-orphan")


class POI(Base):
    __tablename__ = "pois"

    id = Column(Integer, primary_key=True, autoincrement=True)
    h3_cell = Column(String, ForeignKey("tiles.h3_cell"), nullable=False, index=True)
    osm_id = Column(Integer, nullable=False)
    name = Column(String)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    elevation = Column(Integer)

    tile = relationship("Tile", back_populates="pois")

    __table_args__ = (
        UniqueConstraint('h3_cell', 'osm_id', name='uix_h3_osm'),
    )
