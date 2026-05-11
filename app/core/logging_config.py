import asyncio
import logging
import sys
import os
import json
import threading
from collections import deque
from typing import Optional, Set
from datetime import datetime
from zoneinfo import ZoneInfo
from contextvars import ContextVar

# India Standard Time for logging
IST = ZoneInfo("Asia/Kolkata")

# Context variable to store request ID across async context
request_id_ctx: ContextVar[Optional[str]] = ContextVar('request_id', default=None)


class RequestContextFilter(logging.Filter):
    """Filter to add request ID to all log records"""
    
    def filter(self, record):
        # Add request ID from context if available
        record.request_id = request_id_ctx.get() or "--------"
        return True


class ColoredFormatter(logging.Formatter):
    """Custom formatter to add colors to log levels and use IST timestamps"""
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[1;91m',   # Bright Red Bold
        'CRITICAL': '\033[1;95m', # Bright Magenta Bold
        'RESET': '\033[0m'       # Reset
    }
    
    def __init__(self, format_string: str, use_colors: bool = True):
        super().__init__()
        # For terminal environments, be much more aggressive about enabling colors
        self.use_colors = self._should_use_colors(use_colors)
        self.format_string = format_string
        

    
    def _should_use_colors(self, use_colors: bool) -> bool:
        """Simplified color detection - more aggressive for terminals"""
        
        # Explicitly disabled
        if not use_colors:
            return False

        # Force disable colors if explicitly set
        if os.environ.get('NO_COLOR', '').lower() in ('1', 'true', 'yes'):
            return False

        # Force enable colors if explicitly set
        if os.environ.get('FORCE_COLOR', '').lower() in ('1', 'true', 'yes'):
            return True

        # Disable for dumb terminals
        if os.environ.get('TERM') == 'dumb':
            return False

        # Enable colors for all other cases
        return True
    
    def format(self, record):
        if self.use_colors:
            # Add color to the level name
            level_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
            reset_color = self.COLORS['RESET']
            
            # Create colored format string by replacing placeholders
            colored_format = self.format_string.replace(
                '%(levelname)s',
                f'{level_color}%(levelname)s{reset_color}'
            )
            
            # Also color the logger name for better visibility
            colored_format = colored_format.replace(
                '%(name)s',
                f'\033[94m%(name)s{reset_color}'  # Light blue for logger names
            )
            
            # Color the message content based on level
            message_color = level_color
            colored_format = colored_format.replace(
                '%(message)s',
                f'{message_color}%(message)s{reset_color}'
            )
            
            # Create a new formatter instance with the IST converter
            formatter = logging.Formatter(colored_format)
            formatter.converter = lambda *args: datetime.now(IST).timetuple()
        else:
            formatter = logging.Formatter(self.format_string)
            formatter.converter = lambda *args: datetime.now(IST).timetuple()
        
        formatted_message = formatter.format(record)
        
        # Add line gap after each log statement for better readability
        return formatted_message + '\n'

class JsonFormatter(logging.Formatter):
    """
    Structured JSON formatter for production log shipping.

    Each log record is emitted as a single-line JSON object containing:
      timestamp (ISO-8601, UTC), level, logger, message, module, lineno,
      funcName, request_id (from context), and any extra key=value pairs
      added via ``logger.info("msg", extra={"key": "value"})``.

    Usage:
        Only activated when LOG_FORMAT=json env var is set inside setup_logging().
    """

    # Standard LogRecord *instance* attributes (set in LogRecord.__init__ and
    # by logging.Formatter.format).  These must be excluded when collecting
    # user-supplied ``extra={...}`` fields so that we don't accidentally dump
    # the entire LogRecord into every JSON entry.
    # NOTE: logging.LogRecord.__dict__ only contains *class-level* attributes
    # (methods, etc.), NOT instance attributes, so checking against it does
    # not exclude fields like msg, args, levelname, created, thread, …
    _LOGRECORD_INSTANCE_ATTRS: frozenset = frozenset({
        # Core fields set by LogRecord.__init__
        "name", "msg", "args", "created", "filename", "funcName",
        "levelname", "levelno", "lineno", "module", "msecs", "pathname",
        "process", "processName", "relativeCreated", "stack_info",
        "thread", "threadName", "exc_info", "exc_text",
        # Python 3.12+
        "taskName",
        # Set by logging.Formatter.format()
        "message", "asctime",
        # Set by our RequestContextFilter
        "request_id",
    })

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "lineno": record.lineno,
            "funcName": record.funcName,
            "request_id": getattr(record, "request_id", None),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        # Merge only genuine extra fields injected via extra={...}
        for key, value in record.__dict__.items():
            if key not in self._LOGRECORD_INSTANCE_ATTRS and key not in payload:
                try:
                    json.dumps(value)  # only include JSON-serialisable extras
                    payload[key] = value
                except (TypeError, ValueError):
                    payload[key] = str(value)
        return json.dumps(payload, ensure_ascii=False)


