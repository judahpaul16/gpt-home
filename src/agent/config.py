from dataclasses import dataclass, field
from typing import Optional
import os
import json
from pathlib import Path


@dataclass
class AgentConfig:
    """Configuration for the GPT Home agent using Builder pattern."""
    
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 1024
    custom_instructions: str = ""
    embedding_model: str = "openai:text-embedding-3-small"
    embedding_dims: int = 1536
    database_url: Optional[str] = None
    
    @classmethod
    def from_settings(cls, settings_path: Optional[Path] = None) -> "AgentConfig":
        """Factory method to create config from settings file."""
        if settings_path is None:
            settings_path = Path(__file__).parent.parent / "settings.json"
        
        config_data = {}
        if settings_path.exists():
            with open(settings_path, "r") as f:
                settings = json.load(f)
                config_data = {
                    "model": os.getenv("MODEL") or settings.get("model", "gpt-4o-mini"),
                    "temperature": settings.get("temperature", 0.7),
                    "max_tokens": settings.get("max_tokens", 1024),
                    "custom_instructions": settings.get("custom_instructions", ""),
                }
        
        config_data["database_url"] = os.getenv(
            "DATABASE_URL",
            "postgresql://gpt_home:gpt_home_secret@localhost:5432/gpt_home"
        )
        
        return cls(**config_data)
    
    @classmethod
    def builder(cls) -> "AgentConfigBuilder":
        """Returns a builder for fluent configuration."""
        return AgentConfigBuilder()


class AgentConfigBuilder:
    """Builder pattern implementation for AgentConfig."""
    
    def __init__(self):
        self._config = {}
    
    def with_model(self, model: str) -> "AgentConfigBuilder":
        self._config["model"] = model
        return self
    
    def with_temperature(self, temperature: float) -> "AgentConfigBuilder":
        self._config["temperature"] = temperature
        return self
    
    def with_max_tokens(self, max_tokens: int) -> "AgentConfigBuilder":
        self._config["max_tokens"] = max_tokens
        return self
    
    def with_custom_instructions(self, instructions: str) -> "AgentConfigBuilder":
        self._config["custom_instructions"] = instructions
        return self
    
    def with_database_url(self, url: str) -> "AgentConfigBuilder":
        self._config["database_url"] = url
        return self
    
    def with_embedding(self, model: str, dims: int) -> "AgentConfigBuilder":
        self._config["embedding_model"] = model
        self._config["embedding_dims"] = dims
        return self
    
    def build(self) -> AgentConfig:
        return AgentConfig(**self._config)
