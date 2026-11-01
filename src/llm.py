"""LLM client wrapper with retry logic."""
import os
import time

from dotenv import load_dotenv
import openai

from schema import Tokens

load_dotenv()

_client: openai.OpenAI | None = None


def _get_client() -> openai.OpenAI:
    global _client
    if _client is None:
        _client = openai.OpenAI(
            api_key=os.environ["LLM_API_KEY"],
            base_url=os.environ.get("LLM_BASE_URL"),
        )
    return _client


LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")


def call_llm(
    messages: list[dict],
    temperature: float = 0,
    response_format=None,
    max_tokens: int = 500,
) -> tuple[str, object]:
    """Call the LLM with retry on rate-limit / timeout errors.

    Returns (content_str, usage).
    """
    client = _get_client()
    model = os.environ.get("LLM_MODEL", LLM_MODEL)

    kwargs: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format

    last_exc: Exception | None = None
    delays = [1, 2, 4]
    for attempt, delay in enumerate(delays + [None]):
        try:
            resp = client.chat.completions.create(**kwargs)
            content = resp.choices[0].message.content or ""
            return content, resp.usage
        except (openai.RateLimitError, openai.APITimeoutError) as exc:
            last_exc = exc
            if delay is None:
                break
            time.sleep(delay)
        except openai.OpenAIError as exc:
            raise exc

    raise last_exc  # type: ignore[misc]


def tokens_from_usage(usage) -> Tokens:
    """Convert an OpenAI usage object to our Tokens model."""
    if usage is None:
        return Tokens()
    return Tokens(
        prompt=getattr(usage, "prompt_tokens", 0) or 0,
        completion=getattr(usage, "completion_tokens", 0) or 0,
    )

