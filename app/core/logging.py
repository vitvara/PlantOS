"""
Structured JSON logging for PlantOS.

Provides a thin wrapper around the stdlib ``logging`` module that emits
every log record as a single-line JSON object — suitable for Datadog,
CloudWatch, Loki, or any line-oriented log aggregator.

Typical usage
-------------
Module-level logger (preferred)::

    from app.core.logging import get_logger
    logger = get_logger(__name__)

    logger.info("Plant registered", plant_id=42, device_id="esp-01")
    logger.error("OpenAI call failed", error=str(exc), plant_id=42)

Decorator — logs entry, exit, duration and any exception::

    from app.core.logging import log_call, get_logger
    logger = get_logger(__name__)

    @log_call(logger)
    async def identify_species(self, plant_id: int) -> Plant: ...

    # Emits:
    #   {"ts":"…","level":"INFO","logger":"…","msg":"PlantService.identify_species.start"}
    #   {"ts":"…","level":"INFO","logger":"…","msg":"PlantService.identify_species.ok","duration_ms":412.3}

Configuration
-------------
Call ``configure_logging(debug=False)`` once at application startup
(see ``app/lifespan.py``).  All subsequent ``get_logger()`` calls share
the same root handler without any further setup.
"""

from __future__ import annotations

import functools
import inspect
import json
import logging
import time
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------

class JSONFormatter(logging.Formatter):
    """
    Renders every ``LogRecord`` as a compact JSON line.

    Fields always present
    ~~~~~~~~~~~~~~~~~~~~~
    ``ts``     ISO-8601 timestamp (local time).
    ``level``  Log level name (INFO, WARNING, ERROR, …).
    ``logger`` Logger name (usually ``__name__`` of the caller).
    ``msg``    Human-readable message.

    Additional keyword arguments passed to :class:`StructuredLogger` methods
    are merged into the JSON payload at the top level.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts":     self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level":  record.levelname,
            "logger": record.name,
            "msg":    record.getMessage(),
        }
        # Extra keyword context attached by StructuredLogger._emit
        extra = getattr(record, "_kw", None)
        if extra:
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


# ---------------------------------------------------------------------------
# Structured logger
# ---------------------------------------------------------------------------

class StructuredLogger:
    """
    Thin, keyword-friendly wrapper around a stdlib ``logging.Logger``.

    Unlike the stdlib logger, keyword arguments are serialised as top-level
    JSON fields rather than buried in the message string::

        logger.info("Sensor ingested", device_id="esp-01", temperature=24.5)
        # → {"ts":"…","level":"INFO",…,"msg":"Sensor ingested",
        #     "device_id":"esp-01","temperature":24.5}

    Args:
        name: Logger name — pass ``__name__`` for automatic module routing.
    """

    def __init__(self, name: str) -> None:
        self._log = logging.getLogger(name)

    # ------------------------------------------------------------------
    # Internal emit helper
    # ------------------------------------------------------------------

    def _emit(self, level: int, msg: str, **kw: Any) -> None:
        if not self._log.isEnabledFor(level):
            return
        record = self._log.makeRecord(
            name=self._log.name,
            level=level,
            fn="",
            lno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )
        record._kw = kw  # type: ignore[attr-defined]
        self._log.handle(record)

    # ------------------------------------------------------------------
    # Public API — mirrors stdlib logging levels
    # ------------------------------------------------------------------

    def debug(self, msg: str, **kw: Any) -> None:
        """Emit a DEBUG-level structured log entry."""
        self._emit(logging.DEBUG, msg, **kw)

    def info(self, msg: str, **kw: Any) -> None:
        """Emit an INFO-level structured log entry."""
        self._emit(logging.INFO, msg, **kw)

    def warning(self, msg: str, **kw: Any) -> None:
        """Emit a WARNING-level structured log entry."""
        self._emit(logging.WARNING, msg, **kw)

    def error(self, msg: str, **kw: Any) -> None:
        """Emit an ERROR-level structured log entry."""
        self._emit(logging.ERROR, msg, **kw)

    def critical(self, msg: str, **kw: Any) -> None:
        """Emit a CRITICAL-level structured log entry."""
        self._emit(logging.CRITICAL, msg, **kw)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_logger(name: str) -> StructuredLogger:
    """
    Return a :class:`StructuredLogger` bound to *name*.

    Idiomatic usage at module level::

        logger = get_logger(__name__)

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        A :class:`StructuredLogger` instance.
    """
    return StructuredLogger(name)


# ---------------------------------------------------------------------------
# @log_call decorator
# ---------------------------------------------------------------------------

def log_call(logger: StructuredLogger) -> Callable[[F], F]:
    """
    Decorator factory — wrap a function with structured entry/exit logging.

    Supports both ``async def`` and regular ``def`` functions.
    The decorated function's qualified name (``__qualname__``) is used as
    the event prefix so log entries are automatically namespaced::

        @log_call(logger)
        async def identify_species(self, plant_id: int) -> Plant: ...

        # Emits on entry:
        #   {"msg":"PlantService.identify_species.start","plant_id_arg_count":2}
        # Emits on success:
        #   {"msg":"PlantService.identify_species.ok","duration_ms":314.2}
        # Emits on exception:
        #   {"msg":"PlantService.identify_species.error","error":"...","duration_ms":12.1}
        #   (exception is re-raised unchanged)

    Args:
        logger: A :class:`StructuredLogger` instance to write entries to.

    Returns:
        A decorator that wraps the target callable.

    Raises:
        Any exception raised by the wrapped function — this decorator never
        swallows exceptions.
    """

    def decorator(fn: F) -> F:
        is_async = inspect.iscoroutinefunction(fn)
        fname = fn.__qualname__

        if is_async:
            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                t0 = time.perf_counter()
                logger.info(f"{fname}.start")
                try:
                    result = await fn(*args, **kwargs)
                    logger.info(f"{fname}.ok",
                                duration_ms=round((time.perf_counter() - t0) * 1000, 1))
                    return result
                except Exception as exc:
                    logger.error(f"{fname}.error",
                                 error=str(exc),
                                 duration_ms=round((time.perf_counter() - t0) * 1000, 1))
                    raise

            return async_wrapper  # type: ignore[return-value]

        else:
            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                t0 = time.perf_counter()
                logger.info(f"{fname}.start")
                try:
                    result = fn(*args, **kwargs)
                    logger.info(f"{fname}.ok",
                                duration_ms=round((time.perf_counter() - t0) * 1000, 1))
                    return result
                except Exception as exc:
                    logger.error(f"{fname}.error",
                                 error=str(exc),
                                 duration_ms=round((time.perf_counter() - t0) * 1000, 1))
                    raise

            return sync_wrapper  # type: ignore[return-value]

    return decorator  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Startup configuration
# ---------------------------------------------------------------------------

def configure_logging(debug: bool = False) -> None:
    """
    Configure the root logging handler for the application.

    Must be called **once** at application startup (in ``lifespan``).
    Subsequent calls are safe but replace the existing handler.

    Args:
        debug: When ``True`` the root level is set to DEBUG; otherwise INFO.

    Example::

        # app/lifespan.py
        from app.core.logging import configure_logging
        configure_logging(debug=settings.debug)
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if debug else logging.INFO)
