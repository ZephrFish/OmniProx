"""
Base class for OmniProx providers
Handles common functionality across all cloud providers
"""

import configparser
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Optional
import tldextract
import datetime


class BaseOmniProx(ABC):
    """Abstract base class for OmniProx providers"""

    def __init__(self, provider_name: str, args: Any):
        """Initialize base provider

        Args:
            provider_name: Name of the cloud provider (gcp, azure, cloudflare)
            args: Command line arguments namespace
        """
        self.provider = provider_name
        self.args = args
        self.profile = getattr(args, 'profile', 'default')
        self.logger = logging.getLogger(f'omniprox.{provider_name}')
        self.config_path = Path.home() / '.omniprox' / 'profiles.ini'

        # Extract command arguments
        self.command = getattr(args, 'command', None)
        self.url = getattr(args, 'url', None)
        self.api_id = getattr(args, 'api_id', None)
        self.auto_create = getattr(args, 'auto_create', False)

        # Load profile configuration
        self.logger.debug(f"Loading profile '{self.profile}' for {self.provider}")
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        config = configparser.ConfigParser()
        if self.config_path.exists():
            config.read(self.config_path)

        profile_name = f"{self.provider}:{self.profile}"

        if profile_name not in config:
            self.logger.info(f"Profile '{self.profile}' not found, creating new profile")
            print(f"Creating new profile '{self.profile}' for {self.provider.upper()}...")
            self.create_profile(config, profile_name)
        else:
            self.logger.info(f"Loading existing profile '{self.profile}'")
            print(f"Loading profile '{self.profile}' for {self.provider.upper()}...")
            self.load_profile(config, profile_name)

    @abstractmethod
    def create_profile(self, config: configparser.ConfigParser, profile_name: str):
        pass

    @abstractmethod
    def load_profile(self, config: configparser.ConfigParser, profile_name: str):
        pass

    def save_profile(self, config: configparser.ConfigParser):
        self.logger.debug(f"Saving profile to {self.config_path}")
        with open(self.config_path, 'w') as f:
            config.write(f)
        self.logger.info(f"Profile saved successfully")

    @abstractmethod
    def init_provider(self):
        """Initialize provider-specific resources"""
        pass

    def execute(self):
        """Execute the requested command"""
        self.logger.info(f"Executing command: {self.command}")

        command_map = {
            'create': self.create,
            'list': self.list,
            'delete': self.delete,
            'update': self.update,
            'status': self.status,
            'usage': self.usage,
            'cleanup': self.cleanup,
            'proxytest': self.proxytest
        }

        if self.command in command_map:
            try:
                result = command_map[self.command]()
                self.logger.info(f"Command '{self.command}' completed successfully")
                return result
            except Exception as e:
                self.logger.error(f"Command '{self.command}' failed: {e}", exc_info=True)
                raise
        else:
            self.logger.error(f"Unsupported command: {self.command}")
            print(f"Unsupported command for {self.provider}: {self.command}")
            return False

    @abstractmethod
    def create(self):
        pass

    @abstractmethod
    def list(self):
        """List all proxies"""
        pass

    @abstractmethod
    def delete(self):
        """Delete a proxy"""
        pass

    def update(self):
        """Update a proxy (optional)"""
        self.logger.warning(f"Update command not implemented for {self.provider}")
        print(f"Update command is not supported for {self.provider}")
        return False

    def status(self):
        """Check provider status (optional)"""
        self.logger.warning(f"Status command not implemented for {self.provider}")
        print(f"Status command is not supported for {self.provider}")
        return False

    def usage(self):
        """Check usage/billing information (optional)"""
        self.logger.warning(f"Usage command not implemented for {self.provider}")
        print(f"Usage command is not supported for {self.provider}")
        return False

    def proxytest(self):
        """Test proxy creation and IP rotation validation"""
        import time
        import requests
        import random
        import string

        print(f"\n{'='*60}")
        print(f"Proxy Test for {self.provider.upper()}")
        print(f"{'='*60}")
        print(f"Testing IP rotation with ipinfo.io/ip")

        test_url = "https://ipinfo.io/ip"
        test_count = 3
        created_proxies = []

        try:
            # Create test proxies
            print(f"\nStep 1: Creating {test_count} test proxies...")
            original_url = self.url
            self.url = test_url

            for i in range(test_count):
                print(f"  Creating proxy {i+1}/{test_count}...")

                # Temporarily override create behavior for testing
                if hasattr(self, '_create_single_proxy'):
                    result = self._create_single_proxy()
                else:
                    result = self.create()

                if result:
                    # Try to get the created proxy URL - this is provider-specific
                    proxy_url = self._get_last_created_proxy_url()
                    if proxy_url:
                        created_proxies.append(proxy_url)
                        print(f"    [OK] Created: {proxy_url}")
                    else:
                        print(f"    [WARNING] Created but couldn't get URL")
                else:
                    print(f"    [FAILED] Creation failed")

                # Small delay between creations
                time.sleep(2)

            # Test IP rotation
            print(f"\nStep 2: Testing IP rotation...")
            unique_ips = set()

            for i, proxy_url in enumerate(created_proxies):
                try:
                    print(f"  Testing proxy {i+1}: {proxy_url}")

                    # Make request through proxy
                    response = requests.get(proxy_url, timeout=10)
                    if response.status_code == 200:
                        ip = response.text.strip()
                        unique_ips.add(ip)
                        print(f"    [OK] IP: {ip}")
                    else:
                        print(f"    [WARNING] HTTP {response.status_code}")

                except Exception as e:
                    print(f"    [FAILED] Error: {e}")

                time.sleep(1)

            # Results
            print(f"\nStep 3: Results Summary")
            print(f"{'='*60}")
            print(f"Proxies created: {len(created_proxies)}")
            print(f"Successful responses: {len(unique_ips)}")
            print(f"Unique IPs detected: {len(unique_ips)}")

            if len(unique_ips) > 1:
                print(f"[OK] IP ROTATION WORKING - Found {len(unique_ips)} different IPs")
            elif len(unique_ips) == 1:
                print(f"[WARNING] NO IP ROTATION - All requests from same IP: {list(unique_ips)[0]}")
            else:
                print(f"[FAILED] NO SUCCESSFUL RESPONSES")

            print(f"\nDetected IPs: {', '.join(sorted(unique_ips))}")

            # Cleanup
            try:
                cleanup_choice = input(f"\nCleanup test proxies? (y/n): ").strip().lower()
                if cleanup_choice == 'y':
                    print("Cleaning up test proxies...")
                    self.cleanup()
            except (EOFError, KeyboardInterrupt):
                print("\nSkipping cleanup (non-interactive mode)")
                print(f"Run 'omniprox --provider {self.provider} --command cleanup' to clean up manually")

            # Restore original URL
            self.url = original_url

            return len(unique_ips) > 0

        except Exception as e:
            print(f"Error during proxy test: {e}")
            self.url = original_url
            return False

    def _get_last_created_proxy_url(self):
        """Get the URL of the last created proxy (provider-specific implementation needed)"""
        # This should be overridden by each provider
        return None

    def validate_url(self, url: str) -> bool:
        if not url:
            self.logger.error("URL is required but not provided")
            return False

        try:
            from urllib.parse import urlparse
            result = urlparse(url)
            is_valid = all([result.scheme, result.netloc])
            if not is_valid:
                self.logger.error(f"Invalid URL format: {url}")
            return is_valid
        except Exception as e:
            self.logger.error(f"Error validating URL {url}: {e}")
            return False

    def get_domain_from_url(self, url: str) -> str:
        domain = tldextract.extract(url).domain
        self.logger.debug(f"Extracted domain '{domain}' from URL '{url}'")
        return domain

    def generate_api_id(self, url: str) -> str:
        domain = self.get_domain_from_url(url)
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        api_id = f'omniprox-{domain}-{timestamp}'
        self.logger.debug(f"Generated API ID: {api_id}")
        return api_id

    def print_success(self, operation: str, **kwargs):
        self.logger.info(f"Success: {operation}")
        print(f"\nSuccessfully {operation}!")
        for key, value in kwargs.items():
            if value:
                print(f"  {key.replace('_', ' ').title()}: {value}")

    def print_error(self, operation: str, error: str):
        self.logger.error(f"Failed: {operation} - {error}")
        print(f"\nError {operation}: {error}")

    def require_api_id(self) -> bool:
        if not self.api_id:
            self.logger.error("API ID is required but not provided")
            print("Error: --api_id is required for this command")
            return False
        return True

    def require_url(self) -> bool:
        if not self.url:
            self.logger.error("URL is required but not provided")
            print("Error: --url is required for this command")
            return False

        if not self.validate_url(self.url):
            print(f"Error: Invalid URL format: {self.url}")
            return False

        return True

    @abstractmethod
    def cleanup(self):
        """Delete all proxies"""
        pass
