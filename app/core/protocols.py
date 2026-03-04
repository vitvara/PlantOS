"""
Structural-typing contracts (Protocols) for PlantOS.

These interfaces use ``typing.Protocol`` — Python's structural subtyping
mechanism.  A class satisfies a Protocol by having the right methods;
it does **not** need to inherit from it.  This keeps the codebase
compositional (functional-style) rather than relying on inheritance chains.

Why Protocols instead of ABC?
------------------------------
* Any object with the correct interface satisfies the contract — including
  ``MagicMock`` / ``AsyncMock`` in tests, without any extra boilerplate.
* Implementations live in separate modules; this file is pure interface
  definitions with zero business logic.
* ``runtime_checkable`` lets you use ``isinstance()`` guards when needed.

Defined here
------------
``RepositoryProtocol[T, PK]``
    Minimal read interface shared by every repository.

``AIProviderProtocol``
    Strategy interface for LLM calls — swap OpenAI for any other
    provider (Anthropic, Gemini, local model) without touching services.

``OpenAIProvider``
    Concrete ``AIProviderProtocol`` backed by the OpenAI Python SDK.
    Constructed by :class:`~app.core.factory.ServiceFactory` and
    injected into services at startup.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, TypeVar, runtime_checkable

T  = TypeVar("T")   # ORM model type
PK = TypeVar("PK")  # Primary key type (int, str, …)


# ---------------------------------------------------------------------------
# Repository Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class RepositoryProtocol(Protocol[T, PK]):
    """
    Minimal read contract that every repository must satisfy.

    Repositories may expose additional domain-specific methods beyond
    these two, but anything that depends *only* on reading entities should
    type-hint against this Protocol for maximum flexibility.

    Type parameters
    ---------------
    T:  ORM model class (e.g. ``Plant``, ``SensorData``).
    PK: Primary key type, usually ``int``.
    """

    def get_by_id(self, pk: PK) -> Optional[T]:
        """Return the entity with primary key *pk*, or ``None``."""
        ...

    def list_all(self) -> list[T]:
        """Return all entities in the store, newest-first."""
        ...


# ---------------------------------------------------------------------------
# AI Provider Protocol  (Strategy pattern)
# ---------------------------------------------------------------------------

@runtime_checkable
class AIProviderProtocol(Protocol):
    """
    Strategy interface for LLM chat-completion calls.

    Decouples services from the OpenAI SDK so that:

    * Tests can pass a lightweight ``AsyncMock`` without patching at the
      module level.
    * The provider can be swapped (Anthropic, Gemini, Azure OpenAI, a
      local Ollama instance) purely through :class:`ServiceFactory` —
      zero service code changes required.

    Contract
    --------
    ``complete`` receives a fully-formed OpenAI-compatible ``messages``
    list and any additional keyword arguments supported by the underlying
    chat-completions API (e.g. ``max_tokens``, ``response_format``).
    It returns the raw text content of the first choice.
    """

    async def complete(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> str:
        """
        Execute a chat-completion request and return the response text.

        Args:
            messages: OpenAI-compatible message list, e.g.
                      ``[{"role": "user", "content": [...]}]``.
            **kwargs: Passed verbatim to the underlying API call
                      (``max_tokens``, ``response_format``, ``temperature``…).

        Returns:
            The ``content`` string of the first choice.

        Raises:
            Any provider-specific exception on network/API failure.
            Callers are responsible for wrapping in domain exceptions.
        """
        ...


# ---------------------------------------------------------------------------
# OpenAI concrete implementation
# ---------------------------------------------------------------------------

class OpenAIProvider:
    """
    Concrete :class:`AIProviderProtocol` backed by the ``openai`` Python SDK.

    Constructed once per request by :class:`~app.core.factory.ServiceFactory`
    and injected into services that need AI capabilities.

    Args:
        api_key: OpenAI API key (read from ``settings.OPENAI_API_KEY``).
        model:   Model identifier, e.g. ``"gpt-4.1"`` or ``"gpt-4o"``.

    Example::

        provider = OpenAIProvider(api_key="sk-…", model="gpt-4o")
        text = await provider.complete(
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=100,
        )
    """

    def __init__(self, api_key: str, model: str) -> None:
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(api_key=api_key)
        self._model  = model

    async def complete(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> str:
        """
        Call the OpenAI chat-completions endpoint.

        Args:
            messages: Message list forwarded verbatim to the API.
            **kwargs: Extra parameters (``max_tokens``, ``response_format``…).

        Returns:
            The text content of ``choices[0].message.content``.

        Raises:
            openai.OpenAIError: On API or network failure.
        """
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            **kwargs,
        )
        return response.choices[0].message.content or ""
