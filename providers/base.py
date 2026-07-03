"""
Provider base layer for the Documentation Automation Bot.

Defines the abstract interface that every LLM provider must implement,
plus a small helper for loading prompt templates from disk.
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class RegionForLabeling:
    role: str
    candidate_labels: List[str]


@dataclass
class FieldForDescribing:
    name: str
    type: str
    required: bool
    placeholder: str = None
    validation: str = None


def load_prompt(template_name: str, **kwargs: Any) -> str:
    """
    Load a prompt template from ``providers/prompts/`` and substitute
    placeholders.

    Args:
        template_name: File name without extension (e.g. ``label_regions``).
        **kwargs: String placeholders to replace in the template.

    Returns:
        The fully populated prompt string.

    Raises:
        FileNotFoundError: If the requested template does not exist.
    """
    prompts_dir = Path(__file__).parent / "prompts"
    template_path = prompts_dir / f"{template_name}.txt"

    if not template_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {template_path}")

    text = template_path.read_text(encoding="utf-8")

    if kwargs:
        for k, v in kwargs.items():
            text = text.replace(f"{{{k}}}", str(v))

    return text


class Provider(ABC):
    """
    Abstract interface for all LLM-assisted generation backends.

    Concrete implementations include:
    - BrowserProvider (copy-paste to claude.ai)
    - AnthropicProvider (native API)
    - OpenAICompatProvider (Groq, Together AI, etc.)
    - OllamaProvider (local / remote Ollama endpoint)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """
        Return ``True`` if the provider is configured and ready to use.

        For API providers this usually means an API key is present.
        For browser mode this is always ``True``.
        """
        ...

    def generate_labels(
        self, regions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Accepts detected regions and returns them with a ``label`` key added."""
        prompt = load_prompt(
            "label_regions",
            regions_json=self._to_json(regions),
        )
        from llm_ui import request_llm_processing
        from config import get_config
        cfg = get_config()
        
        result = request_llm_processing(prompt, default_provider=cfg.provider, is_json=True)
        if result is None:
            raise KeyboardInterrupt("User cancelled or aborted the prompt review.")
            
        merged_regions = []
        for i, item in enumerate(regions):
            merged = dict(item)
            if i < len(result):
                entry = result[i]
                if isinstance(entry, dict):
                    merged["label"] = entry.get("label", "")
                else:
                    merged["label"] = str(entry)
            else:
                merged["label"] = ""
            merged_regions.append(merged)
        return merged_regions

    def generate_field_descriptions(
        self, fields: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Accepts form fields and returns them with a ``description`` key added."""
        prompt = load_prompt(
            "describe_fields",
            fields_json=self._to_json(fields),
        )
        from llm_ui import request_llm_processing
        from config import get_config
        cfg = get_config()
        
        result = request_llm_processing(prompt, default_provider=cfg.provider, is_json=True)
        if result is None:
            raise KeyboardInterrupt("User cancelled or aborted the prompt review.")
            
        merged_fields = []
        for i, item in enumerate(fields):
            merged = dict(item)
            if i < len(result):
                entry = result[i]
                if isinstance(entry, dict):
                    merged["description"] = entry.get("description", "")
                else:
                    merged["description"] = str(entry)
            else:
                merged["description"] = ""
            merged_fields.append(merged)
        return merged_fields

    def generate_procedure_prose(self, screens: List[Dict[str, Any]]) -> str:
        """Accepts a sequence of screen metadata and returns procedure prose."""
        prompt = load_prompt(
            "procedure_prose",
            screens_json=self._to_json(screens),
        )
        from llm_ui import request_llm_processing
        from config import get_config
        cfg = get_config()
        
        result = request_llm_processing(prompt, default_provider=cfg.provider, is_json=False)
        if result is None:
            raise KeyboardInterrupt("User cancelled or aborted the prompt review.")
            
        return result

    @staticmethod
    def _to_json(data: Any) -> str:
        """Helper: pretty-print a Python object as compact JSON."""
        return json.dumps(data, indent=2, ensure_ascii=False)

    def label_regions(self, regions: List[RegionForLabeling]) -> List[str]:
        raw_regions = []
        for r in regions:
            raw_regions.append({
                "role": r.role,
                "elements_contained": r.candidate_labels
            })
        labeled_regions = self.generate_labels(raw_regions)
        return [r.get("label", "") for r in labeled_regions]

    def describe_fields(self, fields: List[FieldForDescribing]) -> List[str]:
        raw_fields = []
        for f in fields:
            raw_fields.append({
                "accessible_name": f.name,
                "type": f.type,
                "required": f.required,
                "placeholder": f.placeholder,
                "pattern": f.validation
            })
        described_fields = self.generate_field_descriptions(raw_fields)
        return [f.get("description", "") for f in described_fields]

    def procedure_prose(self, actions: List[Dict[str, Any]], context: str) -> str:
        screens = [{
            "context": context,
            "actions": actions
        }]
        return self.generate_procedure_prose(screens)


LLMProvider = Provider