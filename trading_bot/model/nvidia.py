"""NVIDIA-hosted model client (OpenAI-compatible NIM endpoint).

First concrete implementation of ModelClient. Default model is Kimi K3; any other
NVIDIA-hosted chat model can be selected with `model=` without touching cycle or
risk code. The API key is read from the NVIDIA_API_KEY environment variable
(GitHub Secret in cloud runs) and is never written to logs, files or commits.
"""
import json
import os
import time
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPRedirectHandler

from .base import ModelClient, ModelError, ModelResponse
from .validate import validate_agent_output

DEFAULT_BASE_URL = 'https://integrate.api.nvidia.com/v1'
DEFAULT_MODEL = 'moonshotai/kimi-k3'
_MAX_BYTES = 1_000_000


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        raise ValueError('redirect refused')


class NvidiaKimiClient(ModelClient):
    provider = 'nvidia_nim'

    # Kimi K3 on NVIDIA NIM pins these: top_p must be 0.95 for single-step
    # (non-agentic) calls, and the model's documented profile uses temperature
    # 1.0 with thinking always on. The strict system prompt + schema validation
    # + HOLD fallback keep the structured output safe at that temperature.
    def __init__(self, api_key=None, base_url=DEFAULT_BASE_URL,
                 model=DEFAULT_MODEL, timeout=45, temperature=1.0, top_p=0.95):
        self._key = api_key if api_key is not None else os.environ.get('NVIDIA_API_KEY') or None
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self.top_p = top_p

    @property
    def available(self):
        return bool(self._key)

    def _post(self, payload, timeout):
        body = json.dumps(payload).encode()
        req = Request(self.base_url + '/chat/completions', data=body, method='POST',
                      headers={'Authorization': 'Bearer ' + self._key,
                               'Content-Type': 'application/json',
                               'Accept': 'application/json',
                               'User-Agent': 'trading-bot-poc/0.1'})
        try:
            with build_opener(_NoRedirect).open(req, timeout=timeout) as r:
                raw = r.read(_MAX_BYTES + 1)
        except HTTPError as e:
            # Surface the HTTP status + a short body snippet (never the key) so a
            # failed run's logs say *why* (bad key = 401, bad model = 404, rate
            # limit = 429, bad request = 400, ...).
            try:
                detail = e.read(2000).decode('utf-8', 'replace').strip().replace('\n', ' ')
            except Exception:
                detail = ''
            raise ModelError(f'HTTP {e.code} from {self.provider} for model '
                             f'{self.model!r}: {detail[:400]}') from e
        if len(raw) > _MAX_BYTES:
            raise ValueError('oversized model response')
        return json.loads(raw)

    def evaluate(self, request: dict) -> ModelResponse:
        if not self._key:
            raise ModelError('NVIDIA_API_KEY is not set; refusing to run without an explicit key')
        for field in ('request_id', 'snapshot_hash', 'system_prompt', 'context'):
            if field not in request:
                raise ModelError('request missing field: ' + field)
        deadline_ms = request.get('deadline_ms')
        timeout = max(5, min(self.timeout, deadline_ms / 1000)) if deadline_ms else self.timeout
        payload = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': request['system_prompt']},
                {'role': 'user', 'content': json.dumps(request['context'], sort_keys=True)},
            ],
            'temperature': self.temperature,
            'top_p': self.top_p,
            'max_tokens': 1200,
            'response_format': {'type': 'json_object'},
        }
        started = time.monotonic()
        try:
            data = self._post(payload, timeout)
        except ModelError:
            raise  # already carries HTTP status + body detail
        except Exception as e:  # transport, timeout, decode
            raise ModelError('model call failed: ' + type(e).__name__ + ': ' + str(e)[:200]) from e
        latency_ms = int((time.monotonic() - started) * 1000)
        try:
            content = data['choices'][0]['message']['content']
            output = json.loads(content)
            validate_agent_output(output)
        except Exception as e:
            raise ModelError('model output invalid: ' + type(e).__name__) from e
        return ModelResponse(
            request_id=str(data.get('id') or request['request_id']),
            provider=self.provider,
            model=str(data.get('model') or self.model),
            snapshot_hash=request['snapshot_hash'],
            output=output,
            usage=dict(data.get('usage') or {}),
            latency_ms=latency_ms,
        )

    @classmethod
    def from_env(cls, **kw):
        return cls(**kw)
