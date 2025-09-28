"""
OmniProx - Multi-cloud HTTP proxy manager
Supports GCP API Gateway, Azure API Management, and Cloudflare Workers
"""

__version__ = "2.0.0"
__author__ = "OmniProx Contributors"

from .core.base import BaseOmniProx
from .core.utils import setup_logging

__all__ = ['BaseOmniProx', 'setup_logging']