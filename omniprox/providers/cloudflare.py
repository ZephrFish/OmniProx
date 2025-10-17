"""
Cloudflare Provider for OmniProx
Implements Cloudflare Workers proxy functionality
"""

import json
import logging
import configparser
import sys
import time
import random
import string
from typing import Optional, Dict, Any, List
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: requests library required for Cloudflare provider")
    print("Install with: pip install requests")
    sys.exit(1)

from ..core.base import BaseOmniProx
from ..core.utils import normalize_url


class CloudflareProvider(BaseOmniProx):
    """Cloudflare Workers provider for OmniProx"""

    def __init__(self, args: Any):
        """Initialize Cloudflare provider

        Args:
            args: Command line arguments
        """
        # Initialize attributes before calling parent __init__
        self.api_token = None
        self.account_id = None
        self.zone_id = None
        self.base_url = 'https://api.cloudflare.com/client/v4'
        self.endpoints_file = Path.home() / '.omniprox' / 'cloudflare_endpoints.json'
        self._worker_subdomain = None

        # Check for environment variable to hide subdomain
        import os
        self.hide_subdomain = os.getenv("OMNIPROX_HIDE_SUBDOMAIN", "").lower() in ["true", "1", "yes"]

        # Now call parent __init__ which will call load_profile
        super().__init__('cloudflare', args)

    def create_profile(self, config: configparser.ConfigParser, profile_name: str):
        """Create a new Cloudflare profile"""
        import getpass

        print("\nCloudflare Configuration")
        print("="*60)
        print("Steps to get your Cloudflare credentials:")
        print("1. Sign up at https://cloudflare.com")
        print("2. Go to https://dash.cloudflare.com/profile/api-tokens")
        print("3. Create Custom Token with 'Account:Cloudflare Workers Scripts:Edit' permission")
        print("4. Copy the token and your Account ID from the dashboard")
        print("="*60)
        print()

        config[profile_name] = {}
        config[profile_name]['api_token'] = getpass.getpass("Cloudflare API Token: ").strip()
        config[profile_name]['account_id'] = input("Cloudflare Account ID: ").strip()
        config[profile_name]['zone_id'] = input("Cloudflare Zone ID (optional): ").strip() or ''

        self.save_profile(config)
        self.load_profile(config, profile_name)

    def load_profile(self, config: configparser.ConfigParser, profile_name: str):
        """Load Cloudflare profile from configuration"""
        if profile_name in config:
            self.api_token = config[profile_name].get('api_token', '')
            self.account_id = config[profile_name].get('account_id', '')
            self.zone_id = config[profile_name].get('zone_id', '')

        # Ensure endpoints directory exists
        self.endpoints_file.parent.mkdir(parents=True, exist_ok=True)

    @property
    def headers(self) -> Dict[str, str]:
        """Get API request headers"""
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }

    @property
    def worker_subdomain(self) -> str:
        """Get the worker subdomain for workers.dev URLs"""
        if self._worker_subdomain:
            return self._worker_subdomain

        # Try to get configured subdomain
        url = f"{self.base_url}/accounts/{self.account_id}/workers/subdomain"
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if data.get("success") and data.get("result"):
                    subdomain = data["result"].get("subdomain")
                    if subdomain:
                        self._worker_subdomain = subdomain
                        if self.hide_subdomain:
                            self.logger.info("Found worker subdomain: [HIDDEN]")
                        else:
                            self.logger.info(f"Found worker subdomain: {subdomain}")
                        return subdomain
        except requests.RequestException as e:
            self.logger.warning(f"Could not fetch subdomain: {e}")

        # If no subdomain exists, we need to create one or use the account name
        # Workers use a specific subdomain, not the account ID
        # We should prompt the user to set this up
        self.logger.warning("No workers subdomain configured")
        return None

    def _ensure_subdomain(self) -> Optional[str]:
        """Ensure a workers subdomain is configured"""
        subdomain = self.worker_subdomain
        if subdomain:
            return subdomain

        # Try to create/enable subdomain
        url = f"{self.base_url}/accounts/{self.account_id}/workers/subdomain"

        # Generate a generic subdomain name for OPSEC (no obvious tool/service indicators)
        import hashlib
        subdomain_name = f"api-{hashlib.md5(self.account_id.encode()).hexdigest()[:8]}"

        try:
            # First check if we can get the existing subdomain
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("success") and data.get("result"):
                    existing = data["result"].get("subdomain")
                    if existing:
                        self._worker_subdomain = existing

                        # Check if subdomain might reveal personal/account info
                        sensitive_patterns = ['name', 'user', 'personal', 'company', 'respect', 'real', 'deez']
                        if any(pattern in existing.lower() for pattern in sensitive_patterns):
                            if not self.hide_subdomain:
                                print("\nOPSEC WARNING: Worker subdomain may reveal account identity")
                                print(f"   Current subdomain: {existing}.workers.dev")
                                print("   To change this subdomain:")
                                print("   1. Delete all workers: omniprox --provider cf --command cleanup")
                                print("   2. Go to: https://dash.cloudflare.com/workers")
                                print("   3. Change subdomain in Account Settings")
                                print("   4. Use a generic name like: api-proxy, worker-service, etc.")
                                print("   5. Or set: export OMNIPROX_HIDE_SUBDOMAIN=true\n")

                        return existing

            # Try to create subdomain
            response = requests.put(
                url,
                headers=self.headers,
                json={"subdomain": subdomain_name},
                timeout=10
            )

            if response.status_code in [200, 409]:  # 409 means already exists
                # Fetch it again to get the actual subdomain
                response = requests.get(url, headers=self.headers, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success") and data.get("result"):
                        subdomain = data["result"].get("subdomain")
                        if subdomain:
                            self._worker_subdomain = subdomain
                            return subdomain

        except requests.RequestException as e:
            self.logger.error(f"Failed to setup subdomain: {e}")

        return None

    def _generate_worker_name(self) -> str:
        """Generate a unique worker name with generic naming for OPSEC"""
        timestamp = str(int(time.time()))
        random_suffix = ''.join(random.choices(string.ascii_lowercase, k=6))

        # Use more generic prefix options for better OPSEC
        prefixes = ['proxy', 'worker', 'api', 'service', 'app', 'edge']
        prefix = random.choice(prefixes)

        return f"{prefix}-{timestamp}-{random_suffix}"

    def _get_worker_script(self) -> str:
        """Return the optimized Cloudflare Worker script with better performance and security"""
        return '''// OmniProx Cloudflare Worker - Optimized
const ALLOWED_HEADERS = new Set([
  'accept', 'accept-language', 'accept-encoding', 'authorization',
  'cache-control', 'content-type', 'origin', 'referer', 'user-agent',
  'x-api-key', 'x-auth-token', 'x-requested-with'
])

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS, PATCH, HEAD',
  'Access-Control-Allow-Headers': '*',
  'Access-Control-Max-Age': '86400'
}

addEventListener('fetch', event => {
  event.respondWith(handleRequest(event.request))
})

async function handleRequest(request) {
  // Fast CORS preflight response
  if (request.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: CORS_HEADERS })
  }

  try {
    const url = new URL(request.url)

    // Handle status endpoint
    if (url.pathname === '/status') {
      return jsonResponse({
        status: 'operational',
        provider: 'cloudflare',
        type: 'worker'
      })
    }

    // Base URL that was configured during worker creation
    const BASE_URL = '___TARGET_URL___'

    // Extract target URL (query param > header > path)
    let targetUrl = url.searchParams.get('url') ||
                   request.headers.get('X-Target-URL')

    let preservePath = false

    // If not found, try to extract from path
    if (!targetUrl && url.pathname !== '/' && url.pathname !== '/status') {
      targetUrl = extractPathUrl(url.pathname)

      // If still no URL found and we have a base URL, use path-based routing
      if (!targetUrl && BASE_URL && BASE_URL !== 'https://domaingoeshere.local') {
        // The path should be appended to the base URL
        targetUrl = BASE_URL
        preservePath = true
      }
    }

    if (!targetUrl) {
      return jsonError('No target URL provided', 400, {
        usage: '?url=https://example.com or /path/to/proxy or X-Target-URL header',
        baseUrl: BASE_URL !== 'https://domaingoeshere.local' ? BASE_URL : undefined
      })
    }

    // Validate target URL
    let targetURL
    try {
      targetURL = new URL(targetUrl)

      // If we're preserving the path, append the request path to the target URL
      if (preservePath && url.pathname !== '/') {
        // Combine the base URL with the request path
        targetURL.pathname = targetURL.pathname.replace(/\/$/, '') + url.pathname
      }

      // Block private IPs for security
      if (isPrivateIP(targetURL.hostname)) {
        return jsonError('Private IPs not allowed', 403)
      }
    } catch (e) {
      return jsonError('Invalid URL format', 400, { url: targetUrl })
    }

    // Forward query params (except control params)
    const params = new URLSearchParams()
    for (const [key, value] of url.searchParams) {
      if (!['url', '_cb', '_t'].includes(key)) {
        params.append(key, value)
      }
    }
    if (params.toString()) {
      targetURL.search = params.toString()
    }

    // Build optimized request
    const proxyRequest = buildRequest(request, targetURL)

    // Execute with timeout
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 29000)

    try {
      const response = await fetch(proxyRequest, {
        signal: controller.signal,
        cf: { cacheTtl: 0 }
      })
      clearTimeout(timeout)
      return buildResponse(response)
    } catch (e) {
      clearTimeout(timeout)
      if (e.name === 'AbortError') {
        return jsonError('Request timeout', 504)
      }
      throw e
    }

  } catch (error) {
    return jsonError('Proxy failed', 500, {
      error: error.message
    })
  }
}

function extractPathUrl(pathname) {
  if (pathname && pathname !== '/') {
    // Remove leading slash
    let path = pathname.slice(1)

    // Check if it's a full URL (http:// or https://)
    if (path.startsWith('http://') || path.startsWith('https://')) {
      return path
    }

    // Handle Cloudflare's path normalization (https:/ -> https://)
    if (path.startsWith('http:/') && !path.startsWith('http://')) {
      return 'http://' + path.slice(6)  // 'http:/' has 6 chars
    }
    if (path.startsWith('https:/') && !path.startsWith('https://')) {
      return 'https://' + path.slice(7)  // 'https:/' has 7 chars
    }

    // Handle edge cases like double slashes
    if (path.startsWith('/')) {
      path = path.slice(1)
      if (path.startsWith('http://') || path.startsWith('https://')) {
        return path
      }
      // Check again for normalized paths
      if (path.startsWith('http:/') && !path.startsWith('http://')) {
        return 'http://' + path.slice(6)
      }
      if (path.startsWith('https:/') && !path.startsWith('https://')) {
        return 'https://' + path.slice(7)
      }
    }

    // If no protocol found, treat the entire path as a path to append to the base URL
    // This will be handled in the main request handler
    return null
  }
  return null
}

function isPrivateIP(hostname) {
  const patterns = [
    /^127\\./, /^10\\./, /^172\\.(1[6-9]|2[0-9]|3[01])\\./,
    /^192\\.168\\./, /^localhost$/i, /^::1$/
  ]
  return patterns.some(p => p.test(hostname))
}

function buildRequest(request, targetURL) {
  const headers = new Headers()

  // Copy allowed headers
  for (const [key, value] of request.headers) {
    if (ALLOWED_HEADERS.has(key.toLowerCase())) {
      headers.set(key, value)
    }
  }

  headers.set('Host', targetURL.hostname)

  // Handle custom X-Forwarded-For from X-My-X-Forwarded-For header
  const customForwardedFor = request.headers.get('X-My-X-Forwarded-For')
  if (customForwardedFor) {
    headers.set('X-Forwarded-For', customForwardedFor)
    headers.set('X-Real-IP', customForwardedFor.split(',')[0].trim())
  } else {
    // Generate rotating IPs for X-Forwarded-For
    // Note: This only sets the header - actual request still comes from Cloudflare IPs
    const ips = [generateIP(), generateIP()].join(', ')
    headers.set('X-Forwarded-For', ips)
    headers.set('X-Real-IP', generateIP())
  }
  headers.set('CF-Connecting-IP', generateIP())

  return new Request(targetURL.toString(), {
    method: request.method,
    headers: headers,
    body: ['GET', 'HEAD'].includes(request.method) ? null : request.body,
    redirect: 'follow'
  })
}

function buildResponse(response) {
  const headers = new Headers()

  // Copy safe headers
  const skip = new Set(['content-encoding', 'content-length', 'transfer-encoding'])
  for (const [key, value] of response.headers) {
    if (!skip.has(key.toLowerCase())) {
      headers.set(key, value)
    }
  }

  // Add CORS
  Object.entries(CORS_HEADERS).forEach(([k, v]) => headers.set(k, v))

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: headers
  })
}

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', ...CORS_HEADERS }
  })
}

function jsonError(message, status, details = {}) {
  return jsonResponse({ error: message, ...details }, status)
}

function generateIP() {
  // Use diverse, realistic IP ranges from various providers
  const ranges = [
    // Residential ISP ranges
    [[73], [245], [68], [98]],      // Comcast
    [[24], [143], [72], [56]],      // Charter
    [[71], [192], [84], [103]],     // Verizon
    [[47], [156], [92], [201]],     // AT&T
    // Cloud/Hosting ranges
    [[104], [16], [null], [null]],  // Cloudflare
    [[172], [217], [null], [null]], // Google
    [[151], [101], [null], [null]], // Fastly
    [[13], [107], [null], [null]],  // Cloud provider
    // International ranges
    [[185], [null], [null], [null]], // European
    [[103], [null], [null], [null]], // Asian
    [[41], [null], [null], [null]],  // African
  ]

  const template = ranges[Math.floor(Math.random() * ranges.length)]
  return template.map(part => {
    if (Array.isArray(part)) {
      return part[Math.floor(Math.random() * part.length)]
    }
    return part ?? Math.floor(Math.random() * 254) + 1
  }).join('.')
}'''

    def init_provider(self) -> bool:
        """Initialize Cloudflare provider"""
        if not self.api_token or not self.account_id:
            self.logger.error("Cloudflare API token and account ID required")
            print("Error: Cloudflare credentials not configured")
            print("Run 'omniprox --setup' to configure")
            return False

        # Verify credentials by checking account access
        try:
            verify_url = f"{self.base_url}/accounts/{self.account_id}"
            response = requests.get(verify_url, headers=self.headers, timeout=10)

            if response.status_code == 401:
                self.logger.error("Invalid Cloudflare API token")
                print("\nError: Invalid Cloudflare API token")
                print("\nTo fix this:")
                print("1. Go to https://dash.cloudflare.com/profile/api-tokens")
                print("2. Create a new token with these permissions:")
                print("   - Account → Cloudflare Workers Scripts → Edit")
                print("   - Account → Account Settings → Read (optional)")
                print("3. Run 'omniprox --setup' and select Cloudflare to update your token")
                return False
            elif response.status_code == 403:
                self.logger.error("API token lacks required permissions")
                print("\nError: API token lacks required permissions")
                print("Your token needs 'Account:Cloudflare Workers Scripts:Edit' permission")
                print("Please create a new token with the correct permissions")
                return False
            elif response.status_code != 200:
                self.logger.error(f"Failed to verify Cloudflare credentials: {response.status_code}")
                print(f"\nError verifying Cloudflare credentials: {response.status_code}")
                return False

            # Successfully verified
            self.logger.info("Cloudflare credentials verified successfully")
            return True

        except requests.RequestException as e:
            self.logger.error(f"Failed to verify Cloudflare credentials: {e}")
            print(f"\nError connecting to Cloudflare API: {e}")
            return False

    def create(self) -> bool:
        """Create one or more Cloudflare Workers proxies"""
        if not self.init_provider():
            return False

        if not self.url:
            self.logger.error("URL is required for create command")
            print("Error: --url is required for create command")
            return False

        target_url = normalize_url(self.url)

        # Get number of proxies to create (default is 1)
        num_proxies = getattr(self.args, 'number', 1)
        if num_proxies < 1:
            num_proxies = 1
        elif num_proxies > 10:
            print(f"Warning: Limited to 10 proxies per batch. Creating 10 instead of {num_proxies}.")
            num_proxies = 10

        if num_proxies > 1:
            self.logger.info(f"Creating {num_proxies} Cloudflare Workers for {target_url}")
            print(f"\nCreating {num_proxies} Cloudflare Worker proxies for: {target_url}")
        else:
            self.logger.info(f"Creating Cloudflare Worker for {target_url}")
            print(f"\nCreating Cloudflare Worker proxy for: {target_url}")

        created_workers = []
        failed_count = 0

        try:
            # Ensure we have a workers subdomain configured (once for all workers)
            subdomain = self._ensure_subdomain()
            if not subdomain:
                self.logger.error("Could not get or create workers subdomain")
                print("\nError: Could not configure workers subdomain")
                print("Please ensure your account has Workers enabled")
                print("Visit: https://dash.cloudflare.com/workers")
                return False

            # Show prominent warning if subdomain might reveal identity
            sensitive_patterns = ['name', 'user', 'personal', 'company', 'respect', 'real', 'deez']
            if any(pattern in subdomain.lower() for pattern in sensitive_patterns) and not self.hide_subdomain:
                print("\n" + "="*60)
                print("OPSEC WARNING: Subdomain Reveals Account Identity")
                print("="*60)
                print(f"Subdomain: {subdomain}.workers.dev")
                print("\nThis subdomain is PERMANENT and cannot be changed.")
                print("Every worker will use this subdomain.")
                print("\nFor better OPSEC, consider:")
                print("1. Create new Cloudflare account with generic subdomain")
                print("2. Use custom domain (Workers Paid Plan)")
                print("3. Use other providers for sensitive operations")
                print("4. Set environment variable: export OMNIPROX_HIDE_SUBDOMAIN=true")
                print("\nSee docs/CLOUDFLARE_LIMITATIONS.md for details")
                print("="*60)

            # Create multiple workers if requested
            for i in range(num_proxies):
                try:
                    if num_proxies > 1:
                        print(f"\nCreating proxy {i+1}/{num_proxies}...")

                    worker_name = self._generate_worker_name()
                    script_content = self._get_worker_script()

                    # Replace the target URL placeholder with the actual URL
                    script_content = script_content.replace('___TARGET_URL___', target_url)

                    # Deploy the worker script
                    url = f"{self.base_url}/accounts/{self.account_id}/workers/scripts/{worker_name}"

                    files = {
                        'metadata': (None, json.dumps({
                            "body_part": "script",
                            "main_module": "worker.js"
                        })),
                        'script': ('worker.js', script_content, 'application/javascript')
                    }

                    headers = {"Authorization": f"Bearer {self.api_token}"}

                    response = requests.put(url, headers=headers, files=files, timeout=60)

                    if response.status_code == 401:
                        self.logger.error("Authentication failed - invalid API token")
                        print("\nError: Invalid Cloudflare API token")
                        print("Please check your API token has the correct permissions:")
                        print("  - Account → Cloudflare Workers Scripts → Edit")
                        if num_proxies == 1:
                            return False
                        failed_count += 1
                        continue
                    elif response.status_code == 403:
                        self.logger.error("Permission denied - token lacks required permissions")
                        print("\nError: Your API token doesn't have permission to create Workers")
                        print("Please create a new token with 'Account:Cloudflare Workers Scripts:Edit' permission")
                        if num_proxies == 1:
                            return False
                        failed_count += 1
                        continue

                    response.raise_for_status()

                    # Enable subdomain
                    subdomain_url = f"{self.base_url}/accounts/{self.account_id}/workers/scripts/{worker_name}/subdomain"
                    try:
                        requests.post(subdomain_url, headers=self.headers, json={"enabled": True}, timeout=30)
                    except requests.RequestException:
                        pass  # Subdomain enabling is not critical

                    worker_url = f"https://{worker_name}.{subdomain}.workers.dev"

                    # Mask subdomain if requested
                    display_url = worker_url
                    if self.hide_subdomain:
                        display_url = f"https://{worker_name}.[HIDDEN].workers.dev"

                    # Save endpoint info (always save real URL)
                    endpoint = {
                        "name": worker_name,
                        "url": worker_url,
                        "target_url": target_url,
                        "created_at": time.strftime('%Y-%m-%d %H:%M:%S'),
                        "provider": "cloudflare"
                    }

                    self._save_endpoint(endpoint)
                    created_workers.append({
                        "name": worker_name,
                        "url": worker_url
                    })

                    if num_proxies == 1:
                        print("\nCloudflare Worker created successfully!")
                        print(f"Worker Name: {worker_name}")
                        print(f"Worker URL:  {display_url}")
                        print(f"Target URL:  {target_url}")
                        print("\nUsage examples:")
                        if self.hide_subdomain:
                            print(f"  # Note: Replace [HIDDEN] with actual subdomain")
                            print(f"  curl '{display_url}?url={target_url}'")
                            print(f"  curl -H 'X-Target-URL: {target_url}' {display_url}")
                            print(f"  curl {display_url}/{target_url}")
                        else:
                            print(f"  curl '{worker_url}?url={target_url}'")
                            print(f"  curl -H 'X-Target-URL: {target_url}' {worker_url}")
                            print(f"  curl {worker_url}/{target_url}")
                    else:
                        print(f"  [OK] Created: {worker_name}")
                        print(f"       URL: {display_url}")

                except requests.RequestException as e:
                    self.logger.error(f"Failed to create worker {i+1}: {e}")
                    print(f"  [FAILED] Error creating worker: {e}")
                    failed_count += 1
                    if num_proxies == 1:
                        return False
                    continue

            # Summary for batch creation
            if num_proxies > 1:
                print(f"\n" + "="*60)
                print(f"Batch Creation Summary")
                print("="*60)
                print(f"Successfully created: {len(created_workers)} workers")
                if failed_count > 0:
                    print(f"Failed: {failed_count} workers")
                print(f"Target URL: {target_url}")
                print(f"\nCreated Workers:")
                for worker in created_workers:
                    print(f"  - {worker['url']}")
                print(f"\nUsage example (for any worker):")
                if created_workers:
                    print(f"  curl '{created_workers[0]['url']}?url={target_url}'")

            return len(created_workers) > 0

        except Exception as e:
            self.logger.error(f"Unexpected error in batch creation: {e}")
            print(f"Error during batch creation: {e}")
            return len(created_workers) > 0

    def _create_single_proxy(self) -> bool:
        """Create a single proxy for testing purposes"""
        # Force single proxy creation
        original_args = getattr(self.args, 'number', 1)
        if hasattr(self.args, 'number'):
            self.args.number = 1

        result = self.create()

        # Restore original args
        if hasattr(self.args, 'number'):
            self.args.number = original_args

        return result

    def _get_last_created_proxy_url(self):
        """Get the URL of the last created Cloudflare Worker"""
        try:
            # Get the most recent worker from endpoints
            endpoints = self.sync_endpoints()
            if endpoints:
                # Return the most recent worker URL with the test URL parameter
                latest_worker = max(endpoints, key=lambda x: x.get('created_at', ''))
                worker_url = latest_worker.get('url', '')
                if worker_url:
                    # Format for ipinfo.io test
                    return f"{worker_url}?url=https://ipinfo.io/ip"
            return None
        except Exception as e:
            self.logger.error(f"Error getting last created proxy URL: {e}")
            return None

    def list(self) -> bool:
        """List all Cloudflare Workers proxies"""
        if not self.init_provider():
            return False

        self.logger.info("Listing Cloudflare Workers")

        try:
            # Sync with remote workers
            endpoints = self.sync_endpoints()

            if not endpoints:
                print("No OmniProx Cloudflare Workers found")
                print("Create one with: omniprox --provider cloudflare --command create --url https://domaingoeshere.local")
                return True

            print(f"\nOmniProx Cloudflare Workers ({len(endpoints)} total):")
            print("-" * 80)
            print(f"{'Name':<35} {'URL':<40}")
            print("-" * 80)

            for endpoint in endpoints:
                name = endpoint.get("name", "unknown")
                url = endpoint.get("url", "unknown")
                print(f"{name:<35} {url:<40}")

            print("\nTo delete a specific worker:")
            print("  omniprox --provider cloudflare --command delete --api_id <worker-name>")

            return True

        except Exception as e:
            self.logger.error(f"Failed to list workers: {e}")
            print(f"Error listing workers: {e}")
            return False

    def delete(self) -> bool:
        """Delete a Cloudflare Workers proxy"""
        if not self.init_provider():
            return False

        if not self.api_id:
            self.logger.error("API ID (worker name) is required for delete command")
            print("Error: --api_id is required for delete command")
            print("Use 'list' command to see available worker names")
            return False

        self.logger.info(f"Deleting Cloudflare Worker: {self.api_id}")

        try:
            url = f"{self.base_url}/accounts/{self.account_id}/workers/scripts/{self.api_id}"
            response = requests.delete(url, headers=self.headers, timeout=30)

            if response.status_code in [200, 404]:
                print(f"Deleted Cloudflare Worker: {self.api_id}")

                # Remove from local cache
                self._remove_endpoint(self.api_id)

                return True
            else:
                print(f"Failed to delete worker: {response.text}")
                return False

        except requests.RequestException as e:
            self.logger.error(f"Failed to delete worker: {e}")
            print(f"Error deleting worker: {e}")
            return False

    def cleanup(self) -> bool:
        """Delete all Cloudflare Workers proxies"""
        if not self.init_provider():
            return False

        self.logger.info("Cleaning up all Cloudflare Workers")

        # Check if running in non-interactive mode
        import sys
        if not sys.stdin.isatty():
            confirm = "yes"  # Auto-confirm in non-interactive mode
        else:
            confirm = input("Delete ALL OmniProx Cloudflare Workers? (yes/no): ")

        if confirm.lower() != 'yes':
            print("Cleanup cancelled")
            return False

        try:
            endpoints = self.sync_endpoints()

            if not endpoints:
                print("No workers to clean up")
                return True

            deleted = 0
            failed = 0

            print(f"\nDeleting {len(endpoints)} workers...")

            # Prefixes used by _generate_worker_name()
            omniprox_prefixes = ('proxy-', 'worker-', 'api-', 'service-', 'app-', 'edge-', 'omniprox-')

            for endpoint in endpoints:
                name = endpoint.get('name', '')
                if name.startswith(omniprox_prefixes):
                    url = f"{self.base_url}/accounts/{self.account_id}/workers/scripts/{name}"
                    try:
                        response = requests.delete(url, headers=self.headers, timeout=30)
                        if response.status_code in [200, 404]:
                            print(f"  [OK] Deleted: {name}")
                            deleted += 1
                        else:
                            print(f"  [FAILED] Failed to delete: {name}")
                            failed += 1
                    except requests.RequestException:
                        print(f"  [ERROR] Error deleting: {name}")
                        failed += 1

            # Clear local cache
            if self.endpoints_file.exists():
                self.endpoints_file.unlink()

            print(f"\nCleanup complete: {deleted} deleted, {failed} failed")
            return True

        except Exception as e:
            self.logger.error(f"Cleanup failed: {e}")
            print(f"Error during cleanup: {e}")
            return False

    def status(self) -> bool:
        """Check Cloudflare Workers status"""
        if not self.init_provider():
            return False

        self.logger.info("Checking Cloudflare Workers status")

        try:
            # Get account info
            account_url = f"{self.base_url}/accounts/{self.account_id}"
            response = requests.get(account_url, headers=self.headers, timeout=30)

            if response.status_code == 200:
                data = response.json()
                account_info = data.get("result", {})

                print("\nCloudflare Account Status:")
                print("="*60)
                print(f"Account Name: {account_info.get('name', 'N/A')}")
                print(f"Account ID:   {self.account_id}")

                # Get worker subdomain
                print(f"Workers Domain: {self.worker_subdomain}.workers.dev")

                # Count active workers
                endpoints = self.sync_endpoints()
                print(f"Active Workers: {len(endpoints)}")

                # Check daily request limit
                print("\nFree Tier Limits:")
                print("  Daily Requests: 100,000")
                print("  CPU Time: 10ms per request")

                print("\nNote: Detailed usage statistics require additional API permissions")

                return True
            else:
                print(f"Failed to get account status: {response.text}")
                return False

        except requests.RequestException as e:
            self.logger.error(f"Failed to check status: {e}")
            print(f"Error checking status: {e}")
            return False

    def usage(self) -> bool:
        """Check usage statistics (not fully implemented for Cloudflare)"""
        if not self.init_provider():
            return False

        print("\nCloudflare Workers Usage:")
        print("="*60)
        print("Detailed usage statistics require Cloudflare Analytics API access.")
        print("\nFree Tier Limits:")
        print("  Daily Requests: 100,000")
        print("  CPU Time: 10ms per request")
        print("\nFor detailed usage, visit:")
        print(f"  https://dash.cloudflare.com/{self.account_id}/workers/overview")

        return True

    def sync_endpoints(self) -> List[Dict]:
        """Sync local endpoints with remote deployments"""
        try:
            # Get subdomain first
            subdomain = self._ensure_subdomain()
            if not subdomain:
                self.logger.warning("No subdomain configured, using local cache")
                return self._load_endpoints()

            # Get list of all workers from API
            url = f"{self.base_url}/accounts/{self.account_id}/workers/scripts"
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()

            data = response.json()
            remote_workers = []

            # Prefixes used by _generate_worker_name()
            omniprox_prefixes = ('proxy-', 'worker-', 'api-', 'service-', 'app-', 'edge-', 'omniprox-')

            for script in data.get("result", []):
                name = script.get("id", "")
                if name.startswith(omniprox_prefixes):
                    remote_workers.append({
                        "name": name,
                        "url": f"https://{name}.{subdomain}.workers.dev",
                        "created_at": script.get("created_on", "unknown"),
                        "provider": "cloudflare"
                    })

            # Save to local cache
            self._save_all_endpoints(remote_workers)
            return remote_workers

        except requests.RequestException as e:
            self.logger.warning(f"Failed to sync endpoints: {e}")
            # Fall back to local cache
            return self._load_endpoints()

    def _save_endpoint(self, endpoint: Dict):
        """Save a single endpoint to local cache"""
        endpoints = self._load_endpoints()

        # Update or add endpoint
        existing = False
        for i, ep in enumerate(endpoints):
            if ep.get('name') == endpoint.get('name'):
                endpoints[i] = endpoint
                existing = True
                break

        if not existing:
            endpoints.append(endpoint)

        self._save_all_endpoints(endpoints)

    def _remove_endpoint(self, name: str):
        """Remove an endpoint from local cache"""
        endpoints = self._load_endpoints()
        endpoints = [ep for ep in endpoints if ep.get('name') != name]
        self._save_all_endpoints(endpoints)

    def _save_all_endpoints(self, endpoints: List[Dict]):
        """Save all endpoints to file"""
        try:
            with open(self.endpoints_file, 'w') as f:
                json.dump(endpoints, f, indent=2)
        except IOError as e:
            self.logger.warning(f"Could not save endpoints: {e}")

    def _load_endpoints(self) -> List[Dict]:
        """Load saved endpoints from file"""
        if self.endpoints_file.exists():
            try:
                with open(self.endpoints_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return []