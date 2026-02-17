import logging
import os
from typing import Any, Optional

from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore
from langgraph.store.postgres import AsyncPostgresStore

logger = logging.getLogger("memory.store")


async def create_memory_store(
    database_url: Optional[str] = None,
    embedding_model: str = "openai:text-embedding-3-small",
    embedding_dims: int = 1536,
) -> BaseStore:
    """Factory function to create appropriate memory store.

    Uses Strategy pattern to select between PostgreSQL and in-memory storage.

    Args:
        database_url: PostgreSQL connection string. If None, uses in-memory store.
        embedding_model: Model for semantic search embeddings.
        embedding_dims: Dimensions of embedding vectors.

    Returns:
        Configured BaseStore instance.
    """
    if database_url is None:
        database_url = os.getenv("DATABASE_URL")

    index_config = {
        "dims": embedding_dims,
        "embed": embedding_model,
        "fields": ["content", "summary", "$"],
    }

    if database_url:
        try:
            store = AsyncPostgresStore.from_conn_string(
                database_url, index=index_config
            )
            await store.setup()
            return store
        except Exception as e:
            logger.warning(
                "PostgreSQL store initialization failed: %s, falling back to in-memory store",
                e,
            )

    return InMemoryStore(index=index_config)
