"""
Which AI service writes the scenarios, and how to call it.

Four providers share one small interface:
  anthropic          Claude
  openai             OpenAI
  gemini             Google Gemini
  openai_compatible  anything that speaks the OpenAI chat API: Ollama, LM Studio,
                     vLLM, a company gateway, ...

The choice (provider, model, base URL, auth style) is an install-wide setting kept in
storage/llm_config.json and changed by an admin. The API key is NOT stored: the person
generating a scenario types it per request, and it is only forwarded to the provider.
A self-hosted model with no authentication needs no key at all (auth_mode "none").

Heads-up: the scenario prompts were tuned and validated with Claude. A smaller local
model may return malformed XML more often; the scenario guard still validates whatever
comes back before it is ever run.
"""
import json
import os
import ipaddress
from urllib.parse import urlparse

import httpx

from config import STORAGE_DIR
from fsutil import write_private

CONFIG_FILE = os.path.join(STORAGE_DIR, "llm_config.json")

DEFAULT_PROVIDER = "anthropic"
DEFAULT_MODEL = "claude-sonnet-4-6"
VALID_PROVIDERS = {"anthropic", "openai", "gemini", "openai_compatible"}
VALID_AUTH_MODES = {"api_key", "bearer", "none"}
TIMEOUT_S = 120.0

_cached_config = None


def _default_config() -> dict:
    return {"provider": DEFAULT_PROVIDER, "base_url": None, "model": DEFAULT_MODEL, "auth_mode": "api_key"}


def validate_base_url(url: str) -> str:
    """http(s) only, a real host, no credentials in the URL, never the cloud metadata address."""
    u = urlparse(url or "")
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("Base URL must start with http:// or https:// and include a host")
    if u.username or u.password:
        raise ValueError("Put credentials in the key field, not in the URL")
    try:
        ip = ipaddress.ip_address(u.hostname)
        if ip.is_link_local or ip.is_multicast or ip.is_unspecified:
            raise ValueError("That address is not allowed as an AI endpoint")
    except ValueError as e:
        if "not allowed" in str(e):
            raise
    return url.rstrip("/")


def get_config() -> dict:
    global _cached_config
    if _cached_config is not None:
        return _cached_config
    cfg = _default_config()
    try:
        with open(CONFIG_FILE) as f:
            data = json.load(f)
        if data.get("provider") in VALID_PROVIDERS:
            cfg["provider"] = data["provider"]
            cfg["model"] = str(data.get("model") or DEFAULT_MODEL)
            cfg["base_url"] = data.get("base_url") or None
            if data.get("auth_mode") in VALID_AUTH_MODES:
                cfg["auth_mode"] = data["auth_mode"]
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as e:
        print(f"[llm_provider] config unreadable ({e}); using the default (Anthropic)")
    _cached_config = cfg
    return cfg


def save_config(provider: str, model: str, base_url, auth_mode: str) -> dict:
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"provider must be one of: {', '.join(sorted(VALID_PROVIDERS))}")
    if auth_mode not in VALID_AUTH_MODES:
        raise ValueError(f"auth_mode must be one of: {', '.join(sorted(VALID_AUTH_MODES))}")
    model = (model or "").strip()
    if not model or len(model) > 128:
        raise ValueError("Model is required")
    if provider == "openai_compatible" and not base_url:
        raise ValueError("Base URL is required for a private / self-hosted model")
    base_url = validate_base_url(base_url) if base_url else None
    write_private(CONFIG_FILE, json.dumps(
        {"provider": provider, "model": model, "base_url": base_url, "auth_mode": auth_mode}, indent=2))
    reload_config()
    return get_config()


def reload_config() -> None:
    global _cached_config
    _cached_config = None


def key_required() -> bool:
    cfg = get_config()
    return not (cfg["provider"] == "openai_compatible" and cfg["auth_mode"] == "none")


async def generate(api_key: str, prompt: str, max_tokens: int = 3500) -> str:
    """Send one prompt to the configured provider and return the reply text. Raises on any failure."""
    cfg = get_config()
    if key_required() and not api_key:
        raise ValueError("An API key is required for this provider")
    async with httpx.AsyncClient(timeout=TIMEOUT_S, follow_redirects=False) as client:
        if cfg["provider"] == "anthropic":
            return await _anthropic(client, api_key, prompt, max_tokens, cfg)
        if cfg["provider"] == "openai":
            return await _openai_style(client, "https://api.openai.com/v1/chat/completions",
                                       api_key, prompt, max_tokens, cfg, "bearer")
        if cfg["provider"] == "gemini":
            return await _gemini(client, api_key, prompt, max_tokens, cfg)
        url = validate_base_url(cfg["base_url"]) + "/chat/completions"
        return await _openai_style(client, url, api_key, prompt, max_tokens, cfg, cfg["auth_mode"])


def _json(resp: httpx.Response) -> dict:
    try:
        return resp.json()
    except ValueError:
        raise RuntimeError(f"The AI service answered with HTTP {resp.status_code} and no JSON body")


def _error_text(err) -> str:
    return str(err.get("message", err)) if isinstance(err, dict) else str(err)


async def _anthropic(client, api_key, prompt, max_tokens, cfg) -> str:
    resp = await client.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": cfg["model"], "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]})
    data = _json(resp)
    if "error" in data:
        raise RuntimeError(_error_text(data["error"]))
    if data.get("stop_reason") == "max_tokens":
        raise RuntimeError("The reply was cut off (too long). Shorten the description and try again")
    return "".join(b.get("text", "") for b in data.get("content", []))


async def _openai_style(client, url, api_key, prompt, max_tokens, cfg, auth_mode) -> str:
    headers = {"content-type": "application/json"}
    if auth_mode in ("bearer", "api_key") and api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    resp = await client.post(url, headers=headers, json={
        "model": cfg["model"], "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}]})
    data = _json(resp)
    if "error" in data:
        raise RuntimeError(_error_text(data["error"]))
    choice = data["choices"][0]
    if choice.get("finish_reason") == "length":
        raise RuntimeError("The reply was cut off (too long). Shorten the description and try again")
    return choice["message"]["content"] or ""


async def _gemini(client, api_key, prompt, max_tokens, cfg) -> str:
    resp = await client.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{cfg['model']}:generateContent",
        headers={"x-goog-api-key": api_key, "content-type": "application/json"},  # header, so the key never lands in a URL or a log
        json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": max_tokens}})
    data = _json(resp)
    if "error" in data:
        raise RuntimeError(_error_text(data["error"]))
    cand = data["candidates"][0]
    if cand.get("finishReason") == "MAX_TOKENS":
        raise RuntimeError("The reply was cut off (too long). Shorten the description and try again")
    return "".join(p.get("text", "") for p in cand["content"]["parts"])
