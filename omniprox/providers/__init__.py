"""
OmniProx provider modules
"""

__all__ = []

try:
    from .gcp import GCPProvider
    __all__.append('GCPProvider')
except ImportError:
    pass

try:
    from .azure import AzureProvider
    __all__.append('AzureProvider')
except ImportError:
    pass

try:
    from .cloudflare import CloudflareProvider
    __all__.append('CloudflareProvider')
except ImportError:
    pass