# SPDX-License-Identifier: Apache-2.0
"""GuardEx real-time telemetry dashboard.

Captures live OTel spans from your real guard.screen() calls and
displays them in a browser UI at http://localhost:7865.

Usage in your application
-------------------------
    # 1. Import and start the dashboard (before creating Guard)
    from guardex.dashboard import start_dashboard
    start_dashboard(port=7865)          # starts Flask in a background thread

    # 2. Use Guard normally - every screen() call appears live
    from guardex import Guard
    guard = Guard()
    result = guard.screen(user_input, gate="input")

Standalone
----------
    python -m guardex.dashboard
    # Open http://localhost:7865 - starts empty, populate by using Guard in your app
"""

from __future__ import annotations
import logging
import pathlib
import socket
import sys
import threading
import time
import warnings
import webbrowser
from collections import deque

_DEPRECATION = (
    "guardex-dashboard is superseded by `guardex-server --ui` and will be "
    "removed in a future release."
)

logger = logging.getLogger(__name__)

_SPAN_BUFFER_SIZE = 10_000

# OTel setup - custom in-process exporter
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult, SimpleSpanProcessor
    from opentelemetry.sdk.resources import Resource
    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False
    SpanExporter = object  # allow _InProcessExporter class definition to parse
    class SpanExportResult:  # type: ignore[no-redef]
        SUCCESS = True

_spans_store: deque[dict] = deque(maxlen=_SPAN_BUFFER_SIZE)
_spans_lock = threading.Lock()
_otel_setup_done = False
_otel_setup_lock = threading.Lock()

class _InProcessExporter(SpanExporter):
    def export(self, spans):
        for s in spans:
            attrs = dict(s.attributes or {})
            dur_ms = round((s.end_time - s.start_time) / 1_000_000, 2)
            with _spans_lock:
                _spans_store.append({
                    "trace_id":   format(s.context.trace_id, "032x"),
                    "span_id":    format(s.context.span_id, "016x"),
                    "name":       s.name,
                    "start_ms":   s.start_time // 1_000_000,
                    "dur_ms":     dur_ms,
                    "status":     s.status.status_code.name,
                    "gate":       attrs.get("guardex.gate", ""),
                    "action":     attrs.get("guardex.action", ""),
                    "safe":       attrs.get("guardex.safe", True),
                    "category":   attrs.get("guardex.category", "") or "",
                    "latency_ms": round(attrs.get("guardex.latency_ms", dur_ms), 2),
                    "pii":        attrs.get("guardex.pii.detected", False),
                    "pii_count":  attrs.get("guardex.pii.count", 0),
                    "request_id": attrs.get("guardex.request_id", ""),
                    "attrs":      attrs,
                })
        return SpanExportResult.SUCCESS

    def shutdown(self): pass

def _install_otel_exporter() -> None:
    """Install the in-process OTel exporter so the dashboard can capture spans.

    Safe to call multiple times. Plays nice with any pre-existing TracerProvider:
    if the process already has a real TracerProvider configured (e.g. by the
    user's own OTel setup), we attach our span processor to it instead of
    replacing it - so user spans continue to flow to their own exporters.
    """
    global _otel_setup_done
    if not _OTEL_AVAILABLE:
        return
    with _otel_setup_lock:
        if _otel_setup_done:
            return
        current = trace.get_tracer_provider()
        processor = SimpleSpanProcessor(_InProcessExporter())
        if isinstance(current, TracerProvider):
            # Real provider already installed - just add our processor.
            current.add_span_processor(processor)
        else:
            # Default ProxyTracerProvider (or similar) - safe to replace.
            resource = Resource(attributes={"service.name": "guardex"})
            provider = TracerProvider(resource=resource)
            provider.add_span_processor(processor)
            trace.set_tracer_provider(provider)
        _otel_setup_done = True

# Flask API
try:
    from flask import Flask, jsonify, send_from_directory
    _FLASK_AVAILABLE = True
except ImportError:
    _FLASK_AVAILABLE = False
    class _FakeFlask:  # type: ignore[no-redef]
        """No-op stub so @app.route decorators parse without flask installed."""
        def __init__(self, *a, **kw): pass
        def route(self, *a, **kw):
            return lambda f: f
        def run(self, *a, **kw):
            raise ImportError(
                "Dashboard requires optional dependencies. "
                "Install with: pip install guardex-ai[dashboard]"
            )
    Flask = _FakeFlask  # type: ignore[misc,assignment]
    def jsonify(*a, **kw): return None  # type: ignore[misc]
    def send_from_directory(*a, **kw): return None  # type: ignore[misc]

# Serve index.html / style.css / app.js from the bundled assets directory.
_ASSETS_DIR = pathlib.Path(__file__).parent / "dashboard_assets"
app = Flask(__name__, static_folder=str(_ASSETS_DIR), static_url_path="/static")

@app.route("/api/traces")
def api_traces():
    with _spans_lock:
        snapshot = list(_spans_store)
    data = list(reversed(snapshot[-200:]))
    return jsonify(data)

