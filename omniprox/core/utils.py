"""
Utility functions for OmniProx
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional


def setup_logging(level: str = 'INFO', log_file: Optional[str] = None) -> logging.Logger:
    logger = logging.getLogger('omniprox')
    logger.setLevel(getattr(logging, level.upper()))

    logger.handlers = []

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))

    if sys.stdout.isatty():
        class ColoredFormatter(logging.Formatter):
            COLORS = {
                'DEBUG': '\033[36m',
                'INFO': '\033[32m',
                'WARNING': '\033[33m',
                'ERROR': '\033[31m',
                'CRITICAL': '\033[35m',
                'RESET': '\033[0m'
            }

            def format(self, record):
                log_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
                record.levelname = f"{log_color}{record.levelname}{self.COLORS['RESET']}"
                return super().format(record)

        console_formatter = ColoredFormatter(
            '%(asctime)s - %(levelname)s - %(name)s - %(message)s',
            datefmt='%H:%M:%S'
        )
    else:
        console_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(name)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(name)s - %(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


def check_provider_availability(provider: str) -> bool:
    availability = {
        'gcp': check_gcp_availability,
        'azure': check_azure_availability,
        'az': check_azure_availability,
        'cloudflare': check_cloudflare_availability,
        'cf': check_cloudflare_availability,
        'azure-fd': check_azure_availability,
        'azure-frontdoor': check_azure_availability,
        'gcp-lb': check_gcp_availability,
        'gcp-loadbalancer': check_gcp_availability,
        'alibaba': check_alibaba_availability,
        'aliyun': check_alibaba_availability
    }

    checker = availability.get(provider.lower())
    if checker:
        return checker()
    return False


def check_gcp_availability() -> bool:
    """Check if GCP dependencies are available"""
    try:
        import google.cloud.apigateway_v1
        return True
    except ImportError:
        return False


def check_cloudflare_availability() -> bool:
    """Check if Cloudflare dependencies are available"""
    try:
        import requests
        return True
    except ImportError:
        return False


def check_azure_availability() -> bool:
    """Check if Azure dependencies are available"""
    try:
        import azure.mgmt.containerinstance
        import azure.mgmt.resource
        import azure.identity
        return True
    except ImportError:
        return False


def check_alibaba_availability() -> bool:
    """Check if Alibaba Cloud dependencies are available"""
    # For now, return True as Alibaba SDK is optional
    # Users will get installation instructions if SDK is missing
    return True


def get_available_providers() -> list:
    providers = []
    if check_gcp_availability():
        providers.append('gcp')
        providers.append('gcp-lb')  # Same dependencies as GCP
    if check_azure_availability():
        providers.append('azure')
        providers.append('azure-fd')  # Same base dependencies as Azure
    if check_cloudflare_availability():
        providers.append('cloudflare')
    if check_alibaba_availability():
        providers.append('alibaba')
    return providers


def print_provider_status():
    """Print the status of all available providers"""
    providers = {
        'cloudflare': check_cloudflare_availability(),
        'gcp': check_gcp_availability(),
        'gcp-lb': check_gcp_availability(),
        'azure': check_azure_availability(),
        'azure-fd': check_azure_availability(),
        'alibaba': check_alibaba_availability()
    }

    print("\nProvider Availability Status:")
    print("-" * 40)

    for provider, available in providers.items():
        status = "[OK]" if available else "[X]"
        provider_display = provider.upper().replace('-', ' ')
        print(f"{status} {provider_display}")

    print()


def normalize_url(url: str) -> str:
    """Normalize URL by removing trailing slashes

    Args:
        url: URL to normalize

    Returns:
        str: Normalized URL
    """
    if url and url.endswith('/'):
        return url.rstrip('/')
    return url


def format_timestamp(dt) -> str:
    """Format datetime object to string

    Args:
        dt: Datetime object

    Returns:
        str: Formatted timestamp
    """
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def truncate_text(text: str, max_length: int = 50) -> str:
    """Truncate text to maximum length

    Args:
        text: String to truncate
        max_length: Maximum length

    Returns:
        str: Truncated string
    """
    if len(text) > max_length:
        return text[:max_length-3] + '...'
    return text


def get_unique_suffix(length: int = 6) -> str:
    """Generate a unique suffix for resource names

    Args:
        length: Length of the suffix

    Returns:
        str: Random lowercase alphanumeric string
    """
    import random
    import string
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))
