"""Extension contracts. Models receive snapshots only; no DB paths or broker credentials."""
from typing import Protocol

class ProposalAgent(Protocol):
    def propose(self, context: dict) -> dict:
        """Return schemas/proposal.schema.json, including observed revision; no side effects."""
        ...

class RemoteModelTool(Protocol):
    def evaluate(self, request: dict) -> dict:
        """request: request_id, role, model, snapshot_hash, context, deadline_ms.
        response: request_id, provider, model, snapshot_hash, output, usage, latency_ms.
        Timeout/malformed/unavailable => error, never silently substitute a provider.
        """
        ...

class StateBackend(Protocol):
    def read(self) -> dict: ...
    def submit(self, proposal: dict) -> dict:
        """Server fetches trusted market and invokes RiskGateway in an atomic transaction.
        Caller cannot supply price, policy, portfolio, execution mode or DB paths.
        """
        ...
