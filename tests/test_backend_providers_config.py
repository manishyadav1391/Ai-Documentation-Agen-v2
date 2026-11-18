"""
Backend regression tests: config.yaml robustness, provider availability for
local keyless endpoints, the browser provider, and the screen failure note.
"""

import importlib
import io
import sys

import pytest

import config as config_mod
from config import Config, load_config


# --- Item 16: hand-edited config.yaml --------------------------------------

@pytest.mark.parametrize("text", ["- a\n- b\n", "provider: [\n", "just a string\n"])
def test_backend_config_bad_yaml_falls_back_to_defaults(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    cfg = load_config(path)
    assert cfg.provider == Config().provider
    assert (tmp_path / "config.yaml.invalid").exists()


@pytest.mark.parametrize("value,expected", [
    ("openai", "openai_compat"), ("Browser", "browser"), ("OpenRouter", "openrouter"),
    ("nonsense", "browser"),
])
def test_backend_config_provider_aliases(tmp_path, value, expected):
    path = tmp_path / "config.yaml"
    path.write_text(f"provider: {value}\ncurrent_client: demo\n", encoding="utf-8")
    cfg = load_config(path)
    assert cfg.provider == expected
    assert cfg.current_client == "demo"


def test_backend_config_invalid_value_keeps_other_keys(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("providers: null\ncurrent_client: demo\n", encoding="utf-8")
    cfg = load_config(path)
    assert cfg.current_client == "demo"
    assert cfg.providers.openrouter.max_tokens == 8000


# --- Item 17: local keyless endpoints are available --------------------------

def _patch_config(monkeypatch, cfg):
    monkeypatch.setattr(Config, "get_api_key", lambda self, p=None: None)
    monkeypatch.setattr(config_mod, "_config_instance", cfg)


@pytest.mark.parametrize("host,ok", [
    ("http://localhost:11434", True), ("http://127.0.0.1:11434", True),
    ("http://192.168.1.20:11434", True), ("https://ollama.com", False),
])
def test_backend_ollama_local_needs_no_key(monkeypatch, host, ok):
    cfg = Config()
    cfg.providers.ollama.host = host
    _patch_config(monkeypatch, cfg)
    from providers.ollama import OllamaProvider
    assert OllamaProvider().is_available() is ok


@pytest.mark.parametrize("url,ok", [
    ("http://localhost:1234/v1", True), ("https://api.groq.com/openai/v1", False),
])
def test_backend_openai_compat_local_needs_no_key(monkeypatch, url, ok):
    cfg = Config()
    cfg.providers.openai_compat.base_url = url
    _patch_config(monkeypatch, cfg)
    from providers.openai_compat import OpenAICompatProvider
    assert OpenAICompatProvider().is_available() is ok


# --- Item 14: browser provider ------------------------------------------------

def test_backend_browser_provider_without_console_raises(monkeypatch, tmp_path):
    _patch_config(monkeypatch, Config())
    from providers.browser import BrowserProvider
    monkeypatch.setattr(sys, "stdin", None)
    calls = []
    monkeypatch.setattr("builtins.input", lambda *a: calls.append(a) or "")
    with pytest.raises(RuntimeError, match="console"):
        BrowserProvider(work_dir=tmp_path).chat("prompt")
    assert calls == []


def test_backend_browser_provider_deletes_stale_response(monkeypatch, tmp_path):
    _patch_config(monkeypatch, Config())
    import providers.browser as browser
    (tmp_path / "llm_response.txt").write_text("previous screen", encoding="utf-8")
    monkeypatch.setattr(browser, "_has_console", lambda: True)
    monkeypatch.setattr(browser.subprocess, "Popen", lambda *a, **k: None)

    def fake_input(prompt=""):
        # The stale file must be gone by the time the user is asked
        assert not (tmp_path / "llm_response.txt").exists()
        (tmp_path / "llm_response.txt").write_text("new answer", encoding="utf-8")
        return ""
    monkeypatch.setattr("builtins.input", fake_input)
    assert browser.BrowserProvider(work_dir=tmp_path).chat("prompt") == "new answer"


def test_backend_has_console_false_for_non_tty(monkeypatch):
    import providers.browser as browser
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert browser._has_console() is False


# --- Item 5: raw provider errors stay out of screen notes ---------------------

def test_backend_generation_failure_note_is_generic(monkeypatch, tmp_path):
    monkeypatch.setenv("DOCBOT_DATA_DIR", str(tmp_path))
    main = importlib.import_module("main")
    from docbot.models import Screen
    screen = Screen(index=3)
    err = RuntimeError('[openrouter] HTTP 402 from https://openrouter.ai/api/v1: '
                       '{"error":{"message":"requires more credits"}}')
    main.mark_generation_failed(screen, err)
    main.mark_generation_failed(screen, err)
    notes = " ".join(screen.content.notes)
    assert "402" not in notes and "openrouter" not in notes and "credits" not in notes
    assert screen.content.notes == [main.GENERATION_FAILED_NOTE]
    assert screen.content.screen_name == "Screen 3 (Failed)"
