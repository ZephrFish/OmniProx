"""
OmniProx First-Time Setup Module
Handles initial configuration and project creation for all cloud providers
"""

import os
import sys
import subprocess
import configparser
import json
from pathlib import Path
from datetime import datetime
import logging
import getpass


class OmniProxSetup:
    """First-time setup wizard for OmniProx"""

    def _check_azure_cli(self) -> dict:
        """Check Azure CLI authentication and return account info.

        Returns:
            dict with 'success', 'account' (if success), and 'error' (if failed)
        """
        try:
            result = subprocess.run(['az', 'account', 'show'],
                                  capture_output=True, text=True, check=False, timeout=30)
            if result.returncode == 0:
                account = json.loads(result.stdout)
                return {'success': True, 'account': account}
            else:
                return {'success': False, 'error': "Azure CLI not logged in. Run 'az login' first."}
        except FileNotFoundError:
            return {'success': False, 'error': "Azure CLI not installed. Please install it first."}
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': "Azure CLI check timed out."}

    def _get_azure_service_principal(self) -> dict:
        """Collect Azure service principal credentials from user.

        Returns:
            dict with subscription_id, tenant_id, client_id, client_secret
        """
        return {
            'subscription_id': input("Azure Subscription ID: ").strip(),
            'tenant_id': input("Tenant ID: ").strip(),
            'client_id': input("Client ID (App ID): ").strip(),
            'client_secret': getpass.getpass("Client Secret: ").strip()
        }

    def __init__(self):
        """Initialize setup wizard"""
        self.config_dir = Path.home() / '.omniprox'
        self.profiles_file = self.config_dir / 'profiles.ini'

    def run_first_time_setup(self):
        """Run the interactive setup wizard"""
        print("\n" + "="*60)
        print("        OmniProx First-Time Setup Wizard ")
        print("="*60)
        print("\nWelcome to OmniProx! Let's set up your cloud providers.")
        print("\nOmniProx creates HTTP pass-through proxies using:")
        print(" - Cloudflare Workers (Recommended)")
        print(" - Azure Container Instances")
        print(" - Azure Front Door (Global CDN)")
        print(" - Google Cloud API Gateway")
        print(" - GCP HTTPS Load Balancer")
        print(" - Alibaba Cloud API Gateway")

        self.config_dir.mkdir(exist_ok=True)
        print(f"\n[OK] Configuration directory: {self.config_dir}")

        if self.profiles_file.exists():
            print(f"[OK] Found existing configuration at {self.profiles_file}")
            response = input("\nWould you like to add more provider profiles? (y/n): ").strip().lower()
            if response != 'y':
                print("Setup cancelled.")
                return False
        else:
            print(f"[OK] Will create configuration at {self.profiles_file}")

        print("\n" + "="*60)
        print("Provider Setup")
        print("="*60)
        print("\nWhich cloud providers would you like to configure?")
        print("  1. Cloudflare Workers (Recommended)")
        print("  2. Azure Container Instances")
        print("  3. Azure Front Door")
        print("  4. Google Cloud API Gateway")
        print("  5. GCP Load Balancer")
        print("  6. Alibaba Cloud")
        print("  7. All providers")
        print("  8. Skip setup")

        choice = input("\nSelect option (1-8): ").strip()

        providers = []
        if choice == '1':
            providers = ['cloudflare']
        elif choice == '2':
            providers = ['azure']
        elif choice == '3':
            providers = ['azure_frontdoor']
        elif choice == '4':
            providers = ['gcp']
        elif choice == '5':
            providers = ['gcp_loadbalancer']
        elif choice == '6':
            providers = ['alibaba']
        elif choice == '7':
            providers = ['cloudflare', 'azure', 'azure_frontdoor', 'gcp', 'gcp_loadbalancer', 'alibaba']
        elif choice == '8':
            print("\nSetup skipped.")
            return True
        else:
            print("Invalid choice. Setup cancelled.")
            return False

        config = configparser.ConfigParser()
        if self.profiles_file.exists():
            config.read(self.profiles_file)

        for provider in providers:
            print(f"\n" + "="*60)
            print(f"Setting up {provider.upper().replace('_', ' ')}")
            print("="*60)

            if provider == 'azure':
                self._setup_azure(config)
            elif provider == 'azure_frontdoor':
                self._setup_azure_frontdoor(config)
            elif provider == 'gcp':
                self._setup_gcp(config)
            elif provider == 'gcp_loadbalancer':
                self._setup_gcp_loadbalancer(config)
            elif provider == 'cloudflare':
                self._setup_cloudflare(config)
            elif provider == 'alibaba':
                self._setup_alibaba(config)

        with open(self.profiles_file, 'w') as f:
            config.write(f)

        print("\n" + "="*60)
        print(" Setup Complete!")
        print("="*60)
        print(f"\nConfiguration saved to: {self.profiles_file}")
        print("\nYou can now use OmniProx with your configured providers:")
        print("  omniprox --provider cloudflare --command create --url https://domaingoeshere.local")
        print("\nOr use the quick command:")
        print("  omni create https://domaingoeshere.local")

        return True

    def _setup_azure(self, config):
        """Setup Azure provider configuration"""
        print("\nAzure Setup Options:")
        print("  1. Use Azure CLI credentials (recommended)")
        print("  2. Enter service principal manually")
        print("  3. Skip for now")

        choice = input("\nSelect option (1-3): ").strip()

        profile_name = input("Profile name (default: 'default'): ").strip() or 'default'
        profile_key = f"azure:{profile_name}"

        if profile_key not in config:
            config[profile_key] = {}

        if choice == '1':
            cli_result = self._check_azure_cli()
            if cli_result['success']:
                account = cli_result['account']
                print(f"[OK] Azure CLI logged in as: {account.get('user', {}).get('name', 'Unknown')}")
                config[profile_key]['subscription_id'] = account.get('id', '')
                config[profile_key]['tenant_id'] = account.get('tenantId', '')
                config[profile_key]['use_cli'] = 'true'
                print(f"[OK] Tenant ID: {account.get('tenantId', 'Unknown')}")
            else:
                print(cli_result['error'])
                return

        elif choice == '2':
            creds = self._get_azure_service_principal()
            config[profile_key].update(creds)

        elif choice == '3':
            print("[OK] Will use Azure CLI credentials when available")

        config[profile_key]['location'] = input("Azure Location (default: eastus): ").strip() or 'eastus'
        config[profile_key]['resource_group'] = ''
        config[profile_key]['service_name'] = ''
        print(f"[OK] Azure profile '{profile_name}' configured")

    def _setup_gcp(self, config):
        """Setup GCP provider configuration"""
        print("\nGCP Setup Options:")
        print("  1. Use gcloud CLI credentials (recommended)")
        print("  2. Enter service account path manually")
        print("  3. Skip for now")

        choice = input("\nSelect option (1-3): ").strip()

        profile_name = input("Profile name (default: 'default'): ").strip() or 'default'
        profile_key = f"gcp:{profile_name}"

        if profile_key not in config:
            config[profile_key] = {}

        if choice == '1':
            try:
                result = subprocess.run(['gcloud', 'auth', 'list'],
                                      capture_output=True, text=True, check=False, timeout=30)
                if result.returncode == 0 and 'ACTIVE' in result.stdout:
                    print(f"[OK] GCloud CLI configured")
                    config[profile_key]['use_cli'] = 'true'
                else:
                    print("GCloud CLI not authenticated. Run 'gcloud auth login' first.")
                    return
            except FileNotFoundError:
                print("GCloud CLI not installed. Please install it first.")
                return

        elif choice == '2':
            config[profile_key]['credentials_path'] = input("Service Account JSON path: ").strip()

        elif choice == '3':
            print("[OK] Will use gcloud CLI credentials when available")

        config[profile_key]['project_id'] = input("GCP Project ID: ").strip()
        config[profile_key]['region'] = input("Region (default: us-central1): ").strip() or 'us-central1'
        print(f"[OK] GCP profile '{profile_name}' configured")

    def _setup_cloudflare(self, config):
        """Setup Cloudflare provider configuration"""
        print("\nCloudflare Workers Setup:")
        print("\nTo get your Cloudflare credentials:")
        print("1. Sign up at https://cloudflare.com")
        print("2. Go to https://dash.cloudflare.com/profile/api-tokens")
        print("3. Create Custom Token with 'Account:Cloudflare Workers Scripts:Edit' permission")
        print("4. Copy the token and your Account ID from the dashboard")
        print()

        profile_name = input("Profile name (default: 'default'): ").strip() or 'default'
        profile_key = f"cloudflare:{profile_name}"

        if profile_key not in config:
            config[profile_key] = {}

        config[profile_key]['api_token'] = getpass.getpass("Cloudflare API Token: ").strip()
        config[profile_key]['account_id'] = input("Cloudflare Account ID: ").strip()
        config[profile_key]['zone_id'] = input("Cloudflare Zone ID (optional): ").strip() or ''

        print(f"[OK] Cloudflare profile '{profile_name}' configured")

    def _setup_azure_frontdoor(self, config):
        """Setup Azure Front Door provider configuration"""
        print("\nAzure Front Door Setup:")
        print("Azure Front Door is a global CDN and application delivery network.")
        print("\nSetup Options:")
        print("  1. Use Azure CLI credentials (recommended)")
        print("  2. Enter service principal credentials")
        print("  3. Skip for now")

        choice = input("\nSelect option (1-3): ").strip()

        profile_name = input("Profile name (default: 'default'): ").strip() or 'default'
        profile_key = f"azure_frontdoor:{profile_name}"

        if profile_key not in config:
            config[profile_key] = {}

        config[profile_key]['use_cli'] = 'true' if choice == '1' else 'false'

        if choice == '1':
            cli_result = self._check_azure_cli()
            if cli_result['success']:
                account = cli_result['account']
                config[profile_key]['subscription_id'] = account['id']
                print(f"[OK] Using Azure subscription: {account['name']}")
            else:
                print(cli_result['error'])
                return

        elif choice == '2':
            creds = self._get_azure_service_principal()
            config[profile_key].update(creds)

        config[profile_key]['resource_group'] = input("Resource Group Name (default: omniprox-frontdoor): ").strip() or 'omniprox-frontdoor'
        print(f"[OK] Azure Front Door profile '{profile_name}' configured")

    def _setup_gcp_loadbalancer(self, config):
        """Setup GCP Load Balancer provider configuration"""
        print("\nGCP HTTPS Load Balancer Setup:")
        print("GCP Load Balancer provides global load balancing with anycast IP.")
        print("\nSetup Options:")
        print("  1. Use gcloud CLI credentials (recommended)")
        print("  2. Enter service account path manually")
        print("  3. Skip for now")

        choice = input("\nSelect option (1-3): ").strip()

        profile_name = input("Profile name (default: 'default'): ").strip() or 'default'
        profile_key = f"gcp_loadbalancer:{profile_name}"

        if profile_key not in config:
            config[profile_key] = {}

        if choice == '1':
            try:
                result = subprocess.run(['gcloud', 'auth', 'list'],
                                      capture_output=True, text=True, check=False, timeout=30)
                if result.returncode == 0 and 'ACTIVE' in result.stdout:
                    print(f"[OK] GCloud CLI configured")
                    config[profile_key]['use_cli'] = 'true'
                else:
                    print("GCloud CLI not authenticated. Run 'gcloud auth login' first.")
                    return
            except FileNotFoundError:
                print("GCloud CLI not installed. Please install it first.")
                return

        elif choice == '2':
            config[profile_key]['service_account_key'] = input("Service Account JSON path: ").strip()
            config[profile_key]['use_cli'] = 'false'

        config[profile_key]['project_id'] = input("GCP Project ID: ").strip()
        config[profile_key]['region'] = input("Region (default: us-central1): ").strip() or 'us-central1'
        config[profile_key]['zone'] = input("Zone (default: us-central1-a): ").strip() or 'us-central1-a'
        print(f"[OK] GCP Load Balancer profile '{profile_name}' configured")

    def _setup_alibaba(self, config):
        """Setup Alibaba Cloud provider configuration"""
        print("\nAlibaba Cloud API Gateway Setup:")
        print("Alibaba Cloud provides API Gateway services optimized for China and Asia-Pacific.")
        print("\nTo get your Alibaba Cloud credentials:")
        print("1. Sign up at https://www.alibabacloud.com")
        print("2. Go to RAM console to create an AccessKey")
        print("3. Copy your Access Key ID and Access Key Secret")
        print()

        profile_name = input("Profile name (default: 'default'): ").strip() or 'default'
        profile_key = f"alibaba:{profile_name}"

        if profile_key not in config:
            config[profile_key] = {}

        config[profile_key]['access_key_id'] = input("Access Key ID: ").strip()
        config[profile_key]['access_key_secret'] = getpass.getpass("Access Key Secret: ").strip()
        config[profile_key]['region_id'] = input("Region ID (default: cn-hangzhou): ").strip() or 'cn-hangzhou'

        print(f"[OK] Alibaba Cloud profile '{profile_name}' configured")


def check_first_run():
    """Check if this is the first time running OmniProx"""
    config_dir = Path.home() / '.omniprox'
    profiles_file = config_dir / 'profiles.ini'

    if not profiles_file.exists():
        print("\nFirst time using OmniProx? Let's set it up!")
        print("Run with --setup flag or press Ctrl+C to skip.\n")
        return True
    return False