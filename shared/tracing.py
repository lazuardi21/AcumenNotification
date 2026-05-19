"""
Shared distributed tracing setup using OpenTelemetry + Jaeger.
"""
import os
import logging

logger = logging.getLogger(__name__)


def init_tracing(app, service_name=None):
    """Initialize OpenTelemetry tracing with Jaeger exporter for a Flask app.

    Args:
        app: Flask application instance
        service_name: Name to identify this service in Jaeger UI
    """
    if not os.environ.get('JAEGER_ENABLED', 'false').lower() == 'true':
        logger.info("Tracing disabled (JAEGER_ENABLED != true)")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.jaeger.thrift import JaegerExporter
        from opentelemetry.instrumentation.flask import FlaskInstrumentor
        from opentelemetry.sdk.resources import Resource

        svc_name = service_name or os.environ.get('SERVICE_NAME', 'unknown-service')
        resource = Resource.create({"service.name": svc_name})

        provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(provider)

        jaeger_exporter = JaegerExporter(
            agent_host_name=os.environ.get('JAEGER_AGENT_HOST', 'jaeger'),
            agent_port=int(os.environ.get('JAEGER_AGENT_PORT', 6831)),
        )
        provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))

        FlaskInstrumentor().instrument_app(app)

        logger.info(f"Tracing initialized for service '{svc_name}' → Jaeger at "
                     f"{os.environ.get('JAEGER_AGENT_HOST')}:{os.environ.get('JAEGER_AGENT_PORT')}")

    except ImportError as e:
        logger.warning(f"OpenTelemetry dependencies not available: {e}")
    except Exception as e:
        logger.error(f"Failed to initialize tracing: {e}")


def get_tracer(name="default"):
    """Get a tracer instance for manual span creation."""
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return None
