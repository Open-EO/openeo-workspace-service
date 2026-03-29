"""
Logging configuration.

Configures structlog for structured (JSON in production, pretty-printed in dev)
log output.  Call ``configure_logging()`` once at application startup.
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(debug: bool = False, json_logs: bool | None = None) -> None:
    """
    Set up structlog + stdlib logging integration.

    Args:
        debug:      When True, sets the log level to DEBUG.
        json_logs:  Force JSON output (True) or pretty console (False).
                    Defaults to pretty when ``debug=True``, JSON otherwise.
    """
    use_json = json_logs if json_logs is not None else not debug
    level = logging.DEBUG if debug else logging.INFO

    # ---------------------------------------------------------------- stdlib
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )
    # Quieten noisy third-party loggers
    for noisy in ("elasticsearch", "httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # --------------------------------------------------------------- shared processors
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if use_json:
        # Production: JSON lines
        processors: list[structlog.types.Processor] = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Development: colourised console output
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
