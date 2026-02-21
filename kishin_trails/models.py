"""
SQLAlchemy models for the Kishin API.
"""

from sqlalchemy import Column, Integer, String
from kishin_trails.database import Base


class User(Base):
    """
    User model for authentication and profile data.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
