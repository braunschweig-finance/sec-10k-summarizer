"""
Offline tests for the switchable AI client and the governance policy reader. The AI server is faked, so these check
the plumbing (settings, request format, quote checking, scoring), not a real model's answers.
Run from api/:  python -m pytest tests
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import pytest

import ai_client
import governance_policies as gp

AI_VARS = ["AI_PROVIDER", "AI_BASE_URL", "AI_MODEL", "AI_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for v in AI_VARS:
        monkeypatch.delenv(v, raising=False)


def test_default_provider(monkeypatch):
    assert ai_client.settings()["provider"] == "lmstudio"
    assert ai_client.settings()["base_url"] == "http://localhost:1234/v1"
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    assert ai_client.settings()["provider"] == "gemini"   # the live site keeps working unchanged
    monkeypatch.setenv("AI_BASE_URL", "https://gpu.example.edu/v1/")
    s = ai_client.settings()
    assert (s["provider"], s["base_url"]) == ("custom", "https://gpu.example.edu/v1")


def test_describe_never_shows_the_key(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    d = ai_client.describe()
    assert d["has_key"] and "sk-secret" not in json.dumps(d)


def fake_server(monkeypatch, reply, models=("qwen3-4b",), status=200):
    sent = {}

    def get(url, headers=None, timeout=None):
        sent["models_url"] = url
        return httpx.Response(200, json={"data": [{"id": m} for m in models]}, request=httpx.Request("GET", url))

    def post(url, json=None, headers=None, timeout=None):
        sent.update(url=url, body=json, headers=headers)
        content = reply(json) if callable(reply) else reply
        return httpx.Response(status, json={"model": json["model"], "choices": [{"message": {"content": content}}],
                                            "usage": {"prompt_tokens": 100, "completion_tokens": 20}},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(ai_client.httpx, "get", get)
    monkeypatch.setattr(ai_client.httpx, "post", post)
    return sent


def test_openai_compatible_request(monkeypatch):
    sent = fake_server(monkeypatch, "hello", models=("text-embedding-nomic", "qwen3-4b"))
    r = ai_client.chat("hi", system="be brief")
    assert r["text"] == "hello" and r["model"] == "qwen3-4b"      # embedding models are skipped
    assert sent["url"] == "http://localhost:1234/v1/chat/completions"
    assert sent["body"]["temperature"] == 0
    assert sent["body"]["messages"][0] == {"role": "system", "content": "be brief"}
    assert sent["headers"] == {}                                   # LM Studio needs no key


def test_key_sent_and_rate_limit(monkeypatch):
    monkeypatch.setenv("AI_BASE_URL", "https://gpu.example.edu/v1")
    monkeypatch.setenv("AI_API_KEY", "k")
    monkeypatch.setenv("AI_MODEL", "llama-70b")
    sent = fake_server(monkeypatch, "x")
    ai_client.chat("hi")
    assert sent["headers"] == {"Authorization": "Bearer k"} and sent["body"]["model"] == "llama-70b"
    fake_server(monkeypatch, "x", status=429)
    with pytest.raises(ai_client.AIError) as e:
        ai_client.chat("hi")
    assert e.value.busy


def test_server_not_running(monkeypatch):
    def down(*a, **k):
        raise httpx.ConnectError("refused")
    monkeypatch.setattr(ai_client.httpx, "get", down)
    with pytest.raises(ai_client.AIError, match="Is it running"):
        ai_client.chat("hi")


# ---------- Governance policy reader ----------

PROXY = (
    "Table of Contents. Proxy access 12. Special meetings 14. " * 3 +
    "Board Leadership Structure. Our Board is led by an independent Chair, Ms. Jane Doe, and the roles of Chair and CEO are separate. "
    "Shareholders owning 3% of our outstanding shares for three years may include their own director nominees in our proxy "
    "materials under our proxy access bylaw. "
    "Shareholders holding at least 15% of our outstanding shares may call a special meeting. "
    "Our CEO must hold shares worth six times base salary under our stock ownership guidelines. "
    "Directors and executive officers may not pledge Company stock. "
    "We are an equal opportunity employer. " * 20
)


def test_passages_pick_relevant_sentences():
    ex = gp.passages(PROXY, [r"special meeting", r"call a special"])
    assert any("15% of our outstanding shares may call a special meeting" in e for e in ex)
    assert sum(len(e) for e in ex) <= gp.PASSAGE_CHARS


def test_quote_check():
    assert gp.quote_in_filing("Shareholders holding at least 15% of our outstanding shares may call a special meeting.", PROXY)
    assert gp.quote_in_filing("our Board is led by an INDEPENDENT chair ... the roles of Chair and CEO are separate", PROXY)
    assert not gp.quote_in_filing("Shareholders holding at least 10% of our outstanding shares may call a special meeting.", PROXY)
    assert not gp.quote_in_filing("yes", PROXY)


def test_parse_handles_small_model_habits():
    reply = '<think>let me see</think>\n```json\n{"answer": "Yes", "detail": "15% threshold", "quote": "q"}\n```'
    assert gp.parse(reply) == {"answer": "yes", "detail": "15% threshold", "quote": "q"}
    assert gp.parse('{"answer": "maybe"}')["answer"] == "not disclosed"


def test_read_proxy_end_to_end(monkeypatch):
    def answer(body):
        q = body["messages"][-1]["content"]
        if "special meeting" in q.split("\n")[0]:
            return json.dumps({"answer": "yes", "detail": "15% of shares",
                               "quote": "Shareholders holding at least 15% of our outstanding shares may call a special meeting."})
        if "independent director" in q.split("\n")[0]:
            # A made-up quote: must not count
            return json.dumps({"answer": "yes", "detail": "", "quote": "The Chair is fully independent of management at all times."})
        return json.dumps({"answer": "not disclosed", "detail": "", "quote": ""})
    fake_server(monkeypatch, answer)
    out = gp.read_proxy(PROXY)
    by = {r["key"]: r for r in out["policies"]}
    assert by["special_meetings"]["verified"] and by["special_meetings"]["answer"] == "yes"
    assert not by["independent_chair"]["verified"]
    assert by["written_consent"]["answer"] == "not disclosed" and by["written_consent"]["model"] is None  # no AI call
    assert out["score"] == {"friendly": 1, "answered": 1, "asked": len(gp.POLICIES)}
