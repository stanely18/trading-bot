"""Replaceable trading-agent model layer.

The model only reads a prepared snapshot and returns a structured proposal
(schemas/agent-output.schema.json). It never sizes orders in USDT, never calls
the exchange, and is never trusted to enforce risk. Swapping providers must not
require any change to cycle or risk-engine code.
"""
from .base import ModelClient, ModelError, ModelResponse
from .validate import validate_agent_output

__all__ = ['ModelClient', 'ModelError', 'ModelResponse', 'validate_agent_output']