@app.route("/api/stats")
def api_stats():
    with _spans_lock:
        spans = list(_spans_store)
    total   = len(spans)
    passed  = sum(1 for s in spans if s["action"] == "pass")
    blocked = sum(1 for s in spans if s["action"] == "block")
    masked  = sum(1 for s in spans if s["action"] == "mask")
    pii     = sum(1 for s in spans if s["pii"])
    lats    = [s["latency_ms"] for s in spans if s["latency_ms"] > 0]
    cats    = {}
    for s in spans:
        c = s["category"]
        if c:
            cats[c] = cats.get(c, 0) + 1
    return jsonify({
        "total": total, "passed": passed, "blocked": blocked, "masked": masked,
        "pii_total": pii,
        "block_rate": round(blocked / total * 100, 1) if total else 0,
        "pii_rate":   round(pii / total * 100, 1) if total else 0,
        "avg_lat":    round(sum(lats) / len(lats), 1) if lats else 0,
        "p95_lat":    round(sorted(lats)[int(len(lats) * 0.95)], 1) if len(lats) > 5 else 0,
        "categories": cats,
        "lat_series": [{"t": s["start_ms"], "v": s["latency_ms"]} for s in spans[-50:]],
    })

@app.route("/api/info")
def api_info():
    """Runtime-resolved dashboard configuration (port, otel version)."""
    otel_version = ""
    try:
        from importlib.metadata import version as _v
        otel_version = _v("opentelemetry-api")
    except Exception:
        otel_version = "unknown"
    return jsonify({
        "port": _APP_PORT,
        "otel_version": otel_version,
        "service_name": "guardex",
    })


@app.route("/")
def index():
    return send_from_directory(str(_ASSETS_DIR), "index.html")


# Set by start_dashboard / _cli before app.run; used by /api/info.
_APP_PORT: int = 7865


# Public API

def _probe_port(port: int, host: str = "127.0.0.1") -> None:
    """Raise OSError synchronously if ``port`` is already bound.

    Flask's ``app.run`` runs in a daemon thread, so a bind failure there
    would die silently. Probing here surfaces the error at call time.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # SO_REUSEADDR on Windows lets bind() succeed on an in-use port,
        # so the probe must request exclusive use there instead.
        if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        s.bind((host, port))
    except OSError as e:
        raise OSError(
            f"Port {port} on {host} is already in use.\n"
            f"  start_dashboard(port=7866)  or  guardex-dashboard --port 7866"
        ) from e
    finally:
        s.close()


def start_dashboard(port: int = 7865, open_browser: bool = True) -> None:
    """Start the GuardEx telemetry dashboard in a background thread.

    Call this ONCE before creating your Guard instance.  Every subsequent
    guard.screen() / guard.ascreen() call will appear live in the browser.

    Parameters
    ----------
    port:
        Local port to serve the dashboard on (default 7865).
    open_browser:
        Automatically open http://localhost:{port} in the default browser.

    Example
    -------
        from guardex.dashboard import start_dashboard
        start_dashboard()

        from guardex import Guard
        guard = Guard()
        result = guard.screen(user_input, gate="input")
    """
    warnings.warn(_DEPRECATION, DeprecationWarning, stacklevel=2)
    if not _OTEL_AVAILABLE or not _FLASK_AVAILABLE:
        raise ImportError(
            "Dashboard requires optional dependencies. "
            "Install with: pip install guardex-ai[dashboard]"
        )

    global _APP_PORT
    _APP_PORT = port
    _probe_port(port)
    _install_otel_exporter()

    def _serve():
        app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)

    t = threading.Thread(target=_serve, daemon=True)
    t.start()

    if open_browser:
        def _open():
            time.sleep(1.0)
            webbrowser.open(f"http://localhost:{port}")
        threading.Thread(target=_open, daemon=True).start()

    logger.info("GuardEx Telemetry Dashboard: http://localhost:%s", port)


# CLI entrypoint (guardex-dashboard command)

def _cli() -> None:
    """Entry point for the ``guardex-dashboard`` CLI command."""
    print(f"DeprecationWarning: {_DEPRECATION}")
    if not _OTEL_AVAILABLE or not _FLASK_AVAILABLE:
        raise SystemExit(
            "Dashboard requires optional dependencies. "
            "Install with: pip install guardex-ai[dashboard]"
        )
    import argparse
    parser = argparse.ArgumentParser(description="GuardEx real-time telemetry dashboard")
    parser.add_argument("--port", type=int, default=7865, help="Port to serve on (default: 7865)")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser automatically")
    args = parser.parse_args()

    global _APP_PORT
    PORT = args.port
    _APP_PORT = PORT
    _probe_port(PORT)
    _install_otel_exporter()
    print("GuardEx Telemetry Dashboard")
    print("=" * 40)
    print(f"Dashboard: http://localhost:{PORT}")
    print()
    print("Integrate into your app:")
    print("  from guardex.dashboard import start_dashboard")
    print("  start_dashboard()")
    print("  guard = Guard()")
    print("  guard.screen(user_input, gate='input')  # appears here live")
    print()
    print("Press Ctrl+C to stop.")

    if not args.no_browser:
        threading.Thread(
            target=lambda: [time.sleep(1), webbrowser.open(f"http://localhost:{PORT}")],
            daemon=True,
        ).start()

    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)


# Standalone entry point
if __name__ == "__main__":
    _cli()
