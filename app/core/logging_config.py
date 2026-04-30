import logging
import sys
import os
import json
from typing import Optional
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
        Only activated when ENV == "production" inside setup_logging().
    """

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
        # Merge any extra fields injected via extra={...}
        for key, value in record.__dict__.items():
            if key not in logging.LogRecord.__dict__ and key not in payload:
                try:
                    json.dumps(value)  # only include JSON-serialisable extras
                    payload[key] = value
                except (TypeError, ValueError):
                    payload[key] = str(value)
        return json.dumps(payload, ensure_ascii=False)


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
        
        # In production use structured JSON; in all other environments use coloured text.
        env = os.getenv("ENV", "development")
        if env == "production":
            console_handler.setFormatter(JsonFormatter())
        else:
            # Create colored formatter
            formatter = ColoredFormatter(format_string, use_colors=use_colors)
            console_handler.setFormatter(formatter)
        
        # Add handler to root logger
        root_logger.addHandler(console_handler)
        
        if env == "production":
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


