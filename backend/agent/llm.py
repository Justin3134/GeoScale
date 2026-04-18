import json
import os
import re

from openai import OpenAI

# DigitalOcean GenAI Platform exposes an OpenAI-compatible endpoint.
_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.getenv("DIGITALOCEAN_API_KEY"),
            base_url=os.getenv("DIGITALOCEAN_BASE_URL", "https://inference.do-ai.run/v1"),
        )
    return _client


def think(system_prompt: str, user_message: str, max_tokens: int = 1000) -> str:
    """Single-shot LLM call. Returns the assistant's text content, stripped of
    markdown code fences so callers can `json.loads()` safely."""
    response = _get_client().chat.completions.create(
        model=os.getenv("DIGITALOCEAN_MODEL", "llama3.3-70b-instruct"),
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    raw = response.choices[0].message.content or ""
    return _strip_fences(raw)


def _strip_fences(text: str) -> str:
    """Remove markdown code fences and surrounding chatter so the response is parseable JSON."""
    s = text.strip()
    # ```json ... ``` or ``` ... ```
    fence = re.match(r"^```(?:json|JSON)?\s*\n?(.*?)\n?```$", s, re.DOTALL)
    if fence:
        s = fence.group(1).strip()
    # If still not JSON, try extracting the first {...} or [...] block
    if s and s[0] not in "{[":
        m = re.search(r"(\{.*\}|\[.*\])", s, re.DOTALL)
        if m:
            s = m.group(1)
    return s


def think_json(system_prompt: str, user_message: str, max_tokens: int = 1000):
    """Like `think` but parses JSON. Returns None on failure."""
    raw = think(system_prompt, user_message, max_tokens=max_tokens)
    try:
        return json.loads(raw)
    except Exception:
        return None
