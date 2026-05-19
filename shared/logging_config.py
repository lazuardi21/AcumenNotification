"""
Shared structured logging configuration using python-json-logger.
"""
import os
import sys
import logging
import datetime
from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter that injects standard fields into every log record."""

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)

        log_record['timestamp'] = datetime.datetime.utcnow().isoformat() + 'Z'
        log_record['level'] = record.levelname
        log_record['service'] = os.environ.get('SERVICE_NAME', 'unknown')
        log_record['logger'] = record.name

        if record.exc_info:
            log_record['exception'] = self.formatException(record.exc_info)

        # Inject trace context if available
        try:
            from opentelemetry import trace
            span = trace.get_current_span()
            ctx = span.get_span_context()
            if ctx.trace_id:
                log_record['trace_id'] = format(ctx.trace_id, '032x')
                log_record['span_id'] = format(ctx.span_id, '016x')
        except Exception:
            pass


def setup_logging(level=None):
    """Configure structured JSON logging for the application.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR). Defaults to LOG_LEVEL env var.
    """
    log_level = level or os.environ.get('LOG_LEVEL', 'INFO')

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(CustomJsonFormatter(
        '%(timestamp)s %(level)s %(service)s %(name)s %(message)s'
    ))

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    root.handlers = [handler]

    # Reduce noise from third-party libs
    logging.getLogger('pika').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('werkzeug').setLevel(logging.WARNING)

    return root
