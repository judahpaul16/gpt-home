import os
from abc import ABC, abstractmethod
from typing import Optional, Any
from langchain_core.runnables import RunnableConfig
from langgraph.store.base import BaseStore
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres import AsyncPostgresStore
from langchain_litellm import ChatLiteLLM
from langmem import create_manage_memory_tool, create_search_memory_tool

# LangSmith tracing is configured via environment variables:
# - LANGCHAIN_TRACING_V2=true
# - LANGCHAIN_API_KEY=<your-api-key>
# - LANGCHAIN_PROJECT=<project-name>
# - LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
# When these are set, tracing is automatically enabled for all LangChain/LangGraph operations

from agent.config import AgentConfig
from agent.state import AgentState
from tools import get_all_tools, ToolRegistry


class BaseAgent(ABC):
    """Abstract base class for agents following Template Method pattern."""
    
    @abstractmethod
    async def invoke(self, text: str, **kwargs) -> str:
        pass
    
    @abstractmethod
    async def stream(self, text: str, **kwargs):
        pass


class GPTHomeAgent(BaseAgent):
    """Main agent implementation using Strategy pattern for tool selection."""
    
    def __init__(
        self,
        config: AgentConfig,
        checkpointer: Optional[AsyncPostgresSaver] = None,
        store: Optional[BaseStore] = None
    ):
        self.config = config
        self.checkpointer = checkpointer
        self.store = store
        self.tool_registry = ToolRegistry()
        self._agent = None
        self._initialized = False
    
    async def initialize(self):
        """Lazy initialization of the agent graph."""
        if self._initialized:
            return
        
        # Get API key from LITELLM_API_KEY
        api_key = os.getenv("LITELLM_API_KEY")
        
        # ChatLiteLLM uses the model name to determine the provider
        # Supports 100+ providers: OpenAI, Anthropic, Google, Cohere, etc.
        llm = ChatLiteLLM(
            model=self.config.model,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            api_key=api_key,
        )
        
        action_tools = get_all_tools()
        
        memory_tools = []
        if self.store:
            memory_tools = [
                create_manage_memory_tool(namespace=("memories", "{user_id}")),
                create_search_memory_tool(namespace=("memories", "{user_id}")),
            ]
        
        all_tools = action_tools + memory_tools
        
        self._agent = create_react_agent(
            llm,
            tools=all_tools,
            prompt=self._build_system_prompt,
            checkpointer=self.checkpointer,
            store=self.store,
        )
        
        self._initialized = True
    
    def _build_system_prompt(self, state: AgentState) -> list:
        """Build system prompt with memory context."""
        memories_text = ""
        
        if self.store and state.get("user_id"):
            try:
                from langgraph.utils.config import get_store
                store = get_store()
                if store:
                    memories = store.search(
                        ("memories", state["user_id"]),
                        query=state["messages"][-1].content if state["messages"] else "",
                        limit=5
                    )
                    if memories:
                        memories_text = "\n".join([
                            f"- {m.value.get('content', m.value)}" 
                            for m in memories
                        ])
            except Exception:
                pass
        
        system_content = f"""You are a helpful AI assistant for GPT Home, a smart home voice assistant.
You help users with various tasks including:
- Weather information
- Music control via Spotify
- Smart home control via Philips Hue
- Calendar and reminders via CalDAV
- General questions and conversation

{self.config.custom_instructions}

## Important Tool Usage Guidelines
- When users ask about weather without specifying a location, ALWAYS call the weather tool immediately. The tool will automatically detect their location - do NOT ask for their location first.
- When users ask to play music, call the Spotify tool directly.
- When users ask about their calendar or to set reminders, call the calendar tool directly.
- Be proactive - call tools first, ask clarifying questions only if the tool fails or returns an error.

## User Memories
<memories>
{memories_text if memories_text else "No memories stored yet."}
</memories>

When users share preferences or important information, use the memory tools to save them.
When answering questions, search your memories first for relevant context.
Be concise but helpful in your responses as they will be spoken aloud."""

        return [{"role": "system", "content": system_content}, *state["messages"]]
    
    async def invoke(self, text: str, user_id: str = "default", thread_id: str = "default", **kwargs) -> str:
        """Process user input and return response."""
        await self.initialize()
        
        config: RunnableConfig = {
            "configurable": {
                "thread_id": thread_id,
                "user_id": user_id,
            }
        }
        
        result = await self._agent.ainvoke(
            {"messages": [{"role": "user", "content": text}]},
            config=config
        )
        
        if result and result.get("messages"):
            return result["messages"][-1].content
        
        return "I'm sorry, I couldn't process that request."
    
    async def stream(self, text: str, user_id: str = "default", thread_id: str = "default", **kwargs):
        """Stream responses for real-time output."""
        await self.initialize()
        
        config: RunnableConfig = {
            "configurable": {
                "thread_id": thread_id,
                "user_id": user_id,
            }
        }
        
        async for event in self._agent.astream_events(
            {"messages": [{"role": "user", "content": text}]},
            config=config,
            version="v2"
        ):
            yield event


async def create_agent(config: Optional[AgentConfig] = None) -> GPTHomeAgent:
    """Factory function to create and initialize an agent with all dependencies."""
    if config is None:
        config = AgentConfig.from_settings()
    
    checkpointer = None
    store = None
    
    if config.database_url:
        try:
            async with AsyncPostgresSaver.from_conn_string(config.database_url) as saver:
                await saver.setup()
                checkpointer = saver
        except Exception as e:
            print(f"Warning: Could not initialize PostgreSQL checkpointer: {e}")
        
        try:
            store = AsyncPostgresStore.from_conn_string(
                config.database_url,
                index={
                    "dims": config.embedding_dims,
                    "embed": config.embedding_model,
                    "fields": ["content", "$"],
                }
            )
            await store.setup()
        except Exception as e:
            print(f"Warning: Could not initialize PostgreSQL store: {e}")
    
    agent = GPTHomeAgent(config, checkpointer, store)
    await agent.initialize()
    
    return agent
