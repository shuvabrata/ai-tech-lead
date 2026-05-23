"""Unit tests for the custom LLM provider.

Tests use mocked HTTP responses — no live API or VPN required.
Run with: pytest tests/test_custom_provider.py -v -m unit
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.ai_agent.providers.custom import CustomProvider


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def provider(monkeypatch):
    """Return a CustomProvider with env vars mocked to safe test values."""
    monkeypatch.setenv("CUSTOM_API_TOKEN", "test-token")
    monkeypatch.setenv("CUSTOM_API_URL", "https://api.example.com/chat")
    monkeypatch.setenv("CUSTOM_LLM_MODEL", "test-model")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    return CustomProvider()


def _make_response(json_body: dict, status_code: int = 200) -> MagicMock:
    """Build a mock requests.Response."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_body
    mock_resp.text = str(json_body)
    if status_code >= 400:
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_resp
        )
    else:
        mock_resp.raise_for_status.return_value = None
    return mock_resp


# ---------------------------------------------------------------------------
# Required interface tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_provider_name(provider):
    assert provider.name == "custom"


@pytest.mark.unit
def test_default_model(provider):
    assert provider.default_model == "test-model"


@pytest.mark.unit
def test_supports_native_token_counting_is_false(provider):
    assert provider.supports_native_token_counting is False


@pytest.mark.unit
def test_validate_model_accepts_any(provider):
    for model in ("model-a", "model-b", "some-provider/model-v1", "unknown-model-xyz"):
        assert provider.validate_model(model) is True


@pytest.mark.unit
def test_count_tokens_returns_positive_int(provider):
    messages = [{"role": "user", "content": "Hello world, how are you?"}]
    count = provider.count_tokens(messages)
    assert isinstance(count, int)
    assert count > 0


@pytest.mark.unit
def test_count_tokens_empty_messages(provider):
    assert provider.count_tokens([]) == 0


# ---------------------------------------------------------------------------
# _convert_messages_to_prompt tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_convert_messages_to_prompt(provider):
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is 2+2?"},
    ]
    prompt = provider._convert_messages_to_prompt(messages)  # pylint: disable=protected-access
    assert "System: You are a helpful assistant." in prompt
    assert "User: What is 2+2?" in prompt
    assert prompt.index("System:") < prompt.index("User:")


@pytest.mark.unit
def test_convert_messages_includes_assistant_role(provider):
    messages = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello!"},
        {"role": "user", "content": "Bye"},
    ]
    prompt = provider._convert_messages_to_prompt(messages)  # pylint: disable=protected-access
    assert "Assistant: Hello!" in prompt


# ---------------------------------------------------------------------------
# chat_completion — success path
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_chat_completion_returns_response_text(provider):
    mock_resp = _make_response({"response": "The capital of France is Paris."})
    with patch("requests.post", return_value=mock_resp) as mock_post:
        result = provider.chat_completion([{"role": "user", "content": "Capital of France?"}])
    assert result == "The capital of France is Paris."
    mock_post.assert_called_once()


@pytest.mark.unit
def test_chat_completion_sends_correct_payload(provider):
    mock_resp = _make_response({"response": "Answer"})
    with patch("requests.post", return_value=mock_resp) as mock_post:
        provider.chat_completion(
            [{"role": "user", "content": "Hello"}],
            model="override-model",
        )
    _, kwargs = mock_post.call_args
    payload = kwargs["json"]
    assert payload["model"] == "override-model"
    assert "User: Hello" in payload["prompt"]


@pytest.mark.unit
def test_chat_completion_uses_bearer_auth(provider):
    mock_resp = _make_response({"response": "ok"})
    with patch("requests.post", return_value=mock_resp) as mock_post:
        provider.chat_completion([{"role": "user", "content": "hi"}])
    _, kwargs = mock_post.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"


# ---------------------------------------------------------------------------
# chat_completion — error paths
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_chat_completion_raises_on_401(provider):
    mock_resp = _make_response({"detail": "Invalid token"}, status_code=401)
    with patch("requests.post", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="authentication error"):
            provider.chat_completion([{"role": "user", "content": "hi"}])


@pytest.mark.unit
def test_chat_completion_raises_on_500(provider):
    mock_resp = _make_response({"detail": "Server error"}, status_code=500)
    with patch("requests.post", return_value=mock_resp):
        with pytest.raises(RuntimeError):
            provider.chat_completion([{"role": "user", "content": "hi"}])


@pytest.mark.unit
def test_chat_completion_raises_on_empty_response(provider):
    mock_resp = _make_response({"response": ""})
    with patch("requests.post", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="Empty response"):
            provider.chat_completion([{"role": "user", "content": "hi"}])


@pytest.mark.unit
def test_chat_completion_raises_on_network_error(provider):
    with patch("requests.post", side_effect=requests.exceptions.ConnectionError("timeout")):
        with pytest.raises(RuntimeError, match="request error"):
            provider.chat_completion([{"role": "user", "content": "hi"}])


# ---------------------------------------------------------------------------
# stream_chat_completion — simulated streaming
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_stream_yields_all_words(provider):
    mock_resp = _make_response({"response": "The capital of France is Paris."})

    async def run():
        with patch("requests.post", return_value=mock_resp):
            tokens = []
            async for token in provider.stream_chat_completion(
                [{"role": "user", "content": "Capital of France?"}]
            ):
                tokens.append(token)
        return tokens

    tokens = asyncio.run(run())
    reassembled = "".join(tokens)
    assert reassembled == "The capital of France is Paris."


@pytest.mark.unit
def test_stream_words_have_trailing_space_except_last(provider):
    mock_resp = _make_response({"response": "Hello world"})

    async def run():
        with patch("requests.post", return_value=mock_resp):
            tokens = []
            async for token in provider.stream_chat_completion(
                [{"role": "user", "content": "hi"}]
            ):
                tokens.append(token)
        return tokens

    tokens = asyncio.run(run())
    assert tokens == ["Hello ", "world"]


@pytest.mark.unit
def test_stream_raises_on_api_error(provider):
    mock_resp = _make_response({"detail": "Server error"}, status_code=500)

    async def run():
        with patch("requests.post", return_value=mock_resp):
            async for _ in provider.stream_chat_completion(
                [{"role": "user", "content": "hi"}]
            ):
                pass  # pragma: no cover

    with pytest.raises(RuntimeError):
        asyncio.run(run())


@pytest.mark.unit
def test_stream_propagates_cancelled_error(provider):
    """CancelledError raised during the executor await must be re-raised."""

    async def run():
        with patch.object(
            provider, "chat_completion", side_effect=asyncio.CancelledError()
        ):
            async for _ in provider.stream_chat_completion(
                [{"role": "user", "content": "hi"}]
            ):
                pass  # pragma: no cover

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run())


# ---------------------------------------------------------------------------
# Initialisation guard
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_init_raises_without_token(monkeypatch):
    monkeypatch.delenv("CUSTOM_API_TOKEN", raising=False)
    # Also patch load_dotenv so the .env file is not reloaded during __init__
    with patch("app.ai_agent.providers.custom.custom_provider.load_dotenv"):
        with pytest.raises(ValueError, match="CUSTOM_API_TOKEN"):
            CustomProvider()
