import httpx
import pytest

from app.llm.openrouter_client import LLMResponseError, OpenRouterClient


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_complete_json_parses_valid_response(monkeypatch):
    def fake_post(url, headers, json, timeout):
        return DummyResponse({"choices": [{"message": {"content": '{"a": 1}'}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    client = OpenRouterClient(api_key="test-key")
    result = client.complete_json("model-x", "system", "user")
    assert result == {"a": 1}


def test_complete_json_raises_on_invalid_json(monkeypatch):
    def fake_post(url, headers, json, timeout):
        return DummyResponse({"choices": [{"message": {"content": "not json"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    client = OpenRouterClient(api_key="test-key")
    with pytest.raises(LLMResponseError):
        client.complete_json("model-x", "system", "user")
