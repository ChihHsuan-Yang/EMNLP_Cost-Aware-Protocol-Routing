"""OpenAI-compatible chat client with retries, timeout and token accounting.

Works against ANY OpenAI-compatible ``/chat/completions`` endpoint. Uses only
the standard library (urllib) so the package has no hard dependency on the
``openai`` SDK; that also makes the retry and timeout behaviour explicit and
auditable rather than inherited from an SDK version we cannot pin.

Credentials are read from environment variables ONLY. No key, URL or host is
ever written into a config file, a manifest, or a log line.
"""

from __future__ import annotations

import json
import os
import random
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


class LLMResult(object):
    """Mirror of agentverse/llms/base.py::LLMResult."""

    __slots__ = ("content", "send_tokens", "recv_tokens", "total_tokens",
                 "finish_reason", "error", "attempts", "latency_seconds")

    def __init__(self, content="", send_tokens=0, recv_tokens=0, total_tokens=0,
                 finish_reason="", error="", attempts=0, latency_seconds=0.0):
        self.content = content
        self.send_tokens = int(send_tokens)
        self.recv_tokens = int(recv_tokens)
        self.total_tokens = int(total_tokens)
        self.finish_reason = finish_reason
        self.error = error
        self.attempts = int(attempts)
        self.latency_seconds = float(latency_seconds)

    def to_dict(self) -> Dict[str, Any]:
        return {name: getattr(self, name) for name in self.__slots__}


