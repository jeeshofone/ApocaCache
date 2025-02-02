"""
Monitoring and metrics collection for the ApocaCache library maintainer.
"""

from prometheus_client import Counter, Gauge, start_http_server
import structlog

log = structlog.get_logger()

# Metrics
CONTENT_DOWNLOADS = Counter(
    'apocacache_content_downloads_total',
    'Total number of content downloads',
    ['status', 'language']
)

CONTENT_SIZE = Gauge(
    'apocacache_content_size_bytes',
    'Size of downloaded content in bytes',
    ['name', 'language']
)

UPDATE_DURATION = Gauge(
    'apocacache_update_duration_seconds',
    'Duration of content update operations'
)

LIBRARY_SIZE = Gauge(
    'apocacache_library_size_bytes',
    'Total size of the library in bytes'
)

def setup_monitoring(port: int = 9090):
    """Initialize monitoring server and metrics."""
    try:
        start_http_server(port)
        log.info("monitoring.started", port=port)
    except Exception as e:
        log.error("monitoring.start_failed", error=str(e))

def record_download(status: str, language: str):
    """Record a content download attempt."""
    CONTENT_DOWNLOADS.labels(status=status, language=language).inc()

def update_content_size(name: str, language: str, size_bytes: int):
    """Update the size metric for a content item."""
    CONTENT_SIZE.labels(name=name, language=language).set(size_bytes)

def set_update_duration(duration_seconds: float):
    """Set the duration of the last update operation."""
    UPDATE_DURATION.set(duration_seconds)

def set_library_size(size_bytes: int):
    """Update the total library size metric."""
    LIBRARY_SIZE.set(size_bytes) 