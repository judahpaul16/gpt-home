from enum import Enum, auto
from typing import Optional, Any, List
from dataclasses import dataclass
from datetime import datetime
import uuid

from langgraph.store.base import BaseStore
from langmem import create_memory_manager, create_memory_store_manager


class MemoryType(Enum):
    """Types of memories following LangMem's conceptual model."""
    SEMANTIC = auto()    # Facts and knowledge (user preferences, learned information)
    EPISODIC = auto()    # Past experiences (conversation summaries, interactions)
    PROCEDURAL = auto()  # System behavior (optimized prompts, learned patterns)


@dataclass
class Memory:
    """Data class representing a single memory entry."""
    id: str
    content: Any
    memory_type: MemoryType
    namespace: tuple
    created_at: datetime
    updated_at: datetime
    metadata: dict
    
    @classmethod
    def create(
        cls,
        content: Any,
        memory_type: MemoryType,
        namespace: tuple,
        metadata: Optional[dict] = None
    ) -> "Memory":
        now = datetime.utcnow()
        return cls(
            id=str(uuid.uuid4()),
            content=content,
            memory_type=memory_type,
            namespace=namespace,
            created_at=now,
            updated_at=now,
            metadata=metadata or {}
        )


class MemoryManager:
    """Manages agent memories using the Facade pattern.
    
    Provides a unified interface for:
    - Semantic memories (user preferences, facts)
    - Episodic memories (conversation history)
    - Procedural memories (learned behaviors)
    
    Supports both hot-path (immediate) and background (async) memory formation.
    """
    
    def __init__(
        self,
        store: BaseStore,
        model: str = "gpt-4o-mini",
        user_id: str = "default"
    ):
        self.store = store
        self.model = model
        self.user_id = user_id
        
        self._semantic_manager = create_memory_store_manager(
            model,
            store=store,
            namespace=("memories", "{user_id}", "semantic"),
            instructions="""Extract and manage semantic memories about the user.
Focus on:
- Personal preferences (display mode, communication style, etc.)
- Important facts shared by the user
- Recurring topics of interest
Consolidate related memories to avoid redundancy."""
        )
        
        self._episodic_manager = create_memory_store_manager(
            model,
            store=store,
            namespace=("memories", "{user_id}", "episodic"),
            instructions="""Extract episodic memories from conversations.
Focus on:
- Successful interaction patterns
- Notable events or requests
- Context that might be relevant for future interactions"""
        )
    
    async def add_semantic_memory(
        self,
        content: str,
        user_id: Optional[str] = None
    ) -> str:
        """Add a semantic (factual) memory."""
        uid = user_id or self.user_id
        namespace = ("memories", uid, "semantic")
        memory_id = str(uuid.uuid4())
        
        await self.store.aput(
            namespace,
            memory_id,
            {"content": content, "type": "semantic"},
            index=["content"]
        )
        
        return memory_id
    
    async def add_episodic_memory(
        self,
        summary: str,
        context: dict,
        user_id: Optional[str] = None
    ) -> str:
        """Add an episodic (experience) memory."""
        uid = user_id or self.user_id
        namespace = ("memories", uid, "episodic")
        memory_id = str(uuid.uuid4())
        
        await self.store.aput(
            namespace,
            memory_id,
            {"summary": summary, "context": context, "type": "episodic"},
            index=["summary"]
        )
        
        return memory_id
    
    async def search_memories(
        self,
        query: str,
        user_id: Optional[str] = None,
        memory_type: Optional[MemoryType] = None,
        limit: int = 5
    ) -> List[dict]:
        """Search memories using semantic similarity."""
        uid = user_id or self.user_id
        
        if memory_type:
            type_name = memory_type.name.lower()
            namespace = ("memories", uid, type_name)
            results = await self.store.asearch(namespace, query=query, limit=limit)
        else:
            all_results = []
            for mem_type in ["semantic", "episodic"]:
                namespace = ("memories", uid, mem_type)
                try:
                    results = await self.store.asearch(namespace, query=query, limit=limit)
                    all_results.extend(results)
                except Exception:
                    continue
            results = sorted(all_results, key=lambda x: x.score if hasattr(x, 'score') else 0, reverse=True)[:limit]
        
        return [{"id": r.key, "value": r.value, "namespace": r.namespace} for r in results]
    
    async def get_user_profile(self, user_id: Optional[str] = None) -> dict:
        """Get consolidated user profile from semantic memories."""
        uid = user_id or self.user_id
        namespace = ("profiles", uid)
        
        try:
            profile = await self.store.aget(namespace, "profile")
            return profile.value if profile else {}
        except Exception:
            return {}
    
    async def update_user_profile(
        self,
        updates: dict,
        user_id: Optional[str] = None
    ):
        """Update user profile with new information."""
        uid = user_id or self.user_id
        namespace = ("profiles", uid)
        
        current = await self.get_user_profile(uid)
        current.update(updates)
        
        await self.store.aput(namespace, "profile", current)
    
    async def process_conversation_background(
        self,
        messages: List[dict],
        user_id: Optional[str] = None
    ):
        """Background processing to extract memories from conversations.
        
        This implements the "subconscious" memory formation pattern from LangMem.
        """
        uid = user_id or self.user_id
        config = {"configurable": {"user_id": uid}}
        
        await self._semantic_manager.ainvoke({"messages": messages}, config=config)
        await self._episodic_manager.ainvoke({"messages": messages}, config=config)
    
    async def clear_memories(self, user_id: Optional[str] = None):
        """Clear all memories for a user."""
        uid = user_id or self.user_id
        
        for mem_type in ["semantic", "episodic"]:
            namespace = ("memories", uid, mem_type)
            try:
                items = await self.store.asearch(namespace, query="", limit=1000)
                for item in items:
                    await self.store.adelete(namespace, item.key)
            except Exception:
                continue
