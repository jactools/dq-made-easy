"""
Database Initialization Utility for DQ Agent Harness.

This module provides utilities for:
- Creating database tables
- Running migrations
- Checking database connectivity
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine

from .config import DatabaseConfig, get_database_config
from .models import Base


logger = logging.getLogger(__name__)


class DatabaseInitializer:
    """
    Handles database initialization and table creation.
    
    This class provides methods for:
    - Creating all tables
    - Dropping all tables (for testing)
    - Checking if tables exist
    - Running raw SQL
    """
    
    def __init__(self, config: Optional[DatabaseConfig] = None):
        """
        Initialize the database initializer.
        
        Args:
            config: Optional database configuration (uses global if not provided)
        """
        self.config = config or get_database_config()
        self.engine: Optional[AsyncEngine] = None
    
    async def get_engine(self) -> AsyncEngine:
        """Get or create the async database engine."""
        if self.engine is None:
            self.engine = create_async_engine(
                self.config.async_database_url,
                echo=self.config.echo,
                pool_size=2,
                max_overflow=5,
            )
        return self.engine
    
    async def close(self) -> None:
        """Close the database engine."""
        if self.engine:
            await self.engine.dispose()
            self.engine = None
    
    async def create_all_tables(self) -> None:
        """
        Create all database tables defined in the models.
        
        This is idempotent - will not error if tables already exist.
        """
        engine = await self.get_engine()
        
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("All agent harness tables created successfully")
    
    async def drop_all_tables(self) -> None:
        """
        Drop all database tables defined in the models.
        
        WARNING: This will delete all data! Only use for testing.
        """
        engine = await self.get_engine()
        
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            logger.warning("All agent harness tables dropped")
    
    async def check_connectivity(self) -> bool:
        """
        Check if the database is accessible.
        
        Returns:
            True if connection succeeds, False otherwise
        """
        try:
            engine = await self.get_engine()
            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("Database connectivity check passed")
            return True
        except Exception as e:
            logger.error(f"Database connectivity check failed: {e}")
            return False
    
    async def tables_exist(self) -> bool:
        """
        Check if the required tables exist in the database.
        
        Returns:
            True if all tables exist, False otherwise
        """
        try:
            engine = await self.get_engine()
            async with engine.begin() as conn:
                # Get list of tables in the database
                result = await conn.execute(
                    text("""
                        SELECT table_name 
                        FROM information_schema.tables 
                        WHERE table_schema = 'public'
                    """)
                )
                existing_tables = {row[0] for row in result}
                
                # Check if all our tables exist
                required_tables = {table.name for table in Base.metadata.tables.values()}
                
                missing = required_tables - existing_tables
                if missing:
                    logger.debug(f"Missing tables: {missing}")
                    return False
                
                logger.info("All required tables exist")
                return True
        except Exception as e:
            logger.error(f"Error checking tables: {e}")
            return False


async def init_database() -> bool:
    """
    Initialize the database and create all tables.
    
    Returns:
        True if initialization succeeded, False otherwise
    """
    initializer = DatabaseInitializer()
    try:
        # Check connectivity first
        if not await initializer.check_connectivity():
            return False
        
        # Check if tables exist
        if await initializer.tables_exist():
            logger.info("Database tables already exist")
            return True
        
        # Create tables
        await initializer.create_all_tables()
        return True
    finally:
        await initializer.close()


async def drop_database() -> bool:
    """
    Drop all database tables.
    
    WARNING: This will delete all data! Only use for testing.
    
    Returns:
        True if drop succeeded, False otherwise
    """
    initializer = DatabaseInitializer()
    try:
        if not await initializer.check_connectivity():
            return False
        
        await initializer.drop_all_tables()
        return True
    finally:
        await initializer.close()


# Sync wrappers for convenience
def sync_init_database() -> bool:
    """Synchronous wrapper for init_database."""
    return asyncio.run(init_database())


def sync_drop_database() -> bool:
    """Synchronous wrapper for drop_database."""
    return asyncio.run(drop_database())


if __name__ == "__main__":
    # Command-line interface
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [database_init] %(levelname)s: %(message)s",
    )
    
    if len(sys.argv) < 2:
        print("Usage: python -m agents.database.init_db [init|drop|check]")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "init":
        success = asyncio.run(init_database())
        sys.exit(0 if success else 1)
    elif command == "drop":
        print("WARNING: This will delete all agent harness data!")
        print("Type 'yes' to confirm: ", end="")
        if input().strip().lower() == "yes":
            success = asyncio.run(drop_database())
            sys.exit(0 if success else 1)
        else:
            print("Cancelled")
            sys.exit(0)
    elif command == "check":
        initializer = DatabaseInitializer()
        try:
            connectivity = asyncio.run(initializer.check_connectivity())
            tables = asyncio.run(initializer.tables_exist())
            
            print(f"Connectivity: {'OK' if connectivity else 'FAILED'}")
            print(f"Tables: {'exist' if tables else 'missing'}")
            sys.exit(0 if (connectivity and tables) else 1)
        finally:
            asyncio.run(initializer.close())
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
