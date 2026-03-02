"""
GPT Home Action Router

This module provides the main interface for routing user requests to the appropriate
LangGraph agent with persistent memory capabilities.

Design Patterns Used:
- Singleton: For the global agent instance
- Factory: For agent creation
- Strategy: For tool selection based on intent
- Facade: For simplified external API
"""

import asyncio
import os
import re
from asyncio import TimeoutError as AsyncTimeoutError
from typing import Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from src.agent import AgentConfig, GPTHomeAgent
from src.common import load_integration_statuses, logger
from src.memory import MemoryManager

# LangGraph store uses OpenAI SDK directly for embeddings, not LiteLLM
# Set OPENAI_API_KEY from LITELLM_API_KEY at module load time
_litellm_key = os.getenv("LITELLM_API_KEY", "")
_embedding_model = os.getenv("EMBEDDING_MODEL", "openai:text-embedding-3-small")
if _litellm_key and _embedding_model.startswith("openai:"):
    os.environ["OPENAI_API_KEY"] = _litellm_key
    logger.debug("Set OPENAI_API_KEY from LITELLM_API_KEY for embeddings")

_agent_instance: Optional[GPTHomeAgent] = None
_memory_manager: Optional[MemoryManager] = None
_checkpointer = None
_store = None
_connection_pool = None


def _load_settings() -> dict:
    from src.common import load_settings
    return load_settings()


async def _close_persistence():
    """Close database connections for reconnection."""
    global _checkpointer, _store, _connection_pool

    try:
        if _connection_pool is not None:
            await _connection_pool.close()
            logger.info("PostgreSQL connection pool closed for reconnection")
    except Exception:
        pass

    _checkpointer = None
    _store = None
    _connection_pool = None


async def _initialize_persistence():
    """Initialize database connections for checkpointing and memory store."""
    global _checkpointer, _store, _connection_pool

    database_url = os.getenv("DATABASE_URL")

    # Embedding configuration - uses LangChain format with provider prefix
    # Format: 'provider:model-name' e.g., 'openai:text-embedding-3-small'
    embedding_model = os.getenv("EMBEDDING_MODEL", "openai:text-embedding-3-small")
    embedding_dims = int(os.getenv("EMBEDDING_DIMS", "1536"))

    if database_url:
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            from langgraph.store.postgres import AsyncPostgresStore, PoolConfig
            from psycopg_pool import AsyncConnectionPool

            # Create a connection pool that stays open for the app lifetime
            _connection_pool = AsyncConnectionPool(
                conninfo=database_url,
                open=False,  # We'll open it manually
                kwargs={"autocommit": True, "prepare_threshold": 0},
            )
            await _connection_pool.open()
            logger.info("PostgreSQL connection pool opened")

            # Create checkpointer with the pool (not context manager)
            _checkpointer = AsyncPostgresSaver(conn=_connection_pool)
            await _checkpointer.setup()
            logger.info("PostgreSQL checkpointer initialized")

            # Create store with pool_config to avoid context manager
            # Use the context manager properly - enter it and keep reference
            store_cm = AsyncPostgresStore.from_conn_string(
                database_url,
                pool_config=PoolConfig(min_size=1, max_size=10),
                index={
                    "dims": embedding_dims,
                    "embed": embedding_model,
                    "fields": ["content", "summary", "$"],
                },
            )
            _store = await store_cm.__aenter__()
            await _store.setup()
            logger.info("PostgreSQL memory store initialized")
        except Exception as e:
            logger.warning(f"PostgreSQL unavailable, using in-memory storage: {e}")
            _checkpointer = MemorySaver()
            _store = InMemoryStore(
                index={
                    "dims": embedding_dims,
                    "embed": embedding_model,
                }
            )
    else:
        logger.info("No DATABASE_URL configured, using in-memory storage")
        _checkpointer = MemorySaver()
        _store = InMemoryStore(
            index={
                "dims": embedding_dims,
                "embed": embedding_model,
            }
        )


async def _get_agent() -> GPTHomeAgent:
    """Get or create the singleton agent instance."""
    global _agent_instance, _checkpointer, _store

    if _agent_instance is None:
        if _checkpointer is None or _store is None:
            await _initialize_persistence()

        config = AgentConfig.from_settings()
        statuses = await load_integration_statuses()

        _agent_instance = GPTHomeAgent(
            config=config, checkpointer=_checkpointer, store=_store
        )
        await _agent_instance.initialize()
        logger.info("GPT Home agent initialized")

    return _agent_instance


async def _get_memory_manager() -> MemoryManager:
    """Get or create the memory manager instance."""
    global _memory_manager, _store

    if _memory_manager is None:
        if _store is None:
            await _initialize_persistence()

        settings = _load_settings()
        model = settings.get("model", "gpt-4o-mini")

        _memory_manager = MemoryManager(store=_store, model=model)

    return _memory_manager


