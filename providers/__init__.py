"""
LLM Provider abstraction layer.
"""

from .base import Provider, load_prompt
from .browser import BrowserProvider
from .ollama import OllamaProvider
from .openai_compat import OpenAICompatProvider
from .anthropic_api import AnthropicProvider

__all__ = [
    "Provider",
    "load_prompt",
    "BrowserProvider",
    "OllamaProvider",
    "OpenAICompatProvider",
    "AnthropicProvider",
]