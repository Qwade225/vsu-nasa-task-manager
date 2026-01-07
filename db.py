# TrojanTracks/api/db.py

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)
from sqlalchemy.orm import DeclarativeBase


# --- Settings ---------------------------------------------------------------

class Settings(BaseSettings):
    """
    Application settings loaded from environment variables or .env file
    """
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./trojantracks.db"
    
    # Security
    SECRET_KEY: str = "change-this-in-production"
    JWT_SECRET: str = "change-me-in-prod"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    
    # Application
    DEBUG: bool = False
    PORT: int = 8000
    
    # CORS
    ALLOW_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    
    # Reset tokens
    RESET_TOKEN_TTL_MIN: int = 60

    # Load from .env file at project root
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()


# --- SQLAlchemy base/engine/session ----------------------------------------

class Base(DeclarativeBase):
    """Base class for all database models"""
    pass


# Create async engine with connection pooling
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,  # Log SQL queries when DEBUG=True
    future=True,
    pool_pre_ping=True,  # Verify connections before using them
    pool_size=5,  # Number of connections to maintain
    max_overflow=10,  # Max additional connections when pool is full
)

# Create session factory
SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,  # Keep objects usable after commit
    autoflush=False,  # Don't auto-flush before queries
    class_=AsyncSession,
)


# --- FastAPI dependency (use in routes) ------------------------------------

async def get_db() -> AsyncSession:
    """
    Dependency for FastAPI routes to get a database session.
    Usage: db: AsyncSession = Depends(get_db)
    """
    async with SessionLocal() as session:
        yield session


# --- Database initialization -----------------------------------------------

async def init_db() -> None:
    """
    Initialize database tables.
    Call this on application startup.
    """
    async with engine.begin() as conn:
        # Import all models here to ensure they're registered with Base
        from . import models  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """
    Close database connections.
    Call this on application shutdown.
    """
    await engine.dispose()


# --- Database health check -------------------------------------------------

async def check_db_connection() -> bool:
    """
    Check if database is accessible.
    Returns True if connection successful, False otherwise.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute("SELECT 1")
        return True
    except Exception as e:
        print(f"Database connection failed: {e}")
        return False