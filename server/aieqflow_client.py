"""AI-EqfLow (aieqflow.com, OpenAI-compatible) API client.

Auth: Authorization: Bearer $AIEQFLOW_API_KEY
The key is NEVER hardcoded - it is read from the environment variable
AIEQFLOW_API_KEY, falling back to a git-ignored local .env file.
"""

from __future__ import annotations

import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable

DEFAULT_BASE_URL = "https://aieqflow.com/v1"
ENV_KEY = "AIEQFLOW_API_KEY"
RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504}

# WorkBuddy injects env vars as literal "${NAME}" placeholders when the user
# has not filled the connector's token form yet. Treat those as "unset" so we
# fall back to defaults / local .env instead of sending a bogus base URL.
_PLACEHOLDER_RE = re.compile(r"^\$\{[^}]*\}$")

# Extra local fallbacks, checked in order, when the env var is missing.
_ENV_FILE_CANDIDATES = (
    Path(__file__).resolve().parent / ".env",
    Path(__file__).resolve().parent.parent / ".env",
    Path.home() / ".workbuddy" / "ai-eqflow.env",
)


class AIEqFlowError(RuntimeError):
    def __init__(self, status: int, message: str, payload: Any = None):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.payload = payload


def is_placeholder(value: str | None) -> bool:
    """True when value is an unresolved ${VAR} placeholder (or empty)."""
    if not value:
        return True
    return bool(_PLACEHOLDER_RE.match(value.strip()))


def env_str(name: str, default: str = "") -> str:
    """os.environ lookup that treats unresolved ${VAR} placeholders as unset."""
    value = (os.environ.get(name) or "").strip()
    return default if is_placeholder(value) else value


def _load_env_file() -> None:
    """Load KEY=VALUE pairs from a local .env (git-ignored) as a fallback."""
    if env_str(ENV_KEY):
        return
    for env_path in _ENV_FILE_CANDIDATES:
        try:
            if not env_path.exists():
                continue
            text = env_path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and v and is_placeholder(os.environ.get(k)):
                os.environ[k] = v
        if env_str(ENV_KEY):
            return


def mask(secret: str) -> str:
    if not secret:
        return "<empty>"
    return secret[:6] + "..." + secret[-4:] if len(secret) > 12 else "***"


class AIEqFlowClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 3,
    ) -> None:
        _load_env_file()
        self.api_key = api_key or env_str(ENV_KEY)
        if not self.api_key:
            raise RuntimeError(
                f"Missing API key. Open the AI-EqfLow connector card in WorkBuddy "
                f"and paste your key, or set {ENV_KEY} / write it to "
                f"~/.workbuddy/ai-eqflow.env."
            )
        candidates = [base_url, env_str("API_BASE"), DEFAULT_BASE_URL]
        for cand in candidates:
            if cand and not is_placeholder(cand) and str(cand).startswith(("http://", "https://")):
                base_url = str(cand).rstrip("/")
                break
        self.base_url = base_url or DEFAULT_BASE_URL
        self.timeout = timeout
        self.max_retries = max_retries

    # ---------- low level ----------
    def _request(self, method: str, path: str, body: dict | None = None) -> tuple[int, str]:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")

    def _request_json(self, method: str, path: str, body: dict | None = None) -> dict:
        last: tuple[int, str] | None = None
        for attempt in range(1, self.max_retries + 1):
            status, text = self._request(method, path, body)
            if status == 200:
                try:
                    return json.loads(text)
                except json.JSONDecodeError as e:
                    raise AIEqFlowError(status, f"invalid JSON: {e}", text) from e
            last = (status, text)
            if status in RETRY_STATUS and attempt < self.max_retries:
                # exponential backoff + jitter
                time.sleep(min(2 ** attempt, 10) + random.random())
                continue
            break
        status, text = last  # type: ignore[misc]
        try:
            err = json.loads(text).get("error", {})
            msg = err.get("message", text[:300])
        except Exception:
            msg = text[:300]
        raise AIEqFlowError(status, msg, text)

    # ---------- public API ----------
    def list_models(self) -> list[dict]:
        return self._request_json("GET", "/models").get("data", [])

    def chat(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int = 512,
        temperature: float | None = None,
        stream: bool = False,
        **extra: Any,
    ) -> dict:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if temperature is not None:
            body["temperature"] = temperature
        body.update(extra)
        return self._request_json("POST", "/chat/completions", body)

    def chat_text(self, prompt: str, model: str, **kwargs: Any) -> str:
        resp = self.chat([{"role": "user", "content": prompt}], model=model, **kwargs)
        choices = resp.get("choices") or []
        if not choices:
            return ""
        return (choices[0].get("message") or {}).get("content", "") or ""

    def find_chat_models(self, models: Iterable[dict] | None = None) -> list[str]:
        models = list(models if models is not None else self.list_models())
        ids = [
            m["id"]
            for m in models
            if m.get("model_type") == "对话" and "openai" in (m.get("supported_endpoint_types") or [])
        ]
        if ids:
            return ids
        # fallback 1: any model exposing the openai endpoint
        ids = [
            m["id"]
            for m in models
            if "openai" in (m.get("supported_endpoint_types") or [])
        ]
        if ids:
            return ids
        # fallback 2: New-API relays sometimes omit model_type/endpoints entirely
        return [m["id"] for m in models if m.get("id")]

    # ---------- quota / billing ----------
    def get_billing(self) -> dict:
        """OpenAI-compatible billing endpoints.

        Note: these report USD usage. Many relay sites return a placeholder
        hard_limit_usd (e.g. 1e8) meaning 'no hard cap configured'.
        """
        sub = self._request_json("GET", "/v1/dashboard/billing/subscription")
        usage = self._request_json("GET", "/v1/dashboard/billing/usage")
        limit = float(sub.get("hard_limit_usd") or 0)
        used = float(usage.get("total_usage") or 0)
        capped = 0 < limit < 1_000_000  # placeholder values like 1e8 == unlimited
        return {
            "token_name": sub.get("token_name"),
            "has_payment_method": sub.get("has_payment_method"),
            "hard_limit_usd": limit,
            "used_usd": used,
            "remaining_usd": (limit - used) if capped else None,
            "capped": capped,
            "access_until": sub.get("access_until"),
            "raw": {"subscription": sub, "usage": usage},
        }

    def get_token_usage(self) -> dict:
        """GET {root}/api/usage/token - New-API token quota (sk- key works)."""
        root = self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url
        saved = self.base_url
        self.base_url = root
        try:
            return self._request_json("GET", "/api/usage/token")
        finally:
            self.base_url = saved

    def check_quota(self, min_remaining_usd: float = 0.0) -> tuple[bool, dict]:
        """Pre-flight balance check. Returns (ok, billing_info)."""
        info = self.get_billing()
        if info["capped"]:
            ok = info["remaining_usd"] >= min_remaining_usd
        else:
            ok = True  # no hard cap configured -> cannot judge, allow
        return ok, info


if __name__ == "__main__":
    c = AIEqFlowClient()
    print("key:", mask(c.api_key))
    ms = c.list_models()
    print("models:", len(ms))
    print("chat models:", len(c.find_chat_models(ms)))
