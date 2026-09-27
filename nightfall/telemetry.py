"""OpenTelemetry traces and metrics for a session.

Telemetry is off unless an exporter is configured, so the usual case costs one
environment lookup and imports nothing. Where it is on, a session is traced the
way it actually runs: a span per turn, one per model call, one per tool call,
and counters for the tokens and the tools.

What is never recorded: prompts, replies, tool arguments, tool output or file
contents. Only names, counts and sizes. A coding agent's telemetry should not
be the one place its secrets are not.

Nothing in here may raise into the agent loop. A broken exporter loses data;
it does not end the session.
"""

import os
import sys
from contextlib import contextmanager

# OTEL_EXPORTER_OTLP_ENDPOINT switches telemetry on by itself, the way every
# other OTel-instrumented program does. NIGHTFALL_TELEMETRY is the explicit
# switch, and "console" prints spans to the terminal instead of shipping them.
SWITCH = "NIGHTFALL_TELEMETRY"
SERVICE = "nightfall"

_complained = False


def _complain(reason):
    """Say once, quietly, why there is no telemetry."""
    global _complained
    if _complained:
        return
    _complained = True
    try:
        from .ui import ui

        ui.note(f"telemetry off: {reason}")
    except Exception:  # noqa: BLE001 - the warning must not become the failure
        print(f"telemetry off: {reason}", file=sys.stderr)


class _NullSpan:
    """The slice of the span API the call sites in this repo use."""

    def __enter__(self):
        return self

    def __exit__(self, *error):
        return False

    def set_attribute(self, *args, **kwargs):
        return self

    set_attributes = set_attribute
    add_event = set_attribute
    record_exception = set_attribute
    set_status = set_attribute
    end = set_attribute


class _NullTracer:
    def start_as_current_span(self, *args, **kwargs):
        return _NullSpan()


class _NullCounter:
    def add(self, *args, **kwargs):
        return None


class _NullMeter:
    def create_counter(self, *args, **kwargs):
        return _NullCounter()


def _load_env_file():
    """Let ~/.agents/env land in the environment before we read it."""
    try:
        from . import config  # noqa: F401  - importing it is the whole point
    except KeyError:
        pass  # no endpoint configured; that is config's problem, not ours


def _version():
    try:
        from importlib.metadata import version

        return version("nightfall-cli")
    except Exception:  # noqa: BLE001 - running from a source tree without an install
        return "0.0.0"


def _setup():
    """Return the tracer, the meter and the providers to shut down at the end."""
    _load_env_file()

    mode = os.environ.get(SWITCH, "").strip().lower()
    if not mode and not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return _NullTracer(), _NullMeter(), []

    try:
        from opentelemetry import metrics, trace
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
            SimpleSpanProcessor,
        )
    except ImportError as missing:
        _complain(f"{missing} - install it with: uv pip install 'nightfall-cli[otel]'")
        return _NullTracer(), _NullMeter(), []

    console = mode == "console"
    resource = Resource.create(
        {
            "service.name": os.environ.get("OTEL_SERVICE_NAME", SERVICE),
            "service.version": _version(),
        }
    )

    trace_provider = TracerProvider(resource=resource)
    if console:
        trace_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    else:
        # An unreachable collector must not hold the terminal hostage on the
        # way out, so the exporter gets five seconds to give up.
        os.environ.setdefault("OTEL_BSP_EXPORT_TIMEOUT", "5000")
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            trace_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        except ImportError as missing:
            _complain(f"no OTLP exporter ({missing}) - install 'nightfall-cli[otel]'")
    trace.set_tracer_provider(trace_provider)

    meter_provider = MeterProvider(resource=resource)
    if not console:
        try:
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
                OTLPMetricExporter,
            )
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

            meter_provider.add_metric_reader(
                PeriodicExportingMetricReader(OTLPMetricExporter())
            )
        except ImportError as missing:
            _complain(f"no OTLP metric exporter ({missing})")
    metrics.set_meter_provider(meter_provider)

    return (
        trace.get_tracer(SERVICE),
        metrics.get_meter(SERVICE),
        [trace_provider, meter_provider],
    )


tracer, meter, _PROVIDERS = _setup()

turns = meter.create_counter("nightfall.turns", description="User turns handled")
tool_calls = meter.create_counter(
    "nightfall.tool.calls", description="Tool calls attempted"
)
tokens = meter.create_counter(
    "nightfall.llm.tokens", description="Tokens billed by the model", unit="{token}"
)
errors = meter.create_counter("nightfall.errors", description="Model or tool failures")


class Span:
    """A span the caller closes itself, for the loops that would rather not
    re-indent themselves. `span()` below is the normal way in."""

    def __init__(self, name, **attributes):
        self.name = name
        self._attributes = attributes
        try:
            self._manager = tracer.start_as_current_span(name)
        except Exception as failure:  # noqa: BLE001
            _complain(f"tracer refused a span ({failure})")
            self._manager = _NullSpan()

    def __enter__(self):
        try:
            self._span = self._manager.__enter__()
            if self._attributes:
                self._span.set_attributes(self._attributes)
        except Exception as failure:  # noqa: BLE001
            # A span that will not start is a trace with a hole in it, which is
            # worth complaining about and not worth ending a session over.
            _complain(f"span {self.name} would not start ({failure})")
            self._span = _NullSpan()
        return self._span

    def __exit__(self, *error):
        try:
            return self._manager.__exit__(*error)
        except Exception as failure:  # noqa: BLE001
            _complain(f"span {self.name} would not close ({failure})")
            return False


@contextmanager
def span(name, **attributes):
    """Run a block inside a span. The block's exceptions are not ours to eat."""
    with Span(name, **attributes) as open_span:
        yield open_span


def count(counter, value=1, attributes=None):
    """Add to a counter, if there is one and if the number is real."""
    if not value:
        return
    try:
        counter.add(value, attributes or {})
    except Exception as failure:  # noqa: BLE001
        _complain(f"counter dropped a measurement ({failure})")


def shutdown():
    """Flush and stop. A session that exits without this sends nothing."""
    for provider in _PROVIDERS:
        try:
            provider.shutdown()
        except Exception as failure:  # noqa: BLE001
            _complain(f"exporter did not close cleanly ({failure})")