def _is_pool_error(error: Exception) -> bool:
    """Check if error is a database pool/connection error that warrants reconnection."""
    error_str = str(error).lower()
    return any(
        pattern in error_str
        for pattern in [
            "pool",
            "closed",
            "connection",
            "disconnect",
            "terminated",
            "server closed",
        ]
    )


def _is_chat_history_error(error: Exception) -> bool:
    error_str = str(error)
    return "INVALID_CHAT_HISTORY" in error_str or "ToolMessage" in error_str


async def _clear_thread_checkpoints(thread_id: str) -> None:
    if not _connection_pool:
        return
    try:
        async with _connection_pool.connection() as conn:
            for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                await conn.execute(
                    f"DELETE FROM {table} WHERE thread_id = %s", (thread_id,)
                )
        logger.info("Cleared corrupted checkpoints for thread %s", thread_id)
    except Exception as ex:
        logger.warning("Failed to clear checkpoints for %s: %s", thread_id, ex)


async def action_router(
    text: str, user_id: str = "default", thread_id: Optional[str] = None
) -> str:
    """
    Main entry point for processing user requests.

    Routes the text through the LangGraph agent which will:
    1. Search relevant memories for context
    2. Determine the appropriate tool(s) to use
    3. Execute the action
    4. Optionally save new memories
    5. Return the response

    Args:
        text: User's input text
        user_id: Unique identifier for the user (for memory namespacing)
        thread_id: Conversation thread ID (for checkpoint persistence)

    Returns:
        Agent's response string
    """
    global _agent_instance, _checkpointer, _store, _connection_pool

    if thread_id is None:
        thread_id = f"session_{user_id}"

    max_retries = 2

    for attempt in range(max_retries):
        try:
            agent = await _get_agent()
            statuses = await load_integration_statuses()
            response = await asyncio.wait_for(
                agent.invoke(
                    text=text,
                    user_id=user_id,
                    thread_id=thread_id,
                    service_status=statuses,
                ),
                timeout=60.0,
            )

            asyncio.create_task(_background_memory_processing(text, response, user_id))

            return response

        except AsyncTimeoutError:
            logger.error(f"[action_router] Agent invoke timed out after 60s")
            return "I'm sorry, the request took too long. Please try again."

        except Exception as e:
            logger.error(f"Error in action_router (attempt {attempt + 1}): {e}")

            # Handle pool/connection errors by attempting reconnection
            if _is_pool_error(e) and attempt < max_retries - 1:
                logger.info("Pool error detected, attempting to reconnect...")
                try:
                    await _close_persistence()
                    _agent_instance = None
                    await _initialize_persistence()
                    logger.info("Reconnection successful, retrying request...")
                    continue
                except Exception as reconnect_error:
                    logger.error(f"Reconnection failed: {reconnect_error}")

            if _is_chat_history_error(e) and attempt < max_retries - 1:
                logger.info("Chat history error detected, clearing corrupted thread %s", thread_id)
                await _clear_thread_checkpoints(thread_id)
                continue

            # Return friendly error message
            return f"{e}"

    return "I'm having trouble processing that request. Please try again."


async def _background_memory_processing(user_input: str, response: str, user_id: str):
    """Background task to extract and store memories from the conversation."""
    try:
        memory_manager = await _get_memory_manager()
        messages = [
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": response},
        ]
        await memory_manager.process_conversation_background(messages, user_id)
    except Exception:
        pass


async def search_memories(query: str, user_id: str = "default", limit: int = 5) -> list:
    """Search user memories for relevant context."""
    try:
        memory_manager = await _get_memory_manager()
        return await memory_manager.search_memories(query, user_id, limit=limit)
    except Exception as e:
        logger.error(f"Memory search failed: {e}")
        return []


async def add_memory(content: str, user_id: str = "default") -> str:
    """Manually add a memory for a user."""
    try:
        memory_manager = await _get_memory_manager()
        return await memory_manager.add_semantic_memory(content, user_id)
    except Exception as e:
        logger.error(f"Failed to add memory: {e}")
        return ""


async def get_user_profile(user_id: str = "default") -> dict:
    """Get the user's profile information."""
    try:
        memory_manager = await _get_memory_manager()
        return await memory_manager.get_user_profile(user_id)
    except Exception as e:
        logger.error(f"Failed to get user profile: {e}")
        return {}


async def clear_user_memories(user_id: str = "default"):
    """Clear all memories for a user."""
    try:
        memory_manager = await _get_memory_manager()
        await memory_manager.clear_memories(user_id)
    except Exception as e:
        logger.error(f"Failed to clear memories: {e}")


def reset_agent():
    """Reset the agent instance (useful for testing or config changes)."""
    global _agent_instance, _memory_manager
    _agent_instance = None
    _memory_manager = None
