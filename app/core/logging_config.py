import logging
import sys
import os
from typing import Optional

class ColoredFormatter(logging.Formatter):
    """Custom formatter to add colors to log levels"""
    
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
        
        # Debug color detection with a simple test
        if self.use_colors:
            print(f"\033[32m🎨 COLORS ENABLED\033[0m - Testing: \033[31mRED\033[0m \033[33mYELLOW\033[0m \033[36mCYAN\033[0m", flush=True)
        else:
            print("🎨 COLORS DISABLED", flush=True)
        
    def _should_use_colors(self, use_colors: bool) -> bool:
        """Simplified color detection - more aggressive for terminals"""
        
        # Explicitly disabled
        if not use_colors:
            return False
            
        # Force disable colors if explicitly set
        if os.environ.get('NO_COLOR', '').lower() in ('1', 'true', 'yes'):
            print("🎨 Colors DISABLED via NO_COLOR environment variable", flush=True)
            return False
        
        # Force enable colors if explicitly set
        if os.environ.get('FORCE_COLOR', '').lower() in ('1', 'true', 'yes'):
            print("🎨 Colors FORCED via FORCE_COLOR environment variable", flush=True)
            return True
            
        # For most terminals and environments, just enable colors
        # This is more aggressive - assume colors work unless proven otherwise
        
        # Check if we're in a known non-color environment
        if os.environ.get('TERM') == 'dumb':
            print("🎨 Colors DISABLED - TERM=dumb", flush=True)
            return False
            
        # Enable colors for all other cases (be optimistic)
        print("🎨 Colors ENABLED - terminal environment detected", flush=True)
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
            
            formatter = logging.Formatter(colored_format)
        else:
            formatter = logging.Formatter(self.format_string)
        
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
    
    # Enhanced format string with more structure
    if format_string is None:
        format_string = (
            '%(asctime)s │ %(name)-20s │ %(levelname)-8s │ '
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
        
        # Create colored formatter
        formatter = ColoredFormatter(format_string, use_colors=use_colors)
        console_handler.setFormatter(formatter)
        
        # Add handler to root logger
        root_logger.addHandler(console_handler)
        
        # Print setup message with direct color codes (not through logger yet)
        if formatter.use_colors:
            print(f"\n\033[32m🚀 LOGGING SETUP: Configured with level {log_level} (numeric: {numeric_level}) - Colors: Enabled\033[0m\n", 
                  file=sys.stdout, flush=True)
        else:
            print(f"\n🚀 LOGGING SETUP: Configured with level {log_level} (numeric: {numeric_level}) - Colors: Disabled\n", 
                  file=sys.stdout, flush=True)
        
        # Test the logger immediately with different levels to show colors
        root_logger.debug("🔧 Debug logging is enabled")
        root_logger.info("✅ Root logger configured successfully")
        root_logger.warning("⚠️  Warning level logging is active")
        root_logger.error("❌ Error level logging test (this is just a test)")

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.
    """
    logger = logging.getLogger(name)
    # Ensure it inherits from root logger and doesn't have its own handlers
    logger.handlers = []
    logger.propagate = True
    
    # Test log immediately with direct color output
    print(f"\033[94m📝 LOGGER CREATED: {name}\033[0m\n", file=sys.stdout, flush=True)
    
    return logger

# Test colors immediately when module loads
print(f"\n\033[36m🔄 IMPORTING LOGGING CONFIG\033[0m", file=sys.stdout, flush=True)
print(f"Color test: \033[32mGREEN\033[0m \033[33mYELLOW\033[0m \033[31mRED\033[0m \033[36mCYAN\033[0m", flush=True)

setup_logging(force_configure=True)
print(f"\033[32m✅ LOGGING CONFIG IMPORTED\033[0m\n", file=sys.stdout, flush=True)
