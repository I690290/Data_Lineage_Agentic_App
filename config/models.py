"""Bedrock model registry — enum, config dataclass, and factory."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BedrockModel(Enum):
    """Supported Amazon Bedrock model IDs (non-Claude only)."""

    QWEN3_CODER_NEXT = "qwen.qwen3-coder-next"
    DEEPSEEK_R1 = "us.deepseek.r1-v1:0"
    QWEN3_CODER_30B = "qwen.qwen3-coder-30b-a3b-v1:0"
    LLAMA4_SCOUT = "us.meta.llama4-scout-17b-16e-instruct-v1:0"
    # Legacy / embedding models
    NOVA_PRO = "amazon.nova-pro-v1:0"
    NOVA_LITE = "amazon.nova-lite-v1:0"
    NOVA_MICRO = "amazon.nova-micro-v1:0"
    TITAN_EMBED_V2 = "amazon.titan-embed-text-v2:0"


@dataclass
class ModelConfig:
    """Runtime configuration for a single Bedrock model."""

    model_id: str
    max_tokens: int
    temperature: float
    supports_tool_use: bool
    context_window: int


MODEL_REGISTRY: dict[BedrockModel, ModelConfig] = {
    BedrockModel.QWEN3_CODER_NEXT: ModelConfig(
        model_id="qwen.qwen3-coder-next",
        max_tokens=16384,
        temperature=0.1,
        supports_tool_use=True,
        context_window=262144,
    ),
    BedrockModel.DEEPSEEK_R1: ModelConfig(
        model_id="us.deepseek.r1-v1:0",
        max_tokens=8192,
        temperature=0.1,
        supports_tool_use=False,
        context_window=131072,
    ),
    BedrockModel.QWEN3_CODER_30B: ModelConfig(
        model_id="qwen.qwen3-coder-30b-a3b-v1:0",
        max_tokens=8192,
        temperature=0.1,
        supports_tool_use=True,
        context_window=131072,
    ),
    BedrockModel.LLAMA4_SCOUT: ModelConfig(
        model_id="us.meta.llama4-scout-17b-16e-instruct-v1:0",
        max_tokens=8192,
        temperature=0.1,
        supports_tool_use=True,
        context_window=10485760,
    ),
    BedrockModel.NOVA_PRO: ModelConfig(
        model_id="amazon.nova-pro-v1:0",
        max_tokens=5120,
        temperature=0.1,
        supports_tool_use=True,
        context_window=300000,
    ),
    BedrockModel.NOVA_LITE: ModelConfig(
        model_id="amazon.nova-lite-v1:0",
        max_tokens=5120,
        temperature=0.1,
        supports_tool_use=True,
        context_window=300000,
    ),
    BedrockModel.NOVA_MICRO: ModelConfig(
        model_id="amazon.nova-micro-v1:0",
        max_tokens=5120,
        temperature=0.1,
        supports_tool_use=True,
        context_window=128000,
    ),
    BedrockModel.TITAN_EMBED_V2: ModelConfig(
        model_id="amazon.titan-embed-text-v2:0",
        max_tokens=8192,
        temperature=0.0,
        supports_tool_use=False,
        context_window=8192,
    ),
}

# Keep backward-compat constants for code that still imports BedrockModels
class BedrockModels:
    """Legacy constant class — prefer BedrockModel enum for new code."""

    TITAN_EMBED_V2: str = BedrockModel.TITAN_EMBED_V2.value
    NOVA_MICRO: str = BedrockModel.NOVA_MICRO.value
    NOVA_LITE: str = BedrockModel.NOVA_LITE.value
    NOVA_PRO: str = BedrockModel.NOVA_PRO.value
    FALLBACK_CLASSIFICATION: str = "amazon.titan-text-lite-v1"
    FALLBACK_GENERATION: str = "amazon.titan-text-premier-v1:0"


def get_model_config(model_id: str) -> ModelConfig:
    """Return ModelConfig for a given model ID string.

    Args:
        model_id: The Bedrock model ID string (e.g. ``"qwen.qwen3-coder-next"``).

    Returns:
        The matching ModelConfig or a sensible default if the model ID is unknown.
    """
    for model_enum, config in MODEL_REGISTRY.items():
        if config.model_id == model_id:
            return config
    # Return a safe default for unknown models
    return ModelConfig(
        model_id=model_id,
        max_tokens=4096,
        temperature=0.1,
        supports_tool_use=True,
        context_window=128000,
    )
