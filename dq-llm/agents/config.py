"""
Agent Configuration Management for DQ-RuleBuilder Pi Agent Harness.

This module provides configuration management for the agent harness, integrating
with the existing dq-llm environment variable setup and adding agent-specific
settings.

Environment Variables:
- DQ_LLM_MODEL_ID: LLM model identifier (default: Qwen/Qwen2.5-7B-Instruct)
- DQ_LLM_DEVICE_MAP: Device mapping for model loading (default: auto)
- DQ_LLM_MAX_NEW_TOKENS: Maximum tokens to generate (default: 512)
- DQ_LLM_CHAT_PROVIDER: LLM provider (default: huggingface)
- DQ_AGENT_WORKSPACE: Working directory for agent sessions (default: /tmp/dq-agent)
- DQ_AGENT_SESSION_TIMEOUT_SECONDS: Session timeout in seconds (default: 3600)
- DQ_AGENT_MAX_TOOL_CALLS_PER_SESSION: Maximum tool calls per session (default: 100)
- DQ_AGENT_AUDIT_ENABLED: Enable audit logging (default: true)
    - DQ_AGENT_API_BASE_URL: Base URL for DQ API calls (default: https://kong:8443)
"""

import os
from pathlib import Path
from typing import Callable, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DQAgentConfig(BaseSettings):
    """
    Configuration for DQ Agent Harness.
    
    Inherits LLM configuration from the existing dq-llm setup and adds
    agent-specific settings.
    """
    
    # LLM Configuration (inherited from existing dq-llm setup)
    llm_model_id: str = Field(
        default="Qwen/Qwen2.5-7B-Instruct",
        description="LLM model identifier for agent inference"
    )
    llm_device_map: str = Field(
        default="auto",
        description="Device mapping for model loading"
    )
    llm_max_new_tokens: int = Field(
        default=512,
        ge=1,
        le=8192,
        description="Maximum new tokens to generate per response"
    )
    llm_chat_provider: str = Field(
        default="huggingface",
        description="LLM provider: huggingface, openai, anthropic, grok, ollama"
    )
    
    # Agent Configuration
    agent_workspace: Path = Field(
        default=Path("/tmp/dq-agent"),
        description="Working directory for agent session files and state"
    )
    session_timeout_seconds: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description="Maximum session lifetime in seconds (default: 1 hour)"
    )
    max_tool_calls_per_session: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum number of tool calls allowed per session"
    )
    audit_enabled: bool = Field(
        default=True,
        description="Enable audit logging for agent operations"
    )
    
    # API Configuration
    api_base_url: str = Field(
        default="https://kong:8443",
        description="Base URL for DQ API endpoints"
    )
    api_key: Optional[str] = Field(
        default=None,
        description="API key for authenticating with DQ API (prefer DQ_AGENT_API_KEY_FILE env var)"
    )
    api_key_file: Optional[Path] = Field(
        default=None,
        description="Path to file containing API key (more secure than API_KEY)"
    )
    
    # Security
    allowed_tool_directories: list[Path] = Field(
        default_factory=lambda: [Path("/tmp/dq-agent"), Path("/workspace/agent")],
        description="Directories where file tools are allowed to read/write"
    )
    forbidden_tool_patterns: list[str] = Field(
        default_factory=lambda: [
            "rm",
            "kill",
            "shutdown",
            "reboot",
            ":(){ :; };",  # Bash fork bomb
            "> /dev/",
            "mv / "
        ],
        description="Command patterns that are forbidden in bash tool"
    )
    prompt_injection_patterns: list[str] = Field(
        default_factory=lambda: [
            "ignore previous instructions",
            "ignore all previous instructions",
            "system prompt",
            "developer prompt",
            "reveal your hidden instructions",
            "pretend you are",
            "bypass the safety",
            "disregard the above",
            "you are now",
            "forget the rules",
            "override the system",
        ],
        description="Common prompt-injection phrases that should be blocked before tool execution"
    )
    
    # Model Configuration
    model_config = SettingsConfigDict(
        env_file=".env.agent.local",
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="__",
        case_sensitive=False,
    )
    
    def get_api_key(self) -> Optional[str]:
        """
        Get the API key, loading from file if needed.
        
        Priority:
        1. Explicit api_key field
        2. api_key_file field (read from file)
        3. DQ_AGENT_API_KEY_FILE environment variable (read from file)
        4. Default: None
        """
        # 1. Check explicit api_key
        if self.api_key:
            return self.api_key
        
        # 2. Check api_key_file field
        if self.api_key_file and self.api_key_file.exists():
            try:
                with open(self.api_key_file, 'r') as f:
                    return f.read().strip()
            except (IOError, OSError):
                pass
        
        # 3. Check environment variable
        env_key_file = os.environ.get('DQ_AGENT_API_KEY_FILE')
        if env_key_file:
            key_file_path = Path(env_key_file)
            if key_file_path.exists():
                try:
                    with open(key_file_path, 'r') as f:
                        return f.read().strip()
                except (IOError, OSError):
                    pass
        
        return None

    def get_api_key_provider(self, api_key: Optional[str] = None) -> Callable[[], Optional[str]]:
        """Return a callable that resolves the current API key on demand."""
        if api_key is not None and str(api_key).strip():
            normalized_api_key = str(api_key).strip()
            return lambda: normalized_api_key

        return self.get_api_key
    
    @property
    def effective_api_key(self) -> Optional[str]:
        """Get the API key, preferring explicit value over file-based."""
        return self.get_api_key()
    
    @property
    def is_ollama_provider(self) -> bool:
        """Check if using Ollama provider."""
        return self.llm_chat_provider.lower() == "ollama"
    
    @property
    def is_huggingface_provider(self) -> bool:
        """Check if using HuggingFace provider."""
        return self.llm_chat_provider.lower() == "huggingface"
    
    def get_workspace_path(self) -> Path:
        """Get and ensure the workspace directory exists."""
        self.agent_workspace.mkdir(parents=True, exist_ok=True)
        return self.agent_workspace
    
    def to_dict(self, include_secrets: bool = False) -> dict:
        """
        Convert configuration to dictionary.
        
        Args:
            include_secrets: If False, redact sensitive values
        """
        data = self.model_dump()
        
        if not include_secrets:
            # Redact sensitive fields
            data['api_key'] = '***REDACTED***' if data.get('api_key') else None
            if 'api_key_file' in data:
                data['api_key_file'] = '***REDACTED***' if data.get('api_key_file') else None
        
        # Convert Path objects to strings
        for key, value in data.items():
            if isinstance(value, Path):
                data[key] = str(value)
            elif isinstance(value, list) and all(isinstance(x, Path) for x in value):
                data[key] = [str(x) for x in value]
        
        return data


# Global configuration instance (lazy loaded)
_agent_config: Optional[DQAgentConfig] = None


def get_agent_config() -> DQAgentConfig:
    """
    Get the global agent configuration instance.
    
    The configuration is loaded once and cached. Use reset_agent_config()
    to reload from environment.
    
    Returns:
        DQAgentConfig: The loaded configuration
    """
    global _agent_config
    if _agent_config is None:
        _agent_config = DQAgentConfig()
    return _agent_config


def reset_agent_config() -> DQAgentConfig:
    """
    Reset and reload the global agent configuration.
    
    Useful for testing or when environment variables change.
    
    Returns:
        DQAgentConfig: The newly loaded configuration
    """
    global _agent_config
    _agent_config = DQAgentConfig()
    return _agent_config


def get_agent_config_dict(include_secrets: bool = False) -> dict:
    """
    Get the agent configuration as a dictionary.
    
    Args:
        include_secrets: If False, sensitive values are redacted
    
    Returns:
        dict: Configuration as dictionary
    """
    return get_agent_config().to_dict(include_secrets=include_secrets)