class LogStreamHandler(logging.Handler):
    """
    In-process log sink that powers the live-log SSE endpoint.

    Design
    ------
    * Keeps the last ``maxlen`` log entries in a thread-safe ring buffer so
      that new SSE clients can replay recent history before receiving live
      events.
    * Each active SSE subscriber gets its own ``asyncio.Queue``.  When a new
      log record arrives, ``emit()`` puts it into every live queue using
      ``loop.call_soon_threadsafe`` so the call is safe from any thread
      (logging handlers run in the caller's thread, not the event-loop
      thread).
    * The formatter is always ``JsonFormatter`` so the SSE stream is clean,
      structured, and easy to parse regardless of whether the console handler
      is using colours.

    Usage
    -----
    The singleton ``log_stream_handler`` is created at module level and
    attached to the root logger inside ``setup_logging()``.  Import it in the
    route handler::

        from app.core.logging_config import log_stream_handler
    """

    def __init__(self, maxlen: int = 1000) -> None:
        super().__init__()
        self.setFormatter(JsonFormatter())
        self._buffer: deque = deque(maxlen=maxlen)
        self._queues: Set[asyncio.Queue] = set()
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ------------------------------------------------------------------
    # logging.Handler interface
    # ------------------------------------------------------------------

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            entry = (record.levelno, msg)
            with self._lock:
                self._buffer.append(entry)
                loop = self._loop
                queues = list(self._queues)
            if loop and loop.is_running() and queues:
                for q in queues:
                    loop.call_soon_threadsafe(q.put_nowait, entry)
        except Exception:
            self.handleError(record)

    # ------------------------------------------------------------------
    # SSE subscriber management
    # ------------------------------------------------------------------

    def subscribe(self) -> "asyncio.Queue[tuple]":
        """Register a new SSE subscriber and return its queue."""
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        with self._lock:
            try:
                self._loop = asyncio.get_event_loop()
            except RuntimeError:
                pass
            self._queues.add(q)
        return q

    def unsubscribe(self, q: "asyncio.Queue[tuple]") -> None:
        """Remove a subscriber queue (called when the SSE client disconnects)."""
        with self._lock:
            self._queues.discard(q)

    # ------------------------------------------------------------------
    # Buffer access
    # ------------------------------------------------------------------

    def get_buffer(self) -> list:
        """Return a snapshot of the ring buffer as a list of (levelno, json_str) tuples."""
        with self._lock:
            return list(self._buffer)


# Module-level singleton — attached to the root logger in setup_logging().
log_stream_handler = LogStreamHandler(maxlen=1000)


def setup_logging(
    log_level: Optional[str] = None,
    format_string: Optional[str] = None,
    force_configure: bool = False,
    use_colors: bool = True
) -> None:
    """
    Setup logging configuration for the application with colors and formatting.
    """
    
    # Get log level from parameter, environment, or default
    if log_level is None:
        log_level = os.getenv("LOG_LEVEL", "DEBUG").upper()
    
    # Enhanced format string with more structure and Request ID
    if format_string is None:
        format_string = (
            '%(asctime)s │ [%(request_id)s] │ %(name)-20s │ %(levelname)-8s │ '
            '[%(filename)s:%(lineno)d] │ %(funcName)s() │\n'
            '  ➤ %(message)s'
        )
    
    # Configure root logger
    root_logger = logging.getLogger()
    
    # Always clear existing handlers and reconfigure
    if force_configure or not root_logger.handlers:
        # Clear ALL existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Clear all module-level loggers and re-enable any disabled by uvicorn's dictConfig
        for name in logging.Logger.manager.loggerDict:
            module_logger = logging.getLogger(name)
            for handler in module_logger.handlers[:]:
                module_logger.removeHandler(handler)
            # uvicorn's dictConfig sets disable_existing_loggers=True which disables
            # all pre-existing loggers. We must re-enable them here.
            module_logger.disabled = False
        
        # Set log level
        numeric_level = getattr(logging, log_level, logging.DEBUG)
        root_logger.setLevel(numeric_level)
        
        # Create console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        
        # Add request context filter
        request_filter = RequestContextFilter()
        console_handler.addFilter(request_filter)
        
        # Use structured JSON when LOG_FORMAT=json; otherwise use coloured text.
        # This is independent of ENV so you can read human-friendly logs in any
        # environment without having to change ENV.
        use_json = os.getenv("LOG_FORMAT", "text").lower() == "json"
        if use_json:
            console_handler.setFormatter(JsonFormatter())
        else:
            # Create colored formatter
            formatter = ColoredFormatter(format_string, use_colors=use_colors)
            console_handler.setFormatter(formatter)
        
        # Add handler to root logger
        root_logger.addHandler(console_handler)

        # Always attach the in-process stream handler so the SSE endpoint
        # receives every log record regardless of the console format chosen.
        log_stream_handler.setLevel(numeric_level)
        root_logger.addHandler(log_stream_handler)
        
        if use_json:
            root_logger.debug("Logging configured: level=%s format=json", log_level)
        else:
            root_logger.debug("Logging configured: level=%s colors=%s", log_level, formatter.use_colors)

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.
    Propagates to root logger — do NOT clear handlers here; doing so removes
    the single StreamHandler installed by setup_logging() and silences output.
    """
    logger = logging.getLogger(name)
    logger.propagate = True
    logger.disabled = False  # ensure uvicorn's disable_existing_loggers doesn't silence this
    return logger


