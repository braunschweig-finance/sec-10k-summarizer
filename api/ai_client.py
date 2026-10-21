"""
One switchable AI client for the app. Every AI task (the research memo, governance policy reading) calls chat() here,
so changing where the AI runs is a settings change, not a code change.

Settings (environment variables):
  AI_PROVIDER   lmstudio | ollama | openai | gemini | custom
                Left blank: gemini when GEMINI_API_KEY is set (the live site's current setup), otherwise lmstudio.
  AI_BASE_URL   The OpenAI-compatible address, e.g. a university GPU server. Optional for the named providers.
  AI_MODEL      Model name. Optional for lmstudio/ollama: the first model the server lists is used.
  AI_API_KEY    Key for the server, if it needs one (LM Studio and Ollama don't).

LM Studio, Ollama, vLLM (what most university GPU servers run) and OpenAI all speak the same "chat completions"
format, so one code path covers all of them. Gemini keeps Google's own library, which the live site already uses.
"""
import os
import time

import httpx

PRESETS = {
    "lmstudio": {"base_url": "http://localhost:1234/v1"},
    "ollama": {"base_url": "http://localhost:11434/v1"},
    "openai": {"base_url": "https://api.openai.com/v1", "key_env": "OPENAI_API_KEY", "model": "gpt-5-mini"},
    "gemini": {"key_env": "GEMINI_API_KEY", "models": ["gemini-3.8-flash", "gemini-3.6-flash"]},
    "custom": {},
}
# Local models on a laptop CPU can take minutes on a long prompt
TIMEOUT = float(os.environ.get("AI_TIMEOUT", "600"))


class AIError(Exception):
    def __init__(self, message, busy=False):
        super().__init__(message)
        self.busy = busy  # a rate limit: worth trying again later


def settings():
    provider = (os.environ.get("AI_PROVIDER") or "").strip().lower()
    if not provider:
        provider = "custom" if os.environ.get("AI_BASE_URL") else "gemini" if os.environ.get("GEMINI_API_KEY") else "lmstudio"
    if provider not in PRESETS:
        raise AIError(f"Unknown AI_PROVIDER '{provider}'. Use one of: {', '.join(PRESETS)}.")
    p = PRESETS[provider]
    base_url = (os.environ.get("AI_BASE_URL") or p.get("base_url") or "").rstrip("/")
    api_key = os.environ.get("AI_API_KEY") or os.environ.get(p.get("key_env", ""), "")
    model = os.environ.get("AI_MODEL") or p.get("model", "")
    return {"provider": provider, "base_url": base_url, "api_key": api_key, "model": model}


def describe():
    """Where the AI runs, for the /api/ai-status page. Never includes the key."""
    s = settings()
    return {"provider": s["provider"], "base_url": s["base_url"] or None, "model": s["model"] or None,
            "has_key": bool(s["api_key"])}


def chat(prompt, system=None, json_mode=False, max_tokens=None):
    """Sends one prompt and returns {"text", "usage", "model", "provider"}. Temperature 0, so the same filing gives
    the same answer each time."""
    s = settings()
    if s["provider"] == "gemini":
        return _gemini(s, prompt, system)
    if not s["base_url"]:
        raise AIError("AI_BASE_URL is not set.")
    return _openai_compatible(s, prompt, system, json_mode, max_tokens)


def _headers(s):
    return {"Authorization": f"Bearer {s['api_key']}"} if s["api_key"] else {}


def first_model(s):
    """The first model the server lists. In LM Studio that's the model currently loaded."""
    try:
        r = httpx.get(f"{s['base_url']}/models", headers=_headers(s), timeout=10)
        r.raise_for_status()
        models = [m["id"] for m in r.json().get("data", []) if "embed" not in m["id"].lower()]
    except httpx.HTTPError as e:
        raise AIError(f"Can't reach the AI server at {s['base_url']} ({e}). Is it running?")
    if not models:
        raise AIError(f"The AI server at {s['base_url']} has no model loaded.")
    return models[0]


def _openai_compatible(s, prompt, system, json_mode, max_tokens):
    model = s["model"] or first_model(s)
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    body = {"model": model, "messages": messages, "temperature": 0}
    if max_tokens:
        body["max_tokens"] = max_tokens
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    started = time.time()
    try:
        r = httpx.post(f"{s['base_url']}/chat/completions", json=body, headers=_headers(s), timeout=TIMEOUT)
        if r.status_code == 400 and json_mode:
            # Some servers (older LM Studio builds) reject json_object; the prompt asks for JSON anyway
            body.pop("response_format")
            r = httpx.post(f"{s['base_url']}/chat/completions", json=body, headers=_headers(s), timeout=TIMEOUT)
    except httpx.HTTPError as e:
        raise AIError(f"Can't reach the AI server at {s['base_url']} ({e}). Is it running?")
    if r.status_code == 429:
        raise AIError("The AI server is busy (rate limit). Try again in a minute.", busy=True)
    if r.status_code >= 400:
        raise AIError(f"The AI server returned {r.status_code}: {r.text[:300]}")
    data = r.json()
    usage = data.get("usage") or {}
    return {
        "text": data["choices"][0]["message"]["content"] or "",
        "usage": {"input": usage.get("prompt_tokens"), "output": usage.get("completion_tokens")} if usage else None,
        "model": data.get("model") or model,
        "provider": s["provider"],
        "seconds": round(time.time() - started, 1),
    }


def _gemini(s, prompt, system):
    if not s["api_key"]:
        raise AIError("GEMINI_API_KEY is not set on the API server.")
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=s["api_key"])
    config = types.GenerateContentConfig(system_instruction=system) if system else None
    models = [s["model"]] if s["model"] else PRESETS["gemini"]["models"]
    response, last_error, started = None, None, time.time()
    # A 503 is retried once; a 429 moves to the next model instead of retrying (same rule as app.py)
    for model_name in models:
        for attempt in range(2):
            try:
                response = client.models.generate_content(model=model_name, contents=prompt, config=config)
                break
            except Exception as err:
                last_error = err
                if attempt == 0 and ("503" in str(err) or "UNAVAILABLE" in str(err)):
                    time.sleep(3)
                    continue
                break
        if response:
            break
    if not response:
        if "429" in str(last_error) or "RESOURCE_EXHAUSTED" in str(last_error):
            raise AIError("The AI writer is busy (free-tier limit). Try again in a minute.", busy=True)
        raise AIError(f"Failed to generate: {last_error}")
    usage = None
    if getattr(response, "usage_metadata", None):
        usage = {"input": response.usage_metadata.prompt_token_count, "output": response.usage_metadata.candidates_token_count}
    return {"text": response.text, "usage": usage, "model": model_name, "provider": "gemini",
            "seconds": round(time.time() - started, 1)}
