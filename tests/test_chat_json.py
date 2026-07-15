"""
Tests for LLM Provider base class and chat_json retry logic.
"""

from typing import List
from pydantic import BaseModel
import pytest

from providers.base import Provider, GenerationError


class DummySchema(BaseModel):
    items: List[str]


class FakeRetryProvider(Provider):
    """Simulates a provider that fails validation once, then succeeds on retry."""

    def __init__(self):
        self.calls = 0

    @property
    def name(self) -> str:
        return "fake_retry"

    def is_available(self) -> bool:
        return True

    def chat(self, prompt: str, *, max_tokens: int = 8000,
             temperature: float = 0.2, system: str | None = None) -> str:
        self.calls += 1
        if self.calls == 1:
            # Return invalid schema (items field missing)
            return '{"names": ["apple", "orange"]}'
        else:
            # Return valid schema
            return '{"items": ["apple", "orange"]}'


def test_chat_json_validation_retry():
    provider = FakeRetryProvider()
    
    # Trigger structured validation check
    res = provider.chat_json("Get fruit list", DummySchema)
    
    # Should complete successfully after retrying once
    assert res.items == ["apple", "orange"]
    assert provider.calls == 2


class FakeFailureProvider(Provider):
    """Simulates a provider that consistently fails to return valid schema."""
    
    def __init__(self):
        self.calls = 0

    @property
    def name(self) -> str:
        return "fake_fail"

    def is_available(self) -> bool:
        return True

    def chat(self, prompt: str, *, max_tokens: int = 8000,
             temperature: float = 0.2, system: str | None = None) -> str:
        self.calls += 1
        return '{"bad_json": True}'  # Syntax error and wrong schema


def test_chat_json_max_attempts_exhausted():
    provider = FakeFailureProvider()
    
    # Should raise GenerationError after 2 failed attempts
    with pytest.raises(GenerationError):
        provider.chat_json("Get fruit list", DummySchema)
        
    assert provider.calls == 2
