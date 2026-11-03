"""Meta Model API client (stdlib only, no dependencies).

Wired at the Oct 26 gate, per the Oct 22 slice plan. The API is
OpenAI-compatible: POST {base}/chat/completions with a Bearer key.

  base:  META_API_BASE, default https://api.meta.ai/v1
  key:   META_API_KEY, falling back to MODEL_API_KEY
  models: proposer muse-spark-1.3, auditor muse-spark-1.1 (both Muse
    Spark -- same model family, different versions; see Tension B
    disclosure in auditor.py -- family separation is NOT claimed).

Fail-closed by design: a missing key, a network error, a non-200
response, or an unparseable response raises MetaApiError. The caller
(the gate) treats that as an instrument fault, never as a pass and
never as a fabricated verdict. No key material is ever included in
an error message or a lesson record.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

DEFAULT_BASE_URL = "https://api.meta.ai/v1"
DEFAULT_PROPOSER_MODEL = "muse-spark-1.3"
DEFAULT_AUDITOR_MODEL = "muse-spark-1.1"


class MetaApiError(Exception):
    """The Meta Model API could not be used. Never a verdict."""


def _default_transport(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise MetaApiError(f"Meta Model API HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise MetaApiError(f"Meta Model API unreachable: {type(exc).__name__}") from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise MetaApiError("Meta Model API returned an unparseable response") from exc


class MetaApiClient:
    """Minimal chat-completions client. `transport` is injectable so
    tests can fake the API without a key or a network call."""

    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        transport: Optional[Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]]] = None,
    ):
        key = api_key or os.environ.get("META_API_KEY") or os.environ.get("MODEL_API_KEY")
        if not key:
            raise MetaApiError(
                "No Meta Model API key: set META_API_KEY (or MODEL_API_KEY) "
                "from the Meta Model API dashboard. No call was made."
            )
        self.model = model
        self._key = key
        self._base_url = (base_url or os.environ.get("META_API_BASE") or DEFAULT_BASE_URL).rstrip("/")
        self._transport = transport or _default_transport

    def complete(self, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        data = self._transport(
            f"{self._base_url}/chat/completions",
            payload,
            {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"},
        )
        return self._extract_text(data)

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        try:
            choices = data["choices"]
            content = choices[0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise MetaApiError("Meta Model API response had no usable completion") from exc
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        if not isinstance(content, str) or not content.strip():
            raise MetaApiError("Meta Model API returned an empty completion")
        return content.strip()
