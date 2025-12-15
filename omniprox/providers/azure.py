"""
Azure Provider for OmniProx
Creates multiple Azure Container Instances for IP rotation
"""

import json
import logging
import os
import random
import subprocess
import sys
import tempfile
import textwrap
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from omniprox.core.base import BaseOmniProx

from omniprox.core.utils import confirm_action, get_unique_suffix


def _get_rotate_client_path() -> Path:
    """Get the path for the rotation client script (computed fresh each time)"""
    return Path(tempfile.gettempdir()) / 'omniprox_rotate.py'

# Azure SDK imports
try:
    from azure.identity import AzureCliCredential, ClientSecretCredential
    from azure.mgmt.resource import ResourceManagementClient
    from azure.mgmt.containerinstance import ContainerInstanceManagementClient
    from azure.mgmt.containerinstance.models import (
        ContainerGroup,
        Container,
        ContainerPort,
        Port,
        IpAddress,
        ResourceRequests,
        ResourceRequirements,
        OperatingSystemTypes,
        ContainerGroupRestartPolicy,
        EnvironmentVariable
    )
    from azure.core.exceptions import ResourceNotFoundError, HttpResponseError
    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False


class AzureProvider(BaseOmniProx):
    """Azure provider for IP rotation using Container Instances"""

    def __init__(self, args):
        """Initialize Azure provider"""
        # Initialize base attributes first
        self.subscription_id = None
        self.tenant_id = None
        self.client_id = None
        self.client_secret = None
        self.location = 'eastus'
        self.resource_group = None
        self.pool_size = getattr(args, 'number', 3)  # Number of containers in pool
        self.use_cli = True

        # Azure clients
        self.credential = None
        self.resource_client = None
        self.aci_client = None

        # Container pool management
        self.container_pool = []

        # Initialize base class (this will call load_profile)
        super().__init__('azure', args)

    def load_profile(self, config, profile_name):
        """Load Azure configuration from profile"""
        self.config = config
        self.logger.info(f"Loading existing profile '{self.profile}'")
        print(f"Loading profile '{self.profile}' for AZURE...")

        # Load configuration values
        self.subscription_id = config.get(profile_name, 'subscription_id', fallback=None)
        self.tenant_id = config.get(profile_name, 'tenant_id', fallback=None)
        self.client_id = config.get(profile_name, 'client_id', fallback=None)
        self.client_secret = config.get(profile_name, 'client_secret', fallback=None)
        # Override location with command line argument if provided
        if hasattr(self.args, 'region') and self.args.region:
            self.location = self.args.region
        else:
            self.location = config.get(profile_name, 'location', fallback='eastus')
        self.resource_group = config.get(profile_name, 'resource_group', fallback=None)
        self.use_cli = config.get(profile_name, 'use_cli', fallback='true').lower() == 'true'

        # Load existing pool if configured
        pool_json = config.get(profile_name, 'container_pool', fallback='[]')
        try:
            self.container_pool = json.loads(pool_json)
        except (json.JSONDecodeError, ValueError, TypeError):
            self.container_pool = []

    def save_pool_config(self):
        """Save container pool configuration"""
        section = f"{self.provider}:{self.profile}"

        if not self.config.has_section(section):
            self.config.add_section(section)

        self.config.set(section, 'subscription_id', self.subscription_id or '')
        self.config.set(section, 'location', self.location)
        self.config.set(section, 'resource_group', self.resource_group or '')
        self.config.set(section, 'use_cli', 'true' if self.use_cli else 'false')
        self.config.set(section, 'container_pool', json.dumps(self.container_pool))

        # Save to file
        with open(self.config_path, 'w') as f:
            self.config.write(f)

        self.logger.info("Updated profile with container pool")

    def init_provider(self):
        """Initialize Azure provider and verify credentials"""
        if not AZURE_AVAILABLE:
            print("Error: Azure SDK not installed")
            print("Install with: pip install azure-mgmt-containerinstance azure-mgmt-resource azure-identity")
            return False

        # Initialize credential
        if self.use_cli:
            self.logger.info("Configured to use Azure CLI credentials")
            self.credential = AzureCliCredential()

            # Verify CLI authentication
            try:
                result = subprocess.run(
                    ['az', 'account', 'show'],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode == 0:
                    account_info = json.loads(result.stdout)
                    self.logger.info(f"Found active Azure account: {account_info.get('user', {}).get('name', 'Unknown')}")
                    if not self.subscription_id:
                        self.subscription_id = account_info.get('id')
                else:
                    print("Error: No active Azure CLI session")
                    print("Run: az login")
                    return False
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError, OSError) as e:
                self.logger.error(f"Error checking Azure CLI: {e}")
                return False
        else:
            if not all([self.tenant_id, self.client_id, self.client_secret]):
                print("Error: Service principal credentials not configured")
                return False

            self.credential = ClientSecretCredential(
                tenant_id=self.tenant_id,
                client_id=self.client_id,
                client_secret=self.client_secret
            )

        # Initialize Azure clients
        try:
            self.resource_client = ResourceManagementClient(
                self.credential,
                self.subscription_id
            )

            self.aci_client = ContainerInstanceManagementClient(
                self.credential,
                self.subscription_id
            )

            return True
        except Exception as e:
            self.logger.error(f"Error initializing Azure clients: {e}")
            return False

    def _get_proxy_script(self, target_url: str) -> str:
        """Generate the Node.js proxy script content.

        Separated from container creation to avoid shell escaping issues.
        The script is passed via environment variable and written to file at runtime.
        """
        return f'''const http = require('http');
const https = require('https');
const url = require('url');

const BASE_URL = '{target_url}';

const server = http.createServer((req, res) => {{
    let targetUrl;
    const reqUrl = url.parse(req.url, true);

    // Check for URL in query parameter first
    if (reqUrl.query.url) {{
        targetUrl = reqUrl.query.url;
    }}
    // Check if path starts with http
    else if (req.url.startsWith('/http')) {{
        targetUrl = req.url.substring(1);
    }}
    // Otherwise append path to base URL
    else {{
        const baseUrl = new URL(BASE_URL);
        baseUrl.pathname = baseUrl.pathname.replace(/\\/$/, '') + req.url;
        targetUrl = baseUrl.toString();
    }}

    console.log('Proxying to:', targetUrl);

    // Parse target URL
    const targetParsed = url.parse(targetUrl);
    const protocol = targetParsed.protocol === 'https:' ? https : http;

    // Copy headers and add IP rotation
    const headers = Object.assign({{}}, req.headers);
    headers.host = targetParsed.hostname;

    // Rotate IPs for every request
    const randomIP = () => Math.floor(Math.random()*255) + '.' +
                           Math.floor(Math.random()*255) + '.' +
                           Math.floor(Math.random()*255) + '.' +
                           Math.floor(Math.random()*255);

    // Handle custom X-Forwarded-For from X-My-X-Forwarded-For header
    if (headers['x-my-x-forwarded-for']) {{
        headers['x-forwarded-for'] = headers['x-my-x-forwarded-for'];
        headers['x-real-ip'] = headers['x-my-x-forwarded-for'].split(',')[0].trim();
        delete headers['x-my-x-forwarded-for'];
    }} else {{
        headers['x-forwarded-for'] = randomIP();
        headers['x-real-ip'] = randomIP();
    }}
    delete headers['host-length'];

    // Make request
    const options = {{
        hostname: targetParsed.hostname,
        port: targetParsed.port || (targetParsed.protocol === 'https:' ? 443 : 80),
        path: targetParsed.path,
        method: req.method,
        headers: headers
    }};

    const proxyReq = protocol.request(options, (proxyRes) => {{
        res.writeHead(proxyRes.statusCode, proxyRes.headers);
        proxyRes.pipe(res);
    }});

    proxyReq.on('error', (err) => {{
        res.writeHead(502, {{'Content-Type': 'text/plain'}});
        res.end('Proxy error: ' + err.message);
    }});

    req.pipe(proxyReq);
}});

server.listen(80, () => {{
    console.log('OmniProx proxy running on port 80');
    console.log('Base URL:', BASE_URL);
}});
'''

    def create_nginx_container(self, name: str, target_url: str) -> 'Container':
        """Create HTTP proxy container with path preservation.

        Uses environment variable to pass the proxy script, avoiding shell
        escaping issues that occur with inline script execution.
        """
        # Get the proxy script content
        proxy_script = self._get_proxy_script(target_url)

        # Command writes the script from env var to file, then executes it
        # This avoids complex shell escaping issues with inline scripts
        command = [
            'sh', '-c',
            'echo "$PROXY_SCRIPT" > /tmp/proxy.js && node /tmp/proxy.js'
        ]

        container = Container(
            name=name,
            image='mcr.microsoft.com/mirror/docker/library/node:18-alpine',
            resources=ResourceRequirements(
                requests=ResourceRequests(
                    memory_in_gb=0.5,  # Minimal memory
                    cpu=0.5  # Minimal CPU
                )
            ),
            ports=[ContainerPort(port=80)],
            command=command,
            environment_variables=[
                EnvironmentVariable(name='TARGET_URL', value=target_url),
                EnvironmentVariable(name='PROXY_SCRIPT', value=proxy_script)
            ]
        )

        return container

    def create(self):
        """Create a pool of Azure Container Instances for IP rotation"""
        if not self.init_provider():
            return False

        if not self.url:
            print("Error: --url is required for create command")
            return False

        try:
            # Auto-generate names if not provided
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')

            if not self.resource_group:
                self.resource_group = f"omniprox-pool-{datetime.now().strftime('%Y%m%d')}"
                self.logger.info(f"Auto-generating resource group name: {self.resource_group}")

            # Create or verify resource group
            try:
                rg = self.resource_client.resource_groups.get(self.resource_group)
                self.logger.info(f"Using existing resource group: {self.resource_group}")
                print(f"Using existing resource group: {self.resource_group}")
            except ResourceNotFoundError:
                self.logger.info(f"Creating resource group: {self.resource_group}")
                print(f"Creating resource group: {self.resource_group} in {self.location}...")

                rg = self.resource_client.resource_groups.create_or_update(
                    self.resource_group,
                    {
                        'location': self.location,
                        'tags': {
                            'created_by': 'omniprox',
                            'purpose': 'container_pool',
                            'timestamp': timestamp
                        }
                    }
                )
                print(f"Resource group created: {self.resource_group}")

            # Create container pool
            print(f"\nCreating Azure Container Pool for: {self.url}")
            print(f"Pool size: {self.pool_size} containers")
            print("-" * 60)

            # Store target URL for containers
            self.target_url = self.url

            self.container_pool = []
            successful_containers = 0

            for i in range(1, self.pool_size + 1):
                container_group_name = f"omniprox-pool-{i}-{get_unique_suffix()}"
                dns_label = f"omniprox-{i}-{get_unique_suffix()}"

                print(f"\n[{i}/{self.pool_size}] Creating container: {container_group_name}")

                try:
                    # Create container configuration
                    container = self.create_nginx_container(f"proxy-{i}", self.url)

                    # Create container group
                    container_group = ContainerGroup(
                        location=self.location,
                        containers=[container],
                        os_type=OperatingSystemTypes.linux,
                        ip_address=IpAddress(
                            ports=[Port(port=80, protocol='TCP')],
                            type='Public',
                            dns_name_label=dns_label.lower()
                        ),
                        restart_policy=ContainerGroupRestartPolicy.always,
                        tags={
                            'created_by': 'omniprox',
                            'pool_id': timestamp,
                            'target_url': self.url,
                            'container_number': str(i)
                        }
                    )

                    print(f"  Deploying container instance...")
                    operation = self.aci_client.container_groups.begin_create_or_update(
                        self.resource_group,
                        container_group_name,
                        container_group
                    )

                    # Wait for deployment (with timeout)
                    result = operation.result(timeout=60)

                    # Get the public IP/FQDN
                    if result.ip_address:
                        container_info = {
                            'name': container_group_name,
                            'ip': result.ip_address.ip,
                            'fqdn': result.ip_address.fqdn or f"{result.ip_address.ip}",
                            'url': f"http://{result.ip_address.fqdn or result.ip_address.ip}",
                            'target': self.url
                        }

                        self.container_pool.append(container_info)
                        successful_containers += 1

                        print(f"  [OK] Deployed: {container_info['url']}")
                        print(f"       IP: {container_info['ip']}")
                    else:
                        print(f"  [WARNING] Deployed but no IP assigned")

                except Exception as e:
                    print(f"  [FAILED] {str(e)[:100]}")
                    self.logger.error(f"Failed to create container {i}: {e}")

                # Small delay between container creations
                if i < self.pool_size:
                    time.sleep(2)

            # Save pool configuration
            self.save_pool_config()

            # Display summary
            print("\n" + "="*60)
            print("AZURE PROXY POOL CREATED SUCCESSFULLY")
            print("="*60)
            print(f"\nPool Statistics:")
            print(f"  Total Requested: {self.pool_size}")
            print(f"  Successfully Created: {successful_containers}")
            print(f"  Failed: {self.pool_size - successful_containers}")

            if self.container_pool:
                print(f"\nContainer Pool Endpoints ({len(self.container_pool)} containers):")
                for i, container in enumerate(self.container_pool, 1):
                    print(f"  {i}. {container['url']} (IP: {container['ip']})")

                print(f"\nIP Rotation Pool:")
                print(f"  Unique IPs: {len(set(c['ip'] for c in self.container_pool))}")
                print(f"  Target URL: {self.url}")

                # Create rotation client script
                self.create_rotation_client()

                rotate_path = _get_rotate_client_path()
                print(f"\nUsage Examples:")
                print(f"  # Random proxy from pool:")
                print(f"  curl '{random.choice(self.container_pool)['url']}'")
                print(f"\n  # Python rotation client:")
                print(f"  python3 {rotate_path}")
                print(f"\n  # Test IP rotation:")
                print(f"  python3 {rotate_path} test")

                return True
            else:
                print("\nError: No containers were successfully created")
                return False

        except Exception as e:
            self.logger.error(f"Error creating container pool: {e}")
            print(f"Error: {e}")
            return False

    def create_rotation_client(self) -> None:
        """Create a Python client for rotating through the container pool"""
        client_script = textwrap.dedent('''#!/usr/bin/env python3
"""
OmniProx Azure Container Pool Rotation Client
Automatically rotates through container pool for each request
"""

import json
import random
import sys
from typing import Dict, List

import requests

# Container pool configuration
CONTAINER_POOL = {pool_json}

class RotatingProxy:
    def __init__(self, container_pool: List[Dict]):
        self.pool = container_pool
        self.current_index = 0

    def get_random_proxy(self) -> str:
        """Get a random proxy from the pool"""
        return random.choice(self.pool)['url'] if self.pool else None

    def get_next_proxy(self) -> str:
        """Get the next proxy in rotation"""
        if not self.pool:
            return None
        proxy = self.pool[self.current_index]['url']
        self.current_index = (self.current_index + 1) % len(self.pool)
        return proxy

    def make_request(self, path="", method="GET", rotate_type="random", **kwargs):
        """Make a request through a proxy"""
        if rotate_type == "random":
            proxy_url = self.get_random_proxy()
        else:
            proxy_url = self.get_next_proxy()

        if not proxy_url:
            print("Error: No proxies available")
            return None

        full_url = f"{{proxy_url}}{{path}}"

        try:
            response = requests.request(method, full_url, **kwargs)
            proxy_ip = next((p['ip'] for p in self.pool if p['url'] == proxy_url), 'unknown')
            print(f"[OK] Request via: {{proxy_url}} (IP: {{proxy_ip}})")
            return response
        except Exception as e:
            print(f"Error: Request to {{proxy_url}} failed: {{e}}")
            return None

    def test_rotation(self, num_requests=5):
        """Test IP rotation with multiple requests"""
        print(f"\\n[ROTATE] Testing IP Rotation with {{num_requests}} requests:")
        print("-" * 60)

        ips_seen = set()
        successful = 0

        for i in range(num_requests):
            print(f"\\nRequest {{i+1}}:")
            response = self.make_request()
            if response:
                successful += 1
                # Try to extract IP from response
                if response.headers.get('X-Real-IP'):
                    ip = response.headers['X-Real-IP']
                elif 'ip' in response.text.lower():
                    # Try to extract IP from response body
                    ip = response.text.strip()[:20]
                else:
                    ip = "Response received"
                ips_seen.add(ip)
                print(f"  Response: {{ip[:50]}}")

        print("\\n" + "="*60)
        print(f"[STATS] Test Results:")
        print(f"  Successful Requests: {{successful}}/{{num_requests}}")
        print(f"  Unique Responses: {{len(ips_seen)}}")
        print(f"  Container Pool Size: {{len(self.pool)}}")
        print(f"  Unique IPs in Pool: {{len(set(c['ip'] for c in self.pool))}}")

def main():
    proxy = RotatingProxy(CONTAINER_POOL)

    if not CONTAINER_POOL:
        print("Error: No container pool configured")
        print("Run: python3 omniprox.py --provider azure-pool --command create --url <target>")
        return 1

    print(f"[GLOBAL] OmniProx Container Pool Active")
    print(f"   Pool Size: {{len(CONTAINER_POOL)}} containers")
    print(f"   Target: {{CONTAINER_POOL[0].get('target', 'unknown')}}")

    if len(sys.argv) > 1:
        if sys.argv[1] == "test":
            proxy.test_rotation(int(sys.argv[2]) if len(sys.argv) > 2 else 5)
        elif sys.argv[1] == "list":
            print("\\n[LIST] Container Pool:")
            for i, container in enumerate(CONTAINER_POOL, 1):
                print(f"  {{i}}. {{container['url']}} (IP: {{container['ip']}})")
        else:
            # Make request with provided path
            response = proxy.make_request(sys.argv[1])
            if response:
                print(response.text)
    else:
        # Make a single test request
        response = proxy.make_request()
        if response:
            print(f"\\n📄 Response: {{response.text[:200]}}")

if __name__ == "__main__":
    main()
        ''').strip().format(pool_json=json.dumps(self.container_pool, indent=2))

        # Save the client script
        rotate_path = _get_rotate_client_path()
        rotate_path.write_text(client_script)
        rotate_path.chmod(0o755)

        print(f"\n[OK] Rotation client created: {rotate_path}")

    def list(self):
        """List all containers in the pool"""
        if not self.init_provider():
            return False

        try:
            print("Listing Azure Container Pool...")

            # List all container groups
            all_containers = []
            container_groups = self.aci_client.container_groups.list()

            for group in container_groups:
                # Check if it's part of an OmniProx pool
                if group.tags and group.tags.get('created_by') == 'omniprox':
                    if group.tags.get('pool_id'):
                        container_info = {
                            'name': group.name,
                            'resource_group': group.id.split('/')[4],
                            'location': group.location,
                            'state': group.provisioning_state,
                            'pool_id': group.tags.get('pool_id'),
                            'target': group.tags.get('target_url'),
                            'number': group.tags.get('container_number', '?')
                        }

                        if group.ip_address:
                            container_info['ip'] = group.ip_address.ip
                            container_info['fqdn'] = group.ip_address.fqdn
                            container_info['url'] = f"http://{group.ip_address.fqdn or group.ip_address.ip}"

                        all_containers.append(container_info)

            # Group by pool
            pools = {}
            for container in all_containers:
                pool_id = container.get('pool_id', 'unknown')
                if pool_id not in pools:
                    pools[pool_id] = []
                pools[pool_id].append(container)

            if not pools:
                print("No container pools found")
                return True

            # Display pools
            print(f"\nFound {len(pools)} container pool(s):")
            print("="*60)

            for pool_id, containers in pools.items():
                print(f"\n[INFO] Pool ID: {pool_id}")
                print(f"   Containers: {len(containers)}")
                print(f"   Target: {containers[0].get('target', 'unknown')}")
                print(f"   Resource Group: {containers[0].get('resource_group', 'unknown')}")
                print(f"\n   Container Instances:")

                for container in sorted(containers, key=lambda x: int(x.get('number', 0))):
                    print(f"     #{container['number']}: {container.get('url', 'no-url')} (IP: {container.get('ip', 'no-ip')}) [{container['state']}]")

            # Load saved pool if exists
            if self.container_pool:
                print(f"\n[PINNED] Configured Pool ({len(self.container_pool)} containers):")
                for i, container in enumerate(self.container_pool, 1):
                    print(f"   {i}. {container['url']} (IP: {container['ip']})")

            return True

        except Exception as e:
            self.logger.error(f"Error listing container pools: {e}")
            print(f"Error: {e}")
            return False

    def delete(self):
        """Delete a specific container or entire pool"""
        if not self.init_provider():
            return False

        if self.api_id:
            # Delete specific container
            try:
                print(f"Deleting container: {self.api_id}")

                # Find resource group
                groups = self.aci_client.container_groups.list()
                for group in groups:
                    if group.name == self.api_id:
                        resource_group = group.id.split('/')[4]
                        self.aci_client.container_groups.begin_delete(
                            resource_group,
                            self.api_id
                        ).result()
                        print(f"[OK] Deleted container: {self.api_id}")
                        return True

                print(f"Container not found: {self.api_id}")
                return False

            except Exception as e:
                self.logger.error(f"Error deleting container: {e}")
                print(f"Error: {e}")
                return False
        else:
            # Delete entire configured pool
            if not self.container_pool:
                print("No container pool configured")
                return False

            print(f"Deleting container pool ({len(self.container_pool)} containers)...")

            deleted = 0
            for container in self.container_pool:
                try:
                    print(f"Deleting {container['name']}...")
                    self.aci_client.container_groups.begin_delete(
                        self.resource_group,
                        container['name']
                    ).result()
                    deleted += 1
                    print(f"  [OK] Deleted {container['name']}")
                except Exception as e:
                    print(f"  Error: Failed to delete {container['name']}: {e}")

            # Clear pool configuration
            self.container_pool = []
            self.save_pool_config()

            print(f"\n[OK] Deleted {deleted} containers from pool")
            return True

    def cleanup(self):
        """Delete all OmniProx container pools"""
        if not self.init_provider():
            return False

        try:
            print("Finding all OmniProx container pools...")

            # Find all OmniProx containers
            container_groups = self.aci_client.container_groups.list()
            omniprox_containers = []

            for group in container_groups:
                if group.tags and group.tags.get('created_by') == 'omniprox':
                    resource_group = group.id.split('/')[4]
                    omniprox_containers.append({
                        'name': group.name,
                        'resource_group': resource_group,
                        'pool_id': group.tags.get('pool_id', 'unknown')
                    })

            if not omniprox_containers:
                print("No OmniProx containers found to clean up")
                return True

            # Group by pool
            pools = {}
            for container in omniprox_containers:
                pool_id = container['pool_id']
                if pool_id not in pools:
                    pools[pool_id] = []
                pools[pool_id].append(container)

            print(f"\nFound {len(omniprox_containers)} containers in {len(pools)} pool(s)")
            for pool_id, containers in pools.items():
                print(f"  Pool {pool_id}: {len(containers)} containers")

            if not confirm_action("\nDelete all OmniProx containers?"):
                print("Cleanup cancelled")
                return False

            # Delete all containers
            deleted = 0
            for container in omniprox_containers:
                try:
                    print(f"Deleting {container['name']}...")
                    self.aci_client.container_groups.begin_delete(
                        container['resource_group'],
                        container['name']
                    ).result()
                    deleted += 1
                except Exception as e:
                    print(f"  Failed to delete {container['name']}: {e}")

            # Clear saved pool configuration
            self.container_pool = []
            self.save_pool_config()

            print(f"\n[OK] Cleanup completed: deleted {deleted} containers")
            return True

        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
            print(f"Error: {e}")
            return False

    def status(self):
        """Get status of container pool"""
        return self.list()

    def create_profile(self, config, profile_name):
        """Create a new profile configuration"""
        self.config = config
        config[profile_name] = {
            'subscription_id': '',
            'location': 'eastus',
            'resource_group': '',
            'use_cli': 'true',
            'container_pool': '[]'
        }

    def update(self):
        """Update container pool configuration"""
        print("Update command not implemented for container pools")
        print("Use 'delete' and 'create' to modify the pool")
        return False

    def usage(self):
        """Show usage statistics for container pool"""
        if not self.container_pool:
            print("No container pool configured")
            return False

        print(f"Container Pool Usage Statistics:")
        print(f"  Pool Size: {len(self.container_pool)}")
        print(f"  Unique IPs: {len(set(c['ip'] for c in self.container_pool))}")
        print(f"  Target URL: {self.container_pool[0].get('target', 'unknown')}")

        return True

    def proxytest(self):
        """Test IP rotation with the container pool"""
        if not self.container_pool:
            print("No container pool configured. Creating test pool...")

            # Save original URL and set test URL
            original_url = self.url
            self.url = 'https://ipinfo.io/ip'
            self.pool_size = 3  # Create 3 containers for testing

            # Create test pool
            if self.create():
                # Test rotation
                print("\n" + "="*60)
                print("[TEST] TESTING IP ROTATION")
                print("="*60)

                rotate_path = _get_rotate_client_path()
                result = subprocess.run(
                    ['python3', str(rotate_path), 'test', '10'],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                print(result.stdout)

                # Offer to clean up
                try:
                    cleanup = input("\n[CLEAN] Delete test containers? (yes/no): ").strip().lower()
                    if cleanup == 'yes':
                        self.cleanup()
                except (EOFError, KeyboardInterrupt):
                    print("\nSkipping cleanup (non-interactive mode)")
                    print(f"Run 'omniprox --provider azure --command cleanup' to clean up manually")

            self.url = original_url
        else:
            # Test existing pool
            print("Testing existing container pool...")
            rotate_path = _get_rotate_client_path()
            result = subprocess.run(
                ['python3', str(rotate_path), 'test'],
                capture_output=True,
                text=True,
                timeout=60
            )
            print(result.stdout)

        return True