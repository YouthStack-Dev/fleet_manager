import logging
import sys
import os
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
        
        # Clear all module-level loggers too
        for name in logging.Logger.manager.loggerDict:
            module_logger = logging.getLogger(name)
            for handler in module_logger.handlers[:]:
                module_logger.removeHandler(handler)
        
        # Set log level
        numeric_level = getattr(logging, log_level, logging.DEBUG)
        root_logger.setLevel(numeric_level)
        
        # Create console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        
        # Add request context filter
        request_filter = RequestContextFilter()
        console_handler.addFilter(request_filter)
        
        # Create colored formatter
        formatter = ColoredFormatter(format_string, use_colors=use_colors)
        console_handler.setFormatter(formatter)
        
        # Add handler to root logger
        root_logger.addHandler(console_handler)
        
        root_logger.debug("Logging configured: level=%s colors=%s", log_level, formatter.use_colors)

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.
    """
    logger = logging.getLogger(name)
    logger.handlers = []
    logger.propagate = True
    return logger


setup_logging(force_configure=True)


