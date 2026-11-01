"""LLM client wrapper with robust rate-limit handling and graceful degradation."""
import os
import re
import time
import logging

from dotenv import load_dotenv
import openai

from schema import Tokens

load_dotenv()
logger = logging.getLogger("menumate.llm")

_client: openai.OpenAI | None = None


def _get_client() -> openai.OpenAI:
    global _client
    if _client is None:
        _client = openai.OpenAI(
            api_key=os.environ.get("LLM_API_KEY", ""),
            base_url=os.environ.get("LLM_BASE_URL"),
            max_retries=0,  # Disable OpenAI SDK internal retries to take full explicit control
            timeout=12.0,   # Prevent hanging requests indefinitely
        )
    return _client


LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")


def _parse_retry_after(exc: Exception) -> float | None:
    """Extract wait time in seconds from Groq 429 response message or headers."""
    # Check headers if available
    response = getattr(exc, "response", None)
    if response is not None and hasattr(response, "headers"):
        retry_header = response.headers.get("retry-after")
        if retry_header:
            try:
                return float(retry_header)
            except (ValueError, TypeError):
                pass

    # Extract 'Please try again in X.XXs' or similar from error message
    msg = str(exc)
    m = re.search(r"try again in ([\d\.]+)\s*(?:s|seconds)?", msg, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except (ValueError, TypeError):
            pass

    m_ms = re.search(r"try again in (\d+)\s*ms", msg, re.IGNORECASE)
    if m_ms:
        try:
            return float(m_ms.group(1)) / 1000.0
        except (ValueError, TypeError):
            pass

    return None


def call_llm(
    messages: list[dict],
    temperature: float = 0,
    response_format=None,
    max_tokens: int = 500,
) -> tuple[str, object]:
    """Call the LLM with intelligent 429 backoff and graceful non-blocking behavior.

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
    # Maximum 3 attempts with progressive backoff if retry-after is small (< 5s)
    # If retry-after is large or quota exhausted, fail early to let caller use deterministic fallback
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(**kwargs)
            content = resp.choices[0].message.content or ""
            return content, resp.usage
        except (openai.RateLimitError, openai.APITimeoutError) as exc:
            last_exc = exc
            suggested_wait = _parse_retry_after(exc)
            
            # If server asks for an excessively long wait (> 6 seconds), do not freeze the benchmark
            if suggested_wait is not None and suggested_wait > 6.0:
                logger.warning(
                    f"Rate limit hit with long wait ({suggested_wait:.2f}s). Failing fast to fallback."
                )
                break

            # If it's a manageable wait, respect server's hint or use jittered exponential delay
            delay = suggested_wait if suggested_wait is not None else (1.5 * (2 ** attempt))
            # Bound delay to at most 4 seconds per retry
            delay = min(delay, 4.0)

            if attempt < 2:
                time.sleep(delay)
            else:
                break
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


