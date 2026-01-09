from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from langchain_core.tools import Tool, tool


class ToolCommand(ABC):
    """Abstract Command pattern implementation for tools."""

    @abstractmethod
    async def execute(self, *args, **kwargs) -> Any:
        pass

    @abstractmethod
    def get_tool(self) -> Tool:
        pass


@dataclass
class ToolMetadata:
    name: str
    description: str
    category: str
    requires_api_key: bool = False
    api_key_env_var: Optional[str] = None


class ToolRegistry:
    """Registry pattern for managing tools.

    Provides centralized tool registration and retrieval.
    Supports dynamic tool loading and categorization.
    """

    _instance: Optional["ToolRegistry"] = None
    _tools: dict[str, Tool] = {}
    _metadata: dict[str, ToolMetadata] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._tools = {}
            cls._metadata = {}
        return cls._instance

    def register(self, tool: Tool, metadata: Optional[ToolMetadata] = None):
        """Register a tool with optional metadata."""
        self._tools[tool.name] = tool
        if metadata:
            self._metadata[tool.name] = metadata

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_all(self) -> List[Tool]:
        """Get all registered tools."""
        return list(self._tools.values())

    def get_by_category(self, category: str) -> List[Tool]:
        """Get tools by category."""
        return [
            self._tools[name]
            for name, meta in self._metadata.items()
            if meta.category == category
        ]

    def get_available(self) -> List[Tool]:
        """Get all registered tools."""
        return list(self._tools.values())


def get_all_tools() -> List[Tool]:
    """Get all registered tools."""
    from .alarm import alarm_tool
    from .calendar import calendar_tool
    from .lights import lights_tool
    from .spotify import spotify_tool
    from .weather import weather_tool

    registry = ToolRegistry()

    registry.register(
        weather_tool,
        ToolMetadata(
            name="weather",
            description="Get weather information",
            category="information",
            requires_api_key=False,
        ),
    )

    registry.register(
        spotify_tool,
        ToolMetadata(
            name="spotify",
            description="Control Spotify playback",
            category="entertainment",
            requires_api_key=True,
            api_key_env_var="SPOTIFY_CLIENT_ID",
        ),
    )

    registry.register(
        lights_tool,
        ToolMetadata(
            name="lights",
            description="Control Philips Hue lights",
            category="smart_home",
            requires_api_key=True,
            api_key_env_var="PHILIPS_HUE_BRIDGE_IP",
        ),
    )

    registry.register(
        calendar_tool,
        ToolMetadata(
            name="calendar",
            description="Manage calendar events and tasks",
            category="productivity",
            requires_api_key=True,
            api_key_env_var="CALDAV_URL",
        ),
    )

    registry.register(
        alarm_tool,
        ToolMetadata(
            name="alarm",
            description="Set alarms and reminders",
            category="productivity",
            requires_api_key=False,
        ),
    )

    available = registry.get_available()
    print(f"[TOOLS] Available tools: {[t.name for t in available]}", flush=True)
    return available
