"""
GCP Provider for OmniProx
Implements GCP API Gateway proxy functionality
"""

import datetime
import hashlib
import json
import logging
import configparser
import random
import string
import sys
import time
import subprocess
import warnings
import os
from typing import Optional, Dict, Any
from pathlib import Path
from contextlib import contextmanager

from ..core.base import BaseOmniProx
from ..core.utils import confirm_action, normalize_url

try:
    from google.cloud import apigateway_v1
    from google.oauth2 import service_account
    from google.auth import default as google_default
    from google.api_core import exceptions as google_exceptions
    HAS_GCP_LIBS = True
except ImportError:
    HAS_GCP_LIBS = False


class GCPProvider(BaseOmniProx):
    """GCP API Gateway provider for OmniProx"""

    # Resource identification constants
    RESOURCE_LABEL = 'omniprox'
    MANAGED_BY_LABEL = 'managed-by'

    # Timeout constants (in seconds)
    TIMEOUT_SHORT = 30      # Quick API calls and checks
    TIMEOUT_MEDIUM = 60     # Standard operations
    TIMEOUT_LONG = 120      # Long-running operations
    TIMEOUT_VERY_LONG = 300  # Very long operations like project creation

    def __init__(self, args: Any):
        """Initialize GCP provider

        Args:
            args: Command line arguments
        """
        super().__init__('gcp', args)

        # Suppress Google auth warnings unless in debug mode
        self._debug_mode = getattr(args, 'debug', False)
        if not self._debug_mode:
            warnings.filterwarnings("ignore", category=UserWarning, module="google.auth._default")
            warnings.filterwarnings("ignore", message="Your application has authenticated using end user credentials")

        self.project_id = None
        self.credentials_path = None
        self.region = 'us-central1'
        self.credentials = None
        self.api_client = None
        self.use_cli = False

        # GCP-prefixed attributes for compatibility
        self.gcp_project_id = None
        self.gcp_credentials_path = None
        self.gcp_region = 'us-central1'

    @contextmanager
    def _suppress_stderr_warnings(self):
        """Context manager to suppress stderr warnings in non-debug mode"""
        if self._debug_mode:
            yield
            return

        # Temporarily redirect stderr to suppress gRPC/ALTS warnings
        original_stderr = os.dup(2)
        devnull = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(devnull, 2)
            yield
        finally:
            os.dup2(original_stderr, 2)
            os.close(devnull)
            os.close(original_stderr)

    def create_profile(self, config: configparser.ConfigParser, profile_name: str):
        """Create a new GCP profile"""
        config[profile_name] = {}

        print("\nGCP Setup Options:")
        print("  1. Use gcloud CLI credentials (recommended)")
        print("  2. Use service account JSON file")
        print("  3. Skip for now")

        choice = input("\nSelect option (1-3): ").strip()

        if choice == '1':
            config[profile_name]['use_cli'] = 'true'
            config[profile_name]['project_id'] = input("GCP Project ID: ").strip()
        elif choice == '2':
            config[profile_name]['credentials_path'] = input("Service Account JSON path: ").strip()
            config[profile_name]['project_id'] = input("GCP Project ID: ").strip()
        else:
            print("Setup skipped. Configure manually later.")
            return

        config[profile_name]['region'] = input("GCP Region (default: us-central1): ").strip() or 'us-central1'

        self.save_profile(config)
        self.load_profile(config, profile_name)

    def load_profile(self, config: configparser.ConfigParser, profile_name: str):
        """Load GCP profile from configuration"""

        if profile_name in config:
            self.project_id = config[profile_name].get('project_id', '')
            self.credentials_path = config[profile_name].get('credentials_path', '')
            # Override region with command line argument if provided
            if hasattr(self.args, 'region') and self.args.region:
                self.region = self.args.region
            else:
                self.region = config[profile_name].get('region', 'us-central1')
            self.use_cli = config[profile_name].get('use_cli', '').lower() == 'true'

            # Set gcp-prefixed attributes for compatibility
            self.gcp_project_id = self.project_id
            self.gcp_credentials_path = self.credentials_path
            self.gcp_region = self.region

        # Check authentication
        try:
            if not HAS_GCP_LIBS:
                self.logger.error("GCP libraries not installed")
                print("\nError: GCP libraries are not installed.")
                print("Please install them with: pip install google-cloud-api-gateway google-cloud-resource-manager")
                return False

            if self.use_cli:
                self.logger.info("Configured to use gcloud CLI credentials")
                # Check if gcloud is authenticated
                try:
                    result = subprocess.run(
                        ['gcloud', 'auth', 'list', '--filter=status:ACTIVE', '--format=value(account)'],
                        capture_output=True, text=True, check=False, timeout=self.TIMEOUT_SHORT
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        self.logger.info(f"Found active gcloud account: {result.stdout.strip()}")
                        return True
                    else:
                        self.logger.warning("gcloud CLI not authenticated or no active account")
                        print("\nError: gcloud CLI not authenticated.")
                        print("Please run: gcloud auth login")
                        return False
                except FileNotFoundError:
                    self.logger.warning("gcloud CLI not found")
                    print("\nError: gcloud CLI is not installed.")
                    print("Please install the Google Cloud SDK from: https://cloud.google.com/sdk/install")
                    return False

            if self.credentials_path:
                if Path(self.credentials_path).exists():
                    self.logger.info("Using service account credentials")
                    return True
                else:
                    self.logger.error(f"Credentials file not found: {self.credentials_path}")
                    return False

            # Try default credentials
            from google.auth import default as google_default
            from google.auth.exceptions import DefaultCredentialsError
            try:
                credentials, project = google_default()
                if credentials:
                    self.logger.info("Found default GCP credentials")
                    if not self.project_id:
                        self.project_id = project
                        self.gcp_project_id = project
                    return True
            except DefaultCredentialsError as e:
                self.logger.debug(f"Default credentials not available: {e}")

            self.logger.warning("No GCP credentials found")
            print("\nGCP Authentication Required")
            print("Please run: gcloud auth application-default login")
            return False

        except Exception as e:
            self.logger.error(f"Error checking GCP authentication: {e}")
            return False

    def init_provider(self):
        """Initialize GCP provider and clients"""
        if not HAS_GCP_LIBS:
            return False

        # Auto-generate project ID if not set or project doesn't exist
        if not self.project_id or not self._project_exists(self.project_id):
            self.project_id = self._create_or_get_project()
            if not self.project_id:
                return False

        try:
            # Initialize credentials
            if self.credentials_path and Path(self.credentials_path).exists():
                self.credentials = service_account.Credentials.from_service_account_file(
                    self.credentials_path
                )
            else:
                # Use default credentials (gcloud CLI or ADC)
                self.credentials, _ = google_default()

            # Initialize API Gateway client (suppress warnings in non-debug mode)
            with self._suppress_stderr_warnings():
                self.api_client = apigateway_v1.ApiGatewayServiceClient(credentials=self.credentials)

            # Verify project exists
            if self.project_id:
                try:
                    result = subprocess.run(
                        ['gcloud', 'projects', 'describe', self.project_id],
                        capture_output=True, text=True, check=False, timeout=self.TIMEOUT_SHORT
                    )
                    if result.returncode != 0:
                        self.logger.warning(f"Project {self.project_id} not found or not accessible")
                        print(f"\nWarning: Project '{self.project_id}' not found or not accessible")
                        print("Make sure you have access to the project and billing is enabled.")
                except Exception as e:
                    self.logger.debug(f"Could not verify project access: {e}")

            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize GCP provider: {e}")
            print(f"Error initializing GCP provider: {e}")
            return False

    def _get_existing_api_url(self, api_id: str) -> Optional[str]:
        """Check if an API exists and return its URL if it does.

        Args:
            api_id: The API identifier to check

        Returns:
            The API's managed service URL if it exists, None otherwise
        """
        try:
            api_parent = f'projects/{self.project_id}/locations/global'
            existing_api = self.api_client.get_api(name=f'{api_parent}/apis/{api_id}')
            return f"https://{existing_api.managed_service}"
        except google_exceptions.NotFound:
            return None
        except Exception as e:
            self.logger.debug(f"Error checking if API {api_id} exists: {e}")
            return None

    def _project_exists(self, project_id: str) -> bool:
        """Check if a GCP project exists and is active"""
        try:
            result = subprocess.run(
                ['gcloud', 'projects', 'describe', project_id, '--format=value(lifecycleState)'],
                capture_output=True, text=True, check=False, timeout=self.TIMEOUT_SHORT
            )
            return result.returncode == 0 and result.stdout.strip() == 'ACTIVE'
        except subprocess.TimeoutExpired as e:
            self.logger.debug(f"Project check timed out for {project_id}: {e}")
            return False
        except (subprocess.SubprocessError, OSError) as e:
            self.logger.debug(f"Project check failed for {project_id}: {e}")
            return False

    def _create_or_get_project(self) -> str:
        """Create a new GCP project or get an existing omniprox project"""
        try:
            # First, try to find an existing omniprox project
            result = subprocess.run([
                'gcloud', 'projects', 'list',
                f'--filter=labels.{self.MANAGED_BY_LABEL}:{self.RESOURCE_LABEL} AND lifecycleState:ACTIVE',
                '--format=value(projectId)'
            ], capture_output=True, text=True, check=False, timeout=self.TIMEOUT_MEDIUM)

            if result.returncode == 0 and result.stdout.strip():
                existing_project = result.stdout.strip().split('\n')[0]
                self.logger.info(f"Found existing OmniProx project: {existing_project}")
                print(f"Using existing OmniProx project: {existing_project}")
                self._update_profile_project(existing_project)
                return existing_project

            # No existing project, create a new one
            timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
            suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
            project_id = f"omniprox-{timestamp}-{suffix}"

            print(f"\nCreating new GCP project: {project_id}")
            print("This may take a few moments...")

            # Create the project
            result = subprocess.run([
                'gcloud', 'projects', 'create', project_id,
                '--name=OmniProx API Gateway',
                f'--labels={self.MANAGED_BY_LABEL}={self.RESOURCE_LABEL},purpose=api-gateway-proxy'
            ], capture_output=True, text=True, check=False, timeout=self.TIMEOUT_LONG)

            if result.returncode != 0:
                self.logger.error(f"Failed to create project: {result.stderr}")
                print(f"Error creating project: {result.stderr}")
                return None

            # Set as active project
            subprocess.run(['gcloud', 'config', 'set', 'project', project_id], check=False, timeout=self.TIMEOUT_SHORT)

            # Enable required APIs
            print("Enabling required APIs...")
            apis_to_enable = [
                'apigateway.googleapis.com',
                'servicemanagement.googleapis.com',
                'servicecontrol.googleapis.com'
            ]

            for api in apis_to_enable:
                subprocess.run([
                    'gcloud', 'services', 'enable', api, '--project', project_id
                ], check=False, timeout=self.TIMEOUT_LONG)

            self.logger.info(f"Created new GCP project: {project_id}")
            print(f"Successfully created project: {project_id}")

            # Update profile with new project
            self._update_profile_project(project_id)

            return project_id

        except Exception as e:
            self.logger.error(f"Error creating/getting project: {e}")
            print(f"Error managing project: {e}")
            return None

    def _update_profile_project(self, project_id: str):
        """Update the profile configuration with new project ID"""
        try:
            config_path = Path.home() / '.omniprox' / 'profiles.ini'
            config = configparser.ConfigParser()
            config.read(config_path)

            profile_name = f"{self.provider}:{self.profile}"
            if profile_name in config:
                config[profile_name]['project_id'] = project_id
                with open(config_path, 'w') as f:
                    config.write(f)
                self.logger.info(f"Updated profile with project ID: {project_id}")
        except Exception as e:
            self.logger.error(f"Error updating profile: {e}")

    def get_openapi_spec(self, target_url: str) -> str:
        """Generate OpenAPI specification for the proxy with improved POST support"""
        spec = {
            "swagger": "2.0",
            "info": {
                "title": f"OmniProx API Gateway for {target_url}",
                "version": "2.0.0",
                "description": "HTTP proxy with full method support and path forwarding"
            },
            "schemes": ["https", "http"],
            "produces": ["application/json", "text/plain", "text/html", "application/xml"],
            "consumes": ["application/json", "application/x-www-form-urlencoded", "multipart/form-data", "text/plain", "application/xml"],
            "x-google-backend": {
                "address": target_url,
                "protocol": "h2",
                "path_translation": "APPEND_PATH_TO_ADDRESS"
            },
            "x-google-endpoints": [{
                "name": target_url,
                "allowCors": True
            }],
            "securityDefinitions": {
                "api_key": {
                    "type": "apiKey",
                    "name": "X-API-Key",
                    "in": "header"
                }
            },
            "paths": {
                "/**": {
                    "get": {
                        "operationId": "proxyGet",
                        "summary": "Forward GET request",
                        "responses": {
                            "200": {"description": "Success"},
                            "default": {"description": "Response from backend"}
                        },
                        "x-google-backend": {
                            "address": target_url,
                            "path_translation": "APPEND_PATH_TO_ADDRESS"
                        }
                    },
                    "post": {
                        "operationId": "proxyPost",
                        "summary": "Forward POST request with body",
                        "parameters": [
                            {
                                "name": "body",
                                "in": "body",
                                "required": False,
                                "schema": {
                                    "type": "object",
                                    "additionalProperties": True
                                },
                                "description": "Request body to forward"
                            }
                        ],
                        "responses": {
                            "200": {"description": "Success"},
                            "201": {"description": "Created"},
                            "default": {"description": "Response from backend"}
                        },
                        "x-google-backend": {
                            "address": target_url,
                            "path_translation": "APPEND_PATH_TO_ADDRESS"
                        }
                    },
                    "put": {
                        "operationId": "proxyPut",
                        "summary": "Forward PUT request with body",
                        "parameters": [
                            {
                                "name": "body",
                                "in": "body",
                                "required": False,
                                "schema": {
                                    "type": "object",
                                    "additionalProperties": True
                                }
                            }
                        ],
                        "responses": {
                            "200": {"description": "Success"},
                            "default": {"description": "Response from backend"}
                        }
                    },
                    "delete": {
                        "operationId": "proxyDelete",
                        "summary": "Forward DELETE request",
                        "responses": {
                            "200": {"description": "Success"},
                            "204": {"description": "No Content"},
                            "default": {"description": "Response from backend"}
                        }
                    },
                    "patch": {
                        "operationId": "proxyPatch",
                        "summary": "Forward PATCH request with body",
                        "parameters": [
                            {
                                "name": "body",
                                "in": "body",
                                "required": False,
                                "schema": {
                                    "type": "object",
                                    "additionalProperties": True
                                }
                            }
                        ],
                        "responses": {
                            "200": {"description": "Success"},
                            "default": {"description": "Response from backend"}
                        }
                    },
                    "options": {
                        "operationId": "proxyOptions",
                        "summary": "Forward OPTIONS request",
                        "responses": {
                            "200": {"description": "Success"},
                            "204": {"description": "No Content"},
                            "default": {"description": "Response from backend"}
                        }
                    }
                },
            }
        }
        return json.dumps(spec, indent=2)

    def generate_api_id(self, url: str, instance: int = None) -> str:
        """Generate a unique API ID from URL using SHA256 hash"""
        domain = self.get_domain_from_url(url).replace('.', '-')
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:8]
        if instance is not None:
            return f"omniprox-{domain}-{url_hash}-{instance}"
        return f"omniprox-{domain}-{url_hash}"

    def create(self):
        """Create a new GCP API Gateway proxy"""
        if not self.init_provider():
            return False

        if not self.url:
            self.logger.error("URL is required for create command")
            print("Error: --url is required for create command")
            return False

        self.url = normalize_url(self.url)

        # Get number of proxies to create (default is 1)
        num_proxies = getattr(self.args, 'number', 1)

        print(f"\nCreating {num_proxies} GCP API Gateway proxy(ies) for: {self.url}")
        print(f"Project: {self.project_id}")
        print(f"Region: {self.region}")

        created_proxies = []
        failed_proxies = []

        for i in range(num_proxies):
            try:
                if num_proxies > 1:
                    print(f"\n--- Creating proxy {i+1}/{num_proxies} ---")
                    api_id = self.generate_api_id(self.url, i+1)
                else:
                    api_id = self.generate_api_id(self.url)

                result = self._create_api_with_id(api_id)
                if result:
                    created_proxies.append(result)
                else:
                    failed_proxies.append(f"proxy-{i+1}")

            except Exception as e:
                self.logger.error(f"Failed to create proxy {i+1}: {e}")
                failed_proxies.append(f"proxy-{i+1}")

        # Summary
        print(f"\n{'='*60}")
        print(f"Creation Summary")
        print(f"{'='*60}")
        print(f"Total requested: {num_proxies}")
        print(f"Successfully created: {len(created_proxies)}")
        print(f"Failed: {len(failed_proxies)}")

        if created_proxies:
            print(f"\nCreated proxies:")
            for proxy in created_proxies:
                print(f"  {proxy}")

        if failed_proxies:
            print(f"\nFailed proxies: {', '.join(failed_proxies)}")

        return len(created_proxies) > 0

    def _create_api_with_id(self, api_id: str):
        """Create a single API Gateway proxy with specific ID (for batch creation)"""
        try:
            api_parent = f'projects/{self.project_id}/locations/global'

            # Check if API already exists
            existing_url = self._get_existing_api_url(api_id)
            if existing_url:
                print(f"  API '{api_id}' already exists: {existing_url}")
                return existing_url

            # Create API
            api = apigateway_v1.Api()
            api.display_name = f'OmniProx - {self.url}'

            self.logger.info(f"Creating API: {api_id}")
            print(f"Creating API: {api_id}...")

            operation = self.api_client.create_api(
                parent=api_parent,
                api_id=api_id,
                api=api
            )
            api_result = operation.result(timeout=self.TIMEOUT_VERY_LONG)

            # Create API Config
            config_id = f'{api_id}-config-{int(time.time())}'
            openapi_spec = self.get_openapi_spec(self.url)

            config = apigateway_v1.ApiConfig()
            config.display_name = f'Config for {api_id}'

            # Create OpenAPI document
            openapi_doc = apigateway_v1.ApiConfig.OpenApiDocument()
            openapi_doc.document = apigateway_v1.ApiConfig.File(
                path='openapi.yaml',
                contents=openapi_spec.encode('utf-8')
            )
            config.openapi_documents = [openapi_doc]

            self.logger.info(f"Creating API Config: {config_id}")
            print(f"Creating API Config: {config_id}...")

            config_operation = self.api_client.create_api_config(
                parent=api_result.name,
                api_config_id=config_id,
                api_config=config
            )
            config_result = config_operation.result(timeout=self.TIMEOUT_VERY_LONG)

            # Create Gateway
            gateway_id = f'{api_id}-gateway'
            gateway_parent = f'projects/{self.project_id}/locations/{self.region}'

            gateway = apigateway_v1.Gateway()
            gateway.api_config = config_result.name
            gateway.display_name = f'Gateway for {api_id}'

            self.logger.info(f"Creating Gateway: {gateway_id}")
            print(f"Creating Gateway: {gateway_id}...")

            gateway_operation = self.api_client.create_gateway(
                parent=gateway_parent,
                gateway_id=gateway_id,
                gateway=gateway
            )
            gateway_result = gateway_operation.result(timeout=self.TIMEOUT_VERY_LONG)

            gateway_url = f"https://{gateway_result.default_hostname}"

            print(f"  Successfully created '{api_id}': {gateway_url}")
            return gateway_url

        except google_exceptions.AlreadyExists:
            print(f"  API Gateway with ID '{api_id}' already exists")
            return None
        except Exception as e:
            self.logger.error(f"Failed to create API Gateway: {e}")
            print(f"  Error creating API Gateway '{api_id}': {e}")
            return None

    def _create_single_proxy(self) -> bool:
        """Create a single API Gateway proxy for testing purposes"""
        if not self.init_provider():
            return False

        try:
            # Generate unique API ID for testing
            test_suffix = f"test-{int(time.time())}-{random.randint(1000, 9999)}"
            api_id = f"omniprox-{test_suffix}"

            api_parent = f'projects/{self.project_id}/locations/global'

            # Check if API already exists (unlikely for test suffix, but check anyway)
            existing_url = self._get_existing_api_url(api_id)
            if existing_url:
                self._last_created_url = existing_url
                return True

            # Create API
            api = apigateway_v1.Api()
            api.display_name = f'OmniProx - {self.url}'

            self.logger.info(f"Creating API: {api_id}")
            print(f"Creating API: {api_id}...")

            operation = self.api_client.create_api(
                parent=api_parent,
                api_id=api_id,
                api=api
            )
            api_result = operation.result(timeout=self.TIMEOUT_VERY_LONG)

            # Create API Config
            config_id = f'{api_id}-config-{int(time.time())}'
            openapi_spec = self.get_openapi_spec(self.url)

            config = apigateway_v1.ApiConfig()
            config.display_name = f'Config for {api_id}'

            # Create OpenAPI document
            openapi_doc = apigateway_v1.ApiConfig.OpenApiDocument()
            openapi_doc.document = apigateway_v1.ApiConfig.File(
                path='openapi.yaml',
                contents=openapi_spec.encode('utf-8')
            )
            config.openapi_documents = [openapi_doc]

            self.logger.info(f"Creating API Config: {config_id}")
            print(f"Creating API Config: {config_id}...")

            config_operation = self.api_client.create_api_config(
                parent=api_result.name,
                api_config_id=config_id,
                api_config=config
            )
            config_result = config_operation.result(timeout=self.TIMEOUT_VERY_LONG)

            # Create Gateway
            gateway_id = f'{api_id}-gateway'
            gateway_parent = f'projects/{self.project_id}/locations/{self.region}'

            gateway = apigateway_v1.Gateway()
            gateway.api_config = config_result.name
            gateway.display_name = f'Gateway for {api_id}'

            self.logger.info(f"Creating Gateway: {gateway_id}")
            print(f"Creating Gateway: {gateway_id}...")

            gateway_operation = self.api_client.create_gateway(
                parent=gateway_parent,
                gateway_id=gateway_id,
                gateway=gateway
            )
            gateway_result = gateway_operation.result(timeout=self.TIMEOUT_VERY_LONG)

            gateway_url = f"https://{gateway_result.default_hostname}"
            self._last_created_url = gateway_url
            return True

        except google_exceptions.AlreadyExists:
            return False
        except Exception as e:
            self.logger.error(f"Failed to create API Gateway: {e}")
            return False

    def _get_last_created_proxy_url(self) -> str:
        """Get the URL of the last created proxy for testing"""
        return getattr(self, '_last_created_url', None)

    def list(self):
        """List all GCP API Gateway proxies"""
        if not self.init_provider():
            return False

        try:
            print(f"\nListing GCP API Gateways in project: {self.project_id}")
            print("-" * 60)

            # Use gcloud CLI as fallback to get reliable results
            try:
                # Get APIs using gcloud CLI
                result = subprocess.run([
                    'gcloud', 'api-gateway', 'apis', 'list',
                    '--project', self.project_id,
                    '--format', 'json'
                ], capture_output=True, text=True, check=True, timeout=self.TIMEOUT_MEDIUM)

                cli_apis = json.loads(result.stdout) if result.stdout else []
                omniprox_apis = [api for api in cli_apis if 'omniprox' in api.get('name', '').lower()]

                if not omniprox_apis:
                    print("No OmniProx APIs found")
                    return True

            except (subprocess.CalledProcessError, json.JSONDecodeError, Exception) as e:
                self.logger.warning(f"gcloud CLI fallback failed: {e}")

                # Fall back to Python API client
                api_parent = f'projects/{self.project_id}/locations/global'
                apis = self.api_client.list_apis(parent=api_parent)
                omniprox_apis = []

                for api in apis:
                    if 'omniprox' in api.name.lower():
                        omniprox_apis.append({
                            'name': api.name,
                            'displayName': api.display_name,
                            'state': api.state,
                            'managedService': getattr(api, 'managed_service', None)
                        })

                if not omniprox_apis:
                    print("No OmniProx APIs found")
                    return True

            print(f"Found {len(omniprox_apis)} OmniProx API(s):")
            print()

            for api in omniprox_apis:
                # Handle both gcloud CLI JSON format and Python API object
                if isinstance(api, dict):
                    # gcloud CLI JSON format
                    api_id = api['name'].split('/')[-1]
                    display_name = api.get('displayName', '')
                    state = api.get('state', 'UNKNOWN')
                    managed_service = api.get('managedService', '')
                else:
                    # Python API object format
                    api_id = api.name.split('/')[-1]
                    display_name = api.display_name
                    state_map = {0: 'STATE_UNSPECIFIED', 1: 'CREATING', 2: 'ACTIVE', 3: 'FAILED', 4: 'DELETING'}
                    state = state_map.get(api.state, f'UNKNOWN({api.state})')
                    managed_service = getattr(api, 'managed_service', '')

                print(f"API ID: {api_id}")
                print(f"  Display Name: {display_name}")
                print(f"  State: {state}")

                # Show the proxy URL if available
                if managed_service:
                    if not managed_service.startswith('http'):
                        managed_service = f"https://{managed_service}"
                    print(f"  Proxy URL: {managed_service}")

                # Check for gateways (optional since managed service URL is the main proxy URL)
                try:
                    gateway_parent = f'projects/{self.project_id}/locations/{self.region}'
                    gateways = self.api_client.list_gateways(parent=gateway_parent)
                    gateway_found = False

                    for gateway in gateways:
                        # Check if this gateway belongs to the current API
                        api_name = api['name'] if isinstance(api, dict) else api.name
                        if api_name in gateway.api_config:
                            print(f"  Gateway URL: https://{gateway.default_hostname}")
                            gateway_found = True
                            break

                    if not gateway_found:
                        print(f"  Gateway: [Not deployed - using managed service URL above]")

                except Exception as gateway_error:
                    self.logger.debug(f"Could not list gateways for API {api_id}: {gateway_error}")
                    print(f"  Gateway: [Using managed service URL above]")

                print()

            return True

        except Exception as e:
            self.logger.error(f"Failed to list APIs: {e}")
            print(f"Error listing APIs: {e}")
            return False

    def delete(self):
        """Delete a GCP API Gateway proxy"""
        if not self.init_provider():
            return False

        if not self.api_id:
            self.logger.error("API ID is required for delete command")
            print("Error: --api_id is required for delete command")
            print("Use 'list' command to see available API IDs")
            return False

        print(f"\nDeleting GCP API Gateway: {self.api_id}")

        try:
            api_name = f'projects/{self.project_id}/locations/global/apis/{self.api_id}'
            gateway_parent = f'projects/{self.project_id}/locations/{self.region}'

            # Delete associated gateways first
            print("Checking for associated gateways...")
            gateways = self.api_client.list_gateways(parent=gateway_parent)

            for gateway in gateways:
                if api_name in gateway.api_config:
                    gateway_id = gateway.name.split('/')[-1]
                    print(f"Deleting gateway: {gateway_id}...")
                    operation = self.api_client.delete_gateway(name=gateway.name)
                    operation.result(timeout=self.TIMEOUT_VERY_LONG)
                    print(f"  [OK] Deleted gateway: {gateway_id}")

            # Delete API configs
            print("Deleting API configs...")
            configs = self.api_client.list_api_configs(parent=api_name)

            for config in configs:
                config_id = config.name.split('/')[-1]
                print(f"Deleting config: {config_id}...")
                operation = self.api_client.delete_api_config(name=config.name)
                operation.result(timeout=self.TIMEOUT_VERY_LONG)
                print(f"  [OK] Deleted config: {config_id}")

            # Delete the API
            print(f"Deleting API: {self.api_id}...")
            operation = self.api_client.delete_api(name=api_name)
            operation.result(timeout=self.TIMEOUT_VERY_LONG)
            print(f"  [OK] Deleted API: {self.api_id}")

            print(f"\nSuccessfully deleted GCP API Gateway: {self.api_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to delete API Gateway: {e}")
            print(f"Error deleting API Gateway: {e}")
            return False

    def _delete_api_with_gcloud(self, api_id: str) -> bool:
        """Delete API and related resources using gcloud CLI for reliability"""
        try:
            # First, try to delete any gateways
            try:
                # Find all gateways that might be using this API
                result = subprocess.run([
                    'gcloud', 'api-gateway', 'gateways', 'list',
                    '--project', self.project_id,
                    '--location', self.region,
                    '--format', 'value(name)',
                    '--filter', f'name:{api_id}'
                ], capture_output=True, text=True, check=True)

                gateway_names = result.stdout.strip().split('\n') if result.stdout.strip() else []
                for gateway_name in gateway_names:
                    if gateway_name:
                        print(f"  Deleting gateway: {gateway_name.split('/')[-1]}...")
                        subprocess.run([
                            'gcloud', 'api-gateway', 'gateways', 'delete', gateway_name.split('/')[-1],
                            '--project', self.project_id,
                            '--location', self.region,
                            '--quiet',
                            '--async'  # Don't wait for completion
                        ], check=True, capture_output=True, timeout=10)

            except subprocess.CalledProcessError as e:
                # Gateways might not exist, continue
                self.logger.debug(f"No gateways to delete for {api_id}: {e}")

            # Delete API configs
            try:
                result = subprocess.run([
                    'gcloud', 'api-gateway', 'api-configs', 'list',
                    '--project', self.project_id,
                    '--api', api_id,
                    '--format', 'value(name)',
                ], capture_output=True, text=True, check=True)

                config_names = result.stdout.strip().split('\n') if result.stdout.strip() else []
                for config_name in config_names:
                    if config_name:
                        config_id = config_name.split('/')[-1]
                        print(f"  Deleting config: {config_id}...")
                        subprocess.run([
                            'gcloud', 'api-gateway', 'api-configs', 'delete', config_id,
                            '--project', self.project_id,
                            '--api', api_id,
                            '--quiet',
                            '--async'  # Don't wait for completion
                        ], check=True, capture_output=True, timeout=10)

            except subprocess.CalledProcessError as e:
                # Configs might not exist, continue
                self.logger.debug(f"No configs to delete for {api_id}: {e}")

            # Finally, delete the API
            print(f"  Deleting API: {api_id}...")
            subprocess.run([
                'gcloud', 'api-gateway', 'apis', 'delete', api_id,
                '--project', self.project_id,
                '--quiet',
                '--async'  # Don't wait for completion
            ], check=True, capture_output=True, timeout=10)

            return True

        except subprocess.CalledProcessError as e:
            # Get more detailed error information
            error_output = getattr(e, 'stderr', '') or getattr(e, 'stdout', '') or str(e)
            self.logger.error(f"gcloud deletion failed for {api_id}: {error_output}")

            # Try one more time with force deletion
            try:
                print(f"  Retrying deletion with force for: {api_id}...")
                subprocess.run([
                    'gcloud', 'api-gateway', 'apis', 'delete', api_id,
                    '--project', self.project_id,
                    '--quiet',
                    '--async'  # Don't wait for completion
                ], check=False, capture_output=True)  # Don't raise on failure
                return True
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
                self.logger.debug(f"Retry deletion failed for {api_id}: {e}")

            return False
        except Exception as e:
            self.logger.error(f"Unexpected error deleting {api_id}: {e}")
            return False

    def cleanup(self):
        """Delete all OmniProx API Gateways"""
        if not self.init_provider():
            return False

        try:
            api_parent = f'projects/{self.project_id}/locations/global'

            print(f"\nCleaning up OmniProx API Gateways in project: {self.project_id}")

            # Use gcloud CLI to get reliable results (same as list command)
            try:
                # Get APIs using gcloud CLI
                result = subprocess.run([
                    'gcloud', 'api-gateway', 'apis', 'list',
                    '--project', self.project_id,
                    '--format', 'json'
                ], capture_output=True, text=True, check=True, timeout=self.TIMEOUT_MEDIUM)

                cli_apis = json.loads(result.stdout) if result.stdout else []
                omniprox_apis = [api for api in cli_apis if 'omniprox' in api.get('name', '').lower()]

            except (subprocess.CalledProcessError, json.JSONDecodeError, Exception) as e:
                self.logger.warning(f"gcloud CLI fallback failed: {e}")

                # Fall back to Python API client
                apis = self.api_client.list_apis(parent=api_parent)
                omniprox_apis = []

                for api in apis:
                    if 'omniprox' in api.name.lower():
                        omniprox_apis.append({
                            'name': api.name,
                            'displayName': api.display_name,
                            'state': api.state,
                            'managedService': getattr(api, 'managed_service', None)
                        })

            if not omniprox_apis:
                print("No OmniProx APIs to clean up")
                return True

            print(f"Found {len(omniprox_apis)} OmniProx API(s) to delete")

            if not confirm_action("Are you sure you want to delete all OmniProx APIs?"):
                print("Cleanup cancelled")
                return False

            deleted_count = 0
            failed_count = 0

            for api in omniprox_apis:
                # Handle both gcloud CLI JSON format and Python API object
                if isinstance(api, dict):
                    api_name = api['name']
                    api_id = api_name.split('/')[-1]
                else:
                    api_name = api.name
                    api_id = api_name.split('/')[-1]

                try:
                    print(f"\nDeleting {api_id}...")

                    # Use gcloud CLI for more reliable deletion
                    success = self._delete_api_with_gcloud(api_id)

                    if success:
                        print(f"  [OK] Deleted: {api_id}")
                        deleted_count += 1
                    else:
                        print(f"  [FAILED] Could not delete: {api_id}")
                        failed_count += 1

                except Exception as e:
                    print(f"  [FAILED] Error deleting {api_id}: {e}")
                    failed_count += 1

            print(f"\nCleanup completed: {deleted_count} deleted, {failed_count} failed")
            return True

        except Exception as e:
            self.logger.error(f"Cleanup failed: {e}")
            print(f"Error during cleanup: {e}")
            return False

    def status(self):
        """Check GCP API Gateway status"""
        if not self.init_provider():
            return False

        print(f"\n===============================================")
        print(f"GCP API Gateway Status")
        print(f"===============================================")
        print(f"Project: {self.project_id}")
        print(f"Region: {self.region}")

        try:
            api_parent = f'projects/{self.project_id}/locations/global'

            # Count APIs - convert to list first since generator can only be consumed once
            apis = list(self.api_client.list_apis(parent=api_parent))
            omniprox_count = sum(1 for api in apis if 'omniprox' in api.name.lower())
            total_count = len(apis)

            print(f"\nAPI Statistics:")
            print(f"  Total APIs: {total_count}")
            print(f"  OmniProx APIs: {omniprox_count}")
            print(f"  Available slots: {100 - total_count} (max 100 per project)")

            print(f"\nPricing Information:")
            print(f"  First 2 million calls/month: FREE")
            print(f"  Over 2 million: $3.00 per million")
            print(f"  Data transfer: Standard GCP egress rates")

            print(f"\nLimitations:")
            print(f"  Max APIs per project: 100")
            print(f"  Max API configs per API: 20")
            print(f"  Max gateways per region: 5")
            print(f"  Request timeout: 60 seconds")
            print(f"  Request/Response size: 32 MB")

            print(f"\nUseful Commands:")
            print(f"  View in console: https://console.cloud.google.com/api-gateway?project={self.project_id}")
            print(f"  List APIs: gcloud api-gateway apis list")
            print(f"  List gateways: gcloud api-gateway gateways list --location={self.region}")

            return True

        except Exception as e:
            self.logger.error(f"Failed to check status: {e}")
            print(f"Error checking status: {e}")
            return False

    def update(self):
        """Update is not implemented for GCP"""
        print("Update command is not supported for GCP provider")
        print("GCP API Gateway configurations are immutable. Create a new config version instead.")
        return False

    def usage(self):
        """Check GCP usage"""
        print(f"\nGCP API Gateway Usage")
        print("=" * 60)
        print(f"Project: {self.project_id}")
        print(f"\nFor detailed metrics and usage statistics, visit:")
        print(f"  https://console.cloud.google.com/api-gateway?project={self.project_id}")
        print(f"\nPricing:")
        print(f"  First 2 million calls/month: FREE")
        print(f"  Over 2 million: $3.00 per million calls")
        return True