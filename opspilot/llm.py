"""Model access. Any OpenAI-compatible chat API works (hosted free tiers or a local server)."""
import json
import re
import time
import urllib.error
import urllib.request

from .config import Settings


class LLMError(Exception):
    pass


ATTEMPTS = 4


def retry_after(headers) -> float | None:
    try:
        return min(float(headers.get("Retry-After")), 60)
    except (AttributeError, TypeError, ValueError):
        return None


class ChatClient:
    def __init__(self, settings: Settings, transport=None):
        if not (settings.base_url and settings.model):
            raise ValueError("Set OPSPILOT_BASE_URL and OPSPILOT_MODEL to use a model provider")
        self.s = settings
        self.transport = transport or self._http

    def _http(self, payload: dict) -> dict:
        headers = {"Content-Type": "application/json", "User-Agent": "opspilot"}
        if self.s.api_key:
            headers["Authorization"] = f"Bearer {self.s.api_key}"
        request = urllib.request.Request(
            self.s.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode(), headers=headers)
        for attempt in range(ATTEMPTS):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    return json.load(response)
            except urllib.error.HTTPError as e:
                if e.code not in (429, 500, 502, 503) or attempt == ATTEMPTS - 1:
                    raise LLMError(f"HTTP {e.code} from model API") from e
                # Free tiers limit requests per minute, so wait longer after a 429.
                wait = retry_after(e.headers) or (8 if e.code == 429 else 1) * 2 ** attempt
            except (OSError, ValueError) as e:
                if attempt == ATTEMPTS - 1:
                    raise LLMError(f"Model API unreachable: {type(e).__name__}") from e
                wait = 2 ** attempt
            time.sleep(wait)
        raise LLMError("Model API failed")

    def ask_json(self, system: str, user: str, validate, usage: dict) -> dict:
        """Ask for JSON. If it is invalid, show the model the error once, then give up."""
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        error = ""
        for _ in range(2):
            data = self.transport({"model": self.s.model, "messages": list(messages), "temperature": 0})
            content = ""
            try:
                used = data.get("usage") or {}
                usage["calls"] += 1
                usage["input_tokens"] += used.get("prompt_tokens") or 0
                usage["output_tokens"] += used.get("completion_tokens") or 0
                content = data["choices"][0]["message"]["content"]
                found = re.search(r"\{.*\}", content, re.S)
                if not found:
                    raise ValueError("no JSON object in reply")
                return validate(json.loads(found.group(0)))
            except (AttributeError, KeyError, IndexError, TypeError, ValueError) as e:
                error = str(e)
                if content:
                    messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user",
                                 "content": f"Your last answer was invalid ({error}). Reply with JSON only."})
        raise LLMError(f"Invalid model output: {error}")
