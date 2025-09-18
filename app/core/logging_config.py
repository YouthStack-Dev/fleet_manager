import logging
import sys
import os
from typing import Optional

def setup_logging(
    log_level: Optional[str] = None,
    format_string: Optional[str] = None,
    force_configure: bool = False
) -> None:
    """
    Setup logging configuration for the application.
    """
    
    # Get log level from parameter, environment, or default
    if log_level is None:
        log_level = os.getenv("LOG_LEVEL", "DEBUG").upper()
    
    # Default format string
    if format_string is None:
        format_string = (
            '%(asctime)s - %(name)s - %(levelname)s - '
            '[%(filename)s:%(lineno)d] - %(funcName)s() - %(message)s'
        )
    
    # Configure root logger
    root_logger = logging.getLogger()
    
    # Always clear existing handlers and reconfigure for Docker
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
        
        # Create console handler for Docker stdout
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        
        # Create formatter
        formatter = logging.Formatter(format_string)
        console_handler.setFormatter(formatter)
        
        # Add handler to root logger
        root_logger.addHandler(console_handler)
        
        # Force immediate output
        print(f"LOGGING SETUP: Configured with level {log_level} (numeric: {numeric_level})", file=sys.stdout, flush=True)
        
        # Test the logger immediately
        root_logger.info("Root logger configured successfully")

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.
    """
    logger = logging.getLogger(name)
    # Ensure it inherits from root logger and doesn't have its own handlers
    logger.handlers = []
    logger.propagate = True
    
    # Test log immediately
    print(f"LOGGER CREATED: {name}", file=sys.stdout, flush=True)
    
    return logger

# Initialize logging when module is imported
print("IMPORTING LOGGING CONFIG", file=sys.stdout, flush=True)
setup_logging(force_configure=True)
print("LOGGING CONFIG IMPORTED", file=sys.stdout, flush=True)
