"""Model-client contract. Concrete clients (NVIDIA/Kimi, future NVIDIA-hosted
models) implement `evaluate`; trading and risk code depend only on this ABC."""
from abc import ABC, abstractmethod


class ModelError(RuntimeError):
    """Raised for a missing key, timeout, transport failure, malformed output or
    schema-invalid output. The caller must treat this as 'no proposal' and fall
    back to HOLD; a client must never silently substitute another provider."""


class ModelResponse(dict):
    """Response shaped like schemas/model-response.schema.json:
    request_id, provider, model, snapshot_hash, output, usage, latency_ms.
    `output` conforms to schemas/agent-output.schema.json."""


class ModelClient(ABC):
    provider = 'unset'

    @abstractmethod
    def evaluate(self, request: dict) -> ModelResponse:
        """request: request_id, model, snapshot_hash, system_prompt, context, deadline_ms.
        Returns a ModelResponse or raises ModelError. No side effects, no retries
        that could change the experiment's fixed conditions."""
        raise NotImplementedError
