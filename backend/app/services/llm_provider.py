"""LLM Provider abstraction layer.

Supports Ollama (local, free) out of the box.
Swap to OpenAI/Gemini/Azure by changing LLM_PROVIDER env var.
"""

import os
from abc import ABC, abstractmethod
from typing import Optional

import httpx
import structlog
from dotenv import load_dotenv

load_dotenv()

logger = structlog.get_logger(__name__)

# --- Configuration ---

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


# --- Abstract Provider ---


class BaseLLMProvider(ABC):
    """Abstract base for LLM providers."""

    @abstractmethod
    def generate(self, prompt: str, system_prompt: str = "", max_tokens: int = 1024) -> str:
        """Generate a completion from the LLM.

        Args:
            prompt: User prompt/question.
            system_prompt: System instructions.
            max_tokens: Maximum response length.

        Returns:
            Generated text response.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the LLM provider is reachable."""
        ...


# --- Ollama Provider ---


class OllamaProvider(BaseLLMProvider):
    """Local Ollama LLM provider (free, open-source)."""

    def __init__(self, base_url: str = OLLAMA_BASE_URL, model: str = OLLAMA_MODEL):
        self.base_url = base_url
        self.model = model

    def generate(self, prompt: str, system_prompt: str = "", max_tokens: int = 1024) -> str:
        """Generate text using Ollama's API."""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.3,
            },
        }

        try:
            with httpx.Client(timeout=120.0) as client:
                response = client.post(url, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    return data.get("response", "").strip()
                else:
                    logger.error("ollama_generate_failed", status=response.status_code, body=response.text[:200])
                    return f"[LLM Error: Ollama returned {response.status_code}]"
        except httpx.ConnectError:
            return "[LLM Error: Cannot connect to Ollama. Is it running? Start with: ollama serve]"
        except Exception as e:
            logger.error("ollama_error", error=str(e))
            return f"[LLM Error: {e}]"

    def is_available(self) -> bool:
        """Check if Ollama is running and the model is available."""
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.base_url}/api/tags")
                if response.status_code == 200:
                    models = [m["name"] for m in response.json().get("models", [])]
                    # Check if our model (or a variant) is available
                    return any(self.model in m for m in models)
            return False
        except Exception:
            return False


# --- OpenAI Provider (for future enterprise upgrade) ---


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API provider (paid, high quality)."""

    def __init__(self, api_key: str = OPENAI_API_KEY, model: str = OPENAI_MODEL):
        self.api_key = api_key
        self.model = model

    def generate(self, prompt: str, system_prompt: str = "", max_tokens: int = 1024) -> str:
        """Generate text using OpenAI's API."""
        if not self.api_key:
            return "[LLM Error: OpenAI API key not configured]"

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(url, json=payload, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    return data["choices"][0]["message"]["content"].strip()
                else:
                    return f"[LLM Error: OpenAI returned {response.status_code}]"
        except Exception as e:
            return f"[LLM Error: {e}]"

    def is_available(self) -> bool:
        return bool(self.api_key)


# --- Factory ---


def get_llm_provider() -> BaseLLMProvider:
    """Get the configured LLM provider instance.

    Set LLM_PROVIDER env var to switch:
    - "ollama" (default): Local Ollama
    - "openai": OpenAI API
    """
    if LLM_PROVIDER == "openai":
        return OpenAIProvider()
    else:
        return OllamaProvider()


# Singleton instance
_provider: Optional[BaseLLMProvider] = None


def get_llm() -> BaseLLMProvider:
    """Get the singleton LLM provider."""
    global _provider
    if _provider is None:
        _provider = get_llm_provider()
    return _provider
