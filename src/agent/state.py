from typing import TypedDict, Annotated, Sequence
from langgraph.graph import MessagesState
from langchain_core.messages import BaseMessage
from operator import add


class AgentState(MessagesState):
    """State schema for the GPT Home agent.
    
    Extends MessagesState with additional fields for memory and context.
    Uses reducer pattern for message accumulation.
    """
    user_id: str
    thread_id: str
    memories: Annotated[list[dict], add]
    context: dict