class TokenLedger(object):
    """Thread-safe token/call accounting, per agent role and in total.

    Upstream, accounting lives on each OpenAIChat instance
    (total_prompt_tokens / total_completion_tokens / total_request_count,
    agentverse/llms/openai.py:994-996) and is aggregated by
    agentverse/metrics/collector.py::snapshot_agent_tokens. One known upstream
    quirk is reproduced deliberately and one is FIXED:

      * reproduced: counters are reset per problem (upstream
        TaskSolving.prepare_example -> environment.reset_token_counters()).
      * FIXED: upstream increments total_request_count ONCE per logical call,
        so HTTP retries are invisible. Here we record BOTH `calls` (logical)
        and `http_attempts` (actual requests issued), because a cost estimate
        built on the logical count understates a rate-limited run.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.prompt_tokens = 0
            self.completion_tokens = 0
            self.calls = 0
            self.http_attempts = 0
            self.failed_calls = 0
            self.by_role = {}

    def record(self, role: str, result: LLMResult) -> None:
        with self._lock:
            self.prompt_tokens += result.send_tokens
            self.completion_tokens += result.recv_tokens
            self.calls += 1
            self.http_attempts += max(1, result.attempts)
            if result.error:
                self.failed_calls += 1
            slot = self.by_role.setdefault(
                role,
                {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0,
                 "http_attempts": 0, "failed_calls": 0},
            )
            slot["prompt_tokens"] += result.send_tokens
            slot["completion_tokens"] += result.recv_tokens
            slot["calls"] += 1
            slot["http_attempts"] += max(1, result.attempts)
            slot["failed_calls"] += int(bool(result.error))

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "total_tokens": self.prompt_tokens + self.completion_tokens,
                "calls": self.calls,
                "http_attempts": self.http_attempts,
                "failed_calls": self.failed_calls,
                "by_role": json.loads(json.dumps(self.by_role)),
            }


class ProviderError(RuntimeError):
    """Raised when the provider cannot be reached or refuses the request."""


class BaseProvider(object):
    """Interface every backend implements."""

    name = "base"

    def chat(self, messages, model, temperature, max_tokens, timeout_seconds):
        raise NotImplementedError

    def describe(self) -> Dict[str, Any]:
        """Non-secret provider description for the run manifest."""
        return {"provider_type": self.name}


class OpenAICompatibleProvider(BaseProvider):
    """POSTs to ``{base_url}/chat/completions`` with a Bearer token.

    base_url and api_key come from environment variables named by the provider
    config (default INFERENCE_BASE_URL / INFERENCE_API_KEY). Neither value is
    stored on the instance in a form that reaches an artifact: describe()
    reports the env var NAMES and whether they were set, never the values.
    """

    name = "openai_compatible"

    def __init__(self, base_url_env="INFERENCE_BASE_URL",
                 api_key_env="INFERENCE_API_KEY", extra_headers=None,
                 send_auth_header=True):
        self.base_url_env = base_url_env
        self.api_key_env = api_key_env
        self.extra_headers = dict(extra_headers or {})
        self.send_auth_header = bool(send_auth_header)
        self._base_url = os.environ.get(base_url_env, "").strip().rstrip("/")
        self._api_key = os.environ.get(api_key_env, "").strip()
        if not self._base_url:
            raise ProviderError(
                "Environment variable %s is not set. Point it at your "
                "OpenAI-compatible endpoint, e.g. https://host/v1 . "
                "See .env.example." % base_url_env
            )
        if self.send_auth_header and not self._api_key:
            raise ProviderError(
                "Environment variable %s is not set. Set it to your API key, "
                "or set send_auth_header: false in the provider config for an "
                "endpoint that needs no credential." % api_key_env
            )

    def chat(self, messages, model, temperature, max_tokens, timeout_seconds):
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {"Content-Type": "application/json"}
        headers.update(self.extra_headers)
        if self.send_auth_header:
            headers["Authorization"] = "Bearer %s" % self._api_key
        request = urllib.request.Request(
            self._base_url + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    def describe(self) -> Dict[str, Any]:
        return {
            "provider_type": self.name,
            "base_url_env": self.base_url_env,
            "api_key_env": self.api_key_env,
            "base_url_env_set": bool(self._base_url),
            "api_key_env_set": bool(self._api_key),
            "send_auth_header": self.send_auth_header,
            "base_url_value_recorded": False,
        }


def extract_message_text(response: Dict[str, Any]) -> (str, str):
    """Pull assistant text out of a chat-completions response.

    Port of the fallback ladder in agentverse/llms/openai.py::
    _get_content_or_empty (813-912). Some reasoning-tuned servers (gpt-oss
    among them) return an empty ``content`` with the text under
    ``reasoning_content`` / ``reasoning`` / ``output_text``; without this
    ladder those turns read as empty responses.
    """
    choices = response.get("choices") or []
    if not choices:
        return "", ""
    choice = choices[0] or {}
    finish_reason = str(choice.get("finish_reason") or "")
    message = choice.get("message") or {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip(), finish_reason
    for field in ("reasoning_content", "output_text", "reasoning"):
        value = message.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip(), finish_reason
        if isinstance(value, dict):
            for key in ("text", "content", "value", "output_text"):
                nested = value.get(key)
                if isinstance(nested, str) and nested.strip():
                    return nested.strip(), finish_reason
    return "", finish_reason


class ChatClient(object):
    """Retrying wrapper that produces LLMResult and feeds the TokenLedger."""

    def __init__(self, provider, model, temperature=0.0, max_tokens=4096,
                 timeout_seconds=600.0, max_retries=7, backoff_cap_seconds=60.0,
                 ledger=None, logger=None, seed=0):
        self.provider = provider
        self.model = model
        self.temperature = float(temperature)
        self.max_tokens = int(max_tokens)
        self.timeout_seconds = float(timeout_seconds)
        self.max_retries = int(max_retries)
        self.backoff_cap_seconds = float(backoff_cap_seconds)
        self.ledger = ledger if ledger is not None else TokenLedger()
        self.logger = logger
        self._rng = random.Random(seed)

    def _log(self, message: str) -> None:
        if self.logger is not None:
            self.logger(message)

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        """429 and 5xx and connection/timeout errors are retryable; 4xx is not.

        Upstream splits these into a 7-attempt rate-limit budget and a
        4-attempt transient budget (agentverse/llms/openai.py:169-172). We use
        one budget for both and say so in docs/track_b_requirements.md.
        """
        if isinstance(exc, urllib.error.HTTPError):
            return exc.code == 429 or exc.code >= 500
        if isinstance(exc, urllib.error.URLError):
            return True
        return isinstance(exc, (TimeoutError, ConnectionError, OSError))

    def _backoff(self, attempt: int) -> float:
        """Exponential backoff with full jitter, matching _compute_backoff."""
        return min(self.backoff_cap_seconds, (2 ** attempt) + self._rng.random())

    def complete(self, messages: List[Dict[str, str]], role: str = "unknown",
                 max_tokens: Optional[int] = None) -> LLMResult:
        """Issue one logical chat call, retrying transient failures."""
        effective_max_tokens = int(max_tokens or self.max_tokens)
        last_error = ""
        started = time.time()
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.provider.chat(
                    messages=messages,
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=effective_max_tokens,
                    timeout_seconds=self.timeout_seconds,
                )
                text, finish_reason = extract_message_text(response)
                usage = response.get("usage") or {}
                result = LLMResult(
                    content=text,
                    send_tokens=usage.get("prompt_tokens", 0) or 0,
                    recv_tokens=usage.get("completion_tokens", 0) or 0,
                    total_tokens=usage.get("total_tokens", 0) or 0,
                    finish_reason=finish_reason,
                    attempts=attempt,
                    latency_seconds=time.time() - started,
                )
                if not result.total_tokens:
                    result.total_tokens = result.send_tokens + result.recv_tokens
                self.ledger.record(role, result)
                return result
            except Exception as exc:  # noqa: BLE001 - classified below
                last_error = "%s: %s" % (type(exc).__name__, str(exc)[:400])
                if attempt < self.max_retries and self._is_retryable(exc):
                    wait = self._backoff(attempt)
                    self._log("[llm] retry %d/%d for role=%s after %.1fs (%s)"
                              % (attempt, self.max_retries, role, wait, last_error))
                    time.sleep(wait)
                    continue
                break
        result = LLMResult(content="", error=last_error, attempts=self.max_retries,
                           latency_seconds=time.time() - started)
        self.ledger.record(role, result)
        self._log("[llm] call FAILED for role=%s: %s" % (role, last_error))
        return result
